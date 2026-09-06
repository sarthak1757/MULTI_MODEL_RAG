from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.config import DATABASE_PATH
from app.models import EdgeMethod, Entity, EvidenceEdge, Modality, Observation, SemanticEvent
from app.semantic.gemini_client import GeminiClient, GeminiRateLimitError, MissingGeminiAPIKeyError
from app.storage.database import (
    get_entities_for_event,
    get_entity_by_normalized_name,
    get_event,
    get_event_observations,
    initialize_database,
    insert_edge,
    insert_entity,
    link_entity_to_event,
    list_events_for_source,
    update_event_semantics,
)

ALLOWED_RELATIONS = {
    "MENTIONS",
    "LOCATED_IN",
    "ENABLES",
    "USES",
    "PART_OF",
    "RELATED_TO",
    "DISCUSSES",
}


def normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _edge_id(source_id: str, target_id: str, relation: str, event_id: str) -> str:
    key = f"multimodal-rag:semantic-edge:{event_id}:{source_id}:{relation}:{target_id}"
    return str(uuid5(NAMESPACE_URL, key))


def event_input(event: SemanticEvent, observations: list[Observation]) -> dict[str, Any]:
    transcripts = [
        {
            "observation_id": observation.id,
            "start_time": observation.start_time,
            "end_time": observation.end_time,
            "text": observation.content,
        }
        for observation in observations
        if observation.modality == Modality.TRANSCRIPT
    ]
    ocr = [
        {
            "observation_id": observation.id,
            "timestamp": observation.timestamp,
            "text": observation.content,
        }
        for observation in observations
        if observation.modality == Modality.OCR
    ]
    frames = [
        {
            "observation_id": observation.id,
            "timestamp": observation.timestamp,
            "path": observation.content,
        }
        for observation in observations
        if observation.modality == Modality.FRAME
    ]
    documents = [
        {
            "observation_id": observation.id,
            "page": observation.metadata.get("page"),
            "text": observation.content,
        }
        for observation in observations
        if observation.modality == Modality.DOCUMENT
    ]
    return {
        "event_id": event.id,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "transcript": " ".join(item["text"] for item in transcripts),
        "transcript_observations": transcripts,
        "ocr": ocr,
        "frames": frames,
        "documents": documents,
    }


def build_prompt(payload: dict[str, Any]) -> str:
    return (
        "You enrich deterministic multimodal video events. The event membership is fixed; "
        "do not decide which observations belong to the event.\n\n"
        "Use only the provided transcript and OCR evidence. Do not invent missing facts. "
        "OCR may be noisy, so cautiously correct obvious OCR errors only when transcript context supports it. "
        "If uncertain, keep the OCR form or lower confidence.\n\n"
        "Return strict JSON with exactly this shape:\n"
        "{\n"
        '  "title": "...",\n'
        '  "summary": "...",\n'
        '  "entities": [\n'
        '    {"name": "...", "type": "...", "confidence": 0.0, "evidence_observation_ids": ["..."]}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"source": "...", "relation": "MENTIONS", "target": "...", "confidence": 0.0, '
        '"evidence_observation_ids": ["..."]}\n'
        "  ]\n"
        "}\n\n"
        "Relation names should be short and conservative, preferably one of: "
        "MENTIONS, LOCATED_IN, ENABLES, USES, PART_OF, RELATED_TO, DISCUSSES.\n"
        "Every entity and relationship must include evidence_observation_ids drawn from the input.\n\n"
        f"EVENT_INPUT:\n{json.dumps(payload, indent=2)}"
    )


def parse_gemini_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    data = json.loads(clean)
    if not isinstance(data, dict):
        raise ValueError("Gemini JSON response must be an object.")
    return data


def call_gemini_with_json_retry(client: GeminiClient, prompt: str) -> dict[str, Any]:
    first_response = client.generate_json(prompt)
    try:
        return parse_gemini_json(first_response)
    except (json.JSONDecodeError, ValueError):
        retry_prompt = prompt + "\n\nYour previous response was invalid. Return strict JSON only."
        second_response = client.generate_json(retry_prompt)
        return parse_gemini_json(second_response)


def _entity_from_payload(item: dict[str, Any], event_id: str) -> Entity | None:
    name = str(item.get("name", "")).strip()
    if not name:
        return None
    confidence = item.get("confidence")
    evidence_ids = item.get("evidence_observation_ids") or []
    normalized_name = normalize_entity_name(name)
    return Entity(
        name=name,
        normalized_name=normalized_name,
        entity_type=item.get("type") or item.get("entity_type"),
        confidence=float(confidence) if confidence is not None else None,
        metadata={
            "event_id": event_id,
            "extractor": "gemini",
            "evidence_observation_ids": evidence_ids,
        },
    )


def get_or_create_entity(entity: Entity, db_path: Path) -> Entity:
    existing = get_entity_by_normalized_name(entity.normalized_name, db_path)
    if existing is not None:
        return existing
    insert_entity(entity, db_path)
    created = get_entity_by_normalized_name(entity.normalized_name, db_path)
    return created or entity


def _resolved_entity(
    name: str,
    entity_by_normalized_name: dict[str, Entity],
) -> Entity | None:
    return entity_by_normalized_name.get(normalize_entity_name(name))


