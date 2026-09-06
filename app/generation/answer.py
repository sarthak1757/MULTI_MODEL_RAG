from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH, INDEXES_DIR
from app.retrieval.hybrid import retrieve
from app.semantic.gemini_client import GeminiClient, MissingGeminiAPIKeyError


def _clean_text(text: str) -> str:
    return " ".join(str(text).split())


def compact_generation_context(retrieval_payload: dict[str, Any]) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for result in retrieval_payload.get("results", []):
        bundle = result["evidence_bundle"]
        event = bundle["event"]
        relationships = [
            {
                "relation": relationship["relation"],
                "confidence": relationship["confidence"],
                "method": relationship["method"],
            }
            for relationship in bundle["relationships"]
            if relationship["method"] == "llm"
        ]
        context.append(
            {
                "rank": result["rank"],
                "retrieval_score": result["score"],
                "event_id": event["id"],
                "title": event["title"],
                "summary": event["summary"],
                "timestamp_start": event["start_time"],
                "timestamp_end": event["end_time"],
                "event_confidence": event["confidence"],
                "transcript_evidence": [
                    {
                        "start_time": transcript["start_time"],
                        "end_time": transcript["end_time"],
                        "text": transcript["content"],
                    }
                    for transcript in bundle["transcripts"]
                ],
                "ocr_evidence": [
                    {
                        "timestamp": ocr["timestamp"],
                        "text": ocr["text"],
                        "confidence": ocr["confidence"],
                    }
                    for ocr in bundle["ocr"]
                ],
                "document_evidence": [
                    {
                        "page": document["metadata"].get("page"),
                        "text": document["text"],
                    }
                    for document in bundle.get("documents", [])
                ],
                "frames": [
                    {
                        "frame_id": frame["id"],
                        "timestamp": frame["timestamp"],
                    }
                    for frame in bundle["frames"]
                ],
                "entities": [
                    {
                        "name": entity["name"],
                        "type": entity["type"],
                        "confidence": entity["confidence"],
                    }
                    for entity in bundle["entities"]
                ],
                "semantic_relationships": relationships[:10],
            }
        )
    return context


def build_answer_prompt(query: str, context: list[dict[str, Any]]) -> str:
    return (
        "You answer questions using only supplied multimodal evidence bundles.\n\n"
        "Rules:\n"
        "- Do not use outside knowledge.\n"
        "- Do not invent facts.\n"
        "- If the evidence is insufficient, explicitly say so.\n"
        "- Prefer direct transcript evidence.\n"
        "- Use OCR and visual evidence when it adds information.\n"
        "- Preserve uncertainty when OCR is noisy.\n"
        "- Keep answers concise but explanatory.\n\n"
        "Return strict JSON with exactly this shape:\n"
        "{\n"
        '  "answer": "...",\n'
        '  "confidence": 0.0,\n'
        '  "citations": [\n'
        '    {"event_id": "...", "timestamp_start": 0.0, "timestamp_end": 0.0, '
        '"evidence_types": ["transcript"], "support": "..."}\n'
        "  ],\n"
        '  "key_entities": ["..."],\n'
        '  "used_modalities": ["transcript"]\n'
        "}\n\n"
        "The confidence field you return will be ignored and replaced with a local deterministic score.\n\n"
        f"QUESTION:\n{query}\n\n"
        f"EVIDENCE_CONTEXT:\n{json.dumps(context, indent=2)}"
    )


def parse_answer_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    data = json.loads(clean)
    if not isinstance(data, dict):
        raise ValueError("Gemini answer response must be a JSON object.")
    return data


def call_gemini_answer(client: GeminiClient, prompt: str) -> dict[str, Any]:
    first_response = client.generate_json(prompt)
    try:
        return parse_answer_json(first_response)
    except (json.JSONDecodeError, ValueError):
        retry_prompt = prompt + "\n\nYour previous response was invalid. Return strict JSON only."
        return parse_answer_json(client.generate_json(retry_prompt))


