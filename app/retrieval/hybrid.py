from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH, INDEXES_DIR
from app.graph.graph_rag import get_graph_expansion_if_configured
from app.retrieval.evidence_bundle import build_evidence_bundle
from app.retrieval.vector_store import search
from app.storage.database import get_event


GRAPH_EXPANSION_SCORE_FACTOR = 0.75


def retrieve(
    source_id: str,
    query: str,
    top_k: int = 3,
    graph_top_k: int = 2,
    db_path: Path = DATABASE_PATH,
    index_root: Path = INDEXES_DIR,
) -> dict[str, Any]:
    event_results = search(source_id, query, top_k=top_k, db_path=db_path, index_root=index_root)
    graph = get_graph_expansion_if_configured(
        source_id,
        [result["event_id"] for result in event_results],
        related_events_per_seed=graph_top_k,
    )
    selected_results: list[dict[str, Any]] = []
    selected_event_ids: set[str] = set()
    for event_result in event_results:
        selected_results.append({**event_result, "retrieval_path": {"type": "vector"}})
        selected_event_ids.add(event_result["event_id"])

    if graph["status"] == "ready":
        for seed_result in event_results:
            context = graph["contexts"].get(seed_result["event_id"], {})
            for related_event in context.get("related_events", []):
                event_id = related_event["id"]
                if event_id in selected_event_ids:
                    continue
                event = get_event(event_id, db_path)
                if event is None or event.source_id != source_id:
                    continue
                selected_results.append(
                    {
                        "event_id": event.id,
                        "score": round(float(seed_result["score"]) * GRAPH_EXPANSION_SCORE_FACTOR, 6),
                        "title": event.title,
                        "summary": event.summary,
                        "retrieval_path": {
                            "type": "graph_expansion",
                            "shared_entities": related_event.get("shared_entities", []),
                        },
                    }
                )
                selected_event_ids.add(event_id)

    results = []
    for rank, result in enumerate(selected_results, start=1):
        bundle = build_evidence_bundle(result["event_id"], db_path)
        results.append(
            {
                "rank": rank,
                "score": result["score"],
                "event": {
                    "id": result["event_id"],
                    "title": result["title"],
                    "summary": result["summary"],
                },
                "retrieval_path": result["retrieval_path"],
                "evidence_bundle": bundle,
            }
        )
    return {"query": query, "results": results, "graph": {key: value for key, value in graph.items() if key != "contexts"}}


def _print_result(payload: dict[str, Any]) -> None:
    print("QUERY")
    print(payload["query"])
    print()
    print("TOP EVENTS")
    for result in payload["results"]:
        bundle = result["evidence_bundle"]
        print()
        print(f"EVENT {result['rank']}")
        print(f"score: {result['score']}")
        print(f"title: {result['event']['title']}")
        print(f"summary: {result['event']['summary']}")
        print()
        print("EVIDENCE")
        print("transcript:")
        for transcript in bundle["transcripts"]:
            print(f"- {transcript['start_time']} - {transcript['end_time']}: {transcript['content']}")
        print("OCR:")
        for ocr in bundle["ocr"]:
            print(f"- {ocr['timestamp']}: {ocr['text']}")
        print("frames:")
        for frame in bundle["frames"]:
            print(f"- {frame['timestamp']}: {frame['path']}")
        print("entities:")
        for entity in bundle["entities"]:
            print(f"- {entity['name']} | {entity['type']} | {entity['confidence']}")
        print("relationships:")
        for relationship in bundle["relationships"]:
            print(
                f"- {relationship['source']} --{relationship['relation']}--> "
                f"{relationship['target']} | {relationship['confidence']} | {relationship['method']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid event retrieval over FAISS + evidence graph.")
    parser.add_argument("source_id")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of readable output.")
    args = parser.parse_args()

    payload = retrieve(args.source_id, args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_result(payload)


if __name__ == "__main__":
    main()