def _relationship_edges(
    event_id: str,
    relationships: list[dict[str, Any]],
    entity_by_normalized_name: dict[str, Entity],
) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = []
    for relationship in relationships:
        confidence = float(relationship.get("confidence") or 0.0)
        evidence_ids = relationship.get("evidence_observation_ids") or []
        relation = str(relationship.get("relation", "RELATED_TO")).strip().upper()
        if relation not in ALLOWED_RELATIONS:
            relation = "RELATED_TO"
        if confidence < 0.60 or not evidence_ids:
            continue

        source = _resolved_entity(str(relationship.get("source", "")), entity_by_normalized_name)
        target = _resolved_entity(str(relationship.get("target", "")), entity_by_normalized_name)
        if source is None or target is None:
            continue

        edges.append(
            EvidenceEdge(
                id=_edge_id(source.id, target.id, relation, event_id),
                source_node_id=source.id,
                target_node_id=target.id,
                relation=relation,
                confidence=confidence,
                method=EdgeMethod.LLM,
                evidence_observation_ids=[str(evidence_id) for evidence_id in evidence_ids],
                metadata={
                    "event_id": event_id,
                    "extractor": "gemini",
                    "relation_source": "semantic_enrichment",
                },
            )
        )
    return edges


def enrich_event(
    event: SemanticEvent,
    client: GeminiClient,
    db_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    observations = get_event_observations(event.id, db_path)
    before = {"title": event.title, "summary": event.summary}
    payload = event_input(event, observations)
    response = call_gemini_with_json_retry(client, build_prompt(payload))

    title = str(response.get("title") or event.title).strip()
    summary = str(response.get("summary") or event.summary).strip()
    entity_items = response.get("entities") or []
    relationship_items = response.get("relationships") or []

    entity_by_normalized_name: dict[str, Entity] = {}
    for item in entity_items:
        if not isinstance(item, dict):
            continue
        entity = _entity_from_payload(item, event.id)
        if entity is None:
            continue
        persisted_entity = get_or_create_entity(entity, db_path)
        confidence = entity.confidence if entity.confidence is not None else persisted_entity.confidence
        link_entity_to_event(event.id, persisted_entity.id, confidence=confidence, db_path=db_path)
        entity_by_normalized_name[persisted_entity.normalized_name] = persisted_entity

    relationship_edges = _relationship_edges(event.id, relationship_items, entity_by_normalized_name)
    for edge in relationship_edges:
        insert_edge(edge, db_path)

    entity_names = sorted({entity.name for entity in entity_by_normalized_name.values()})
    entity_name_by_id = {
        entity.id: entity.name
        for entity in entity_by_normalized_name.values()
    }
    update_event_semantics(event.id, title, summary, entity_names, db_path)
    after = {"title": title, "summary": summary}

    return {
        "event_id": event.id,
        "before": before,
        "after": after,
        "entities": get_entities_for_event(event.id, db_path),
        "relationships": relationship_edges,
        "relationship_labels": [
            {
                "source": entity_name_by_id.get(edge.source_node_id, edge.source_node_id),
                "relation": edge.relation,
                "target": entity_name_by_id.get(edge.target_node_id, edge.target_node_id),
                "confidence": edge.confidence,
            }
            for edge in relationship_edges
        ],
    }


def enrich_source(
    source_id: str,
    event_id: str | None = None,
    client: GeminiClient | None = None,
    db_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    initialize_database(db_path)
    gemini = client or GeminiClient()

    if event_id:
        event = get_event(event_id, db_path)
        events = [event] if event and event.source_id == source_id else []
    else:
        events = list_events_for_source(source_id, db_path)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for event in events:
        try:
            results.append(enrich_event(event, gemini, db_path))
        except GeminiRateLimitError as exc:
            errors.append({"event_id": event.id, "error": str(exc)})
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append({"event_id": event.id, "error": f"Invalid Gemini JSON: {exc}"})
            continue

    return {
        "source_id": source_id,
        "events_requested": len(events),
        "events_enriched": len(results),
        "errors": errors,
        "results": results,
    }


def print_enrichment_debug(result: dict[str, Any]) -> None:
    print("BEFORE")
    print(f"Title: {result['before']['title']}")
    print(f"Summary: {result['before']['summary']}")
    print()
    print("AFTER")
    print(f"Title: {result['after']['title']}")
    print(f"Summary: {result['after']['summary']}")
    print()
    print("Entities:")
    for entity in result["entities"]:
        print(f"- {entity.name} | {entity.entity_type} | {entity.confidence}")
    if not result["entities"]:
        print("- (none)")
    print()
    print("Relationships:")
    for relationship in result["relationship_labels"]:
        print(
            f"- {relationship['source']} --{relationship['relation']}--> "
            f"{relationship['target']} | {relationship['confidence']}"
        )
    if not result["relationship_labels"]:
        print("- (none)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich existing SemanticEvents with Gemini.")
    parser.add_argument("source_id", help="Source UUID.")
    parser.add_argument("--event", dest="event_id", help="Only enrich a single SemanticEvent ID.")
    args = parser.parse_args()

    try:
        summary = enrich_source(args.source_id, event_id=args.event_id)
    except MissingGeminiAPIKeyError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        json.dumps(
            {
                "source_id": summary["source_id"],
                "events_requested": summary["events_requested"],
                "events_enriched": summary["events_enriched"],
                "errors": summary["errors"],
            },
            indent=2,
        )
    )
    for result in summary["results"]:
        print()
        print_enrichment_debug(result)


if __name__ == "__main__":
    main()