def calculate_confidence(retrieval_payload: dict[str, Any]) -> float:
    results = retrieval_payload.get("results", [])
    if not results:
        return 0.0

    top_score = max(0.0, min(1.0, float(results[0].get("score") or 0.0)))
    second_score = max(0.0, min(1.0, float(results[1].get("score") or 0.0))) if len(results) > 1 else 0.0
    score_gap = max(0.0, top_score - second_score)
    top_bundle = results[0]["evidence_bundle"]
    event_confidence = float(top_bundle["event"].get("confidence") or 0.5)
    modalities = set()
    if top_bundle["transcripts"]:
        modalities.add("transcript")
    if top_bundle["ocr"]:
        modalities.add("ocr")
    if top_bundle["frames"]:
        modalities.add("frame")
    modality_score = len(modalities) / 3
    evidence_count = len(top_bundle["transcripts"]) + len(top_bundle["ocr"]) + len(top_bundle["frames"])
    evidence_score = min(1.0, evidence_count / 5)

    confidence = (
        0.35 * top_score
        + 0.20 * score_gap
        + 0.20 * event_confidence
        + 0.15 * modality_score
        + 0.10 * evidence_score
    )
    return round(max(0.0, min(1.0, confidence)), 3)


def insufficient_evidence_response(query: str, retrieval_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "query": query,
        "answer": "The retrieved evidence is insufficient to answer this question.",
        "confidence": 0.0,
        "citations": [],
        "key_entities": [],
        "used_modalities": [],
        "retrieval": retrieval_payload or {"query": query, "results": []},
        "error": None,
    }


def answer_question(
    source_id: str,
    query: str,
    top_k: int = 3,
    client: GeminiClient | None = None,
    db_path: Path = DATABASE_PATH,
    index_root: Path = INDEXES_DIR,
) -> dict[str, Any]:
    retrieval_payload = retrieve(source_id, query, top_k=top_k, db_path=db_path, index_root=index_root)
    if not retrieval_payload.get("results"):
        return insufficient_evidence_response(query, retrieval_payload)

    prompt = build_answer_prompt(query, compact_generation_context(retrieval_payload))
    try:
        gemini = client or GeminiClient()
        model_response = call_gemini_answer(gemini, prompt)
    except Exception as exc:
        response = insufficient_evidence_response(query, retrieval_payload)
        response["error"] = f"Answer generation failed: {exc}"
        return response

    confidence = calculate_confidence(retrieval_payload)
    return {
        "query": query,
        "answer": str(model_response.get("answer") or "").strip()
        or "The retrieved evidence is insufficient to answer this question.",
        "confidence": confidence,
        "citations": model_response.get("citations") or [],
        "key_entities": model_response.get("key_entities") or [],
        "used_modalities": model_response.get("used_modalities") or [],
        "retrieval": retrieval_payload,
        "error": None,
    }


def _print_answer(payload: dict[str, Any], debug: bool = False) -> None:
    print("QUESTION")
    print(payload["query"])
    print()
    print("ANSWER")
    print(payload["answer"])
    print()
    print("CONFIDENCE")
    print(payload["confidence"])
    print()
    print("EVIDENCE")
    for index, result in enumerate(payload["retrieval"].get("results", []), start=1):
        bundle = result["evidence_bundle"]
        event = bundle["event"]
        modalities = []
        if bundle["transcripts"]:
            modalities.append("transcript")
        if bundle["ocr"]:
            modalities.append("OCR")
        if bundle["frames"]:
            modalities.append("frame")
        print()
        print(f"[{index}] {event['start_time']} - {event['end_time']}")
        print(f"Event: {event['title']}")
        print(f"Modalities: {', '.join(modalities) if modalities else '(none)'}")
        print()
        print("Transcript:")
        transcript_text = " ".join(_clean_text(item["content"]) for item in bundle["transcripts"])
        print(f"\"{transcript_text}\"" if transcript_text else "(none)")
        print()
        print("OCR:")
        ocr_text = " ".join(_clean_text(item["text"]) for item in bundle["ocr"])
        print(f"\"{ocr_text}\"" if ocr_text else "(none)")
        print()
        print("Entities:")
        entity_names = [entity["name"] for entity in bundle["entities"]]
        print(", ".join(entity_names) if entity_names else "(none)")
    if payload.get("error"):
        print()
        print("ERROR")
        print(payload["error"])
    if debug:
        print()
        print("DEBUG")
        print(json.dumps(payload["retrieval"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grounded answers from retrieved evidence bundles.")
    parser.add_argument("source_id")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    try:
        payload = answer_question(args.source_id, args.query, top_k=args.top_k)
    except MissingGeminiAPIKeyError as exc:
        raise SystemExit(str(exc)) from exc
    _print_answer(payload, debug=args.debug)


if __name__ == "__main__":
    main()
