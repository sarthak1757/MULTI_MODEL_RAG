from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH
from app.models import Modality
from app.storage.database import (
    get_entities_for_event,
    get_event,
    get_event_observations,
    get_neighbors,
)


def _event_dict(event) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "source_id": event.source_id,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "entities": event.entities,
        "confidence": event.confidence,
    }


def _edge_dict(edge) -> dict[str, Any]:
    return {
        "source": edge.source_node_id,
        "relation": edge.relation,
        "target": edge.target_node_id,
        "confidence": edge.confidence,
        "method": edge.method.value,
        "evidence_observation_ids": edge.evidence_observation_ids,
        "metadata": edge.metadata,
    }


def build_evidence_bundle(event_id: str, db_path: Path = DATABASE_PATH) -> dict[str, Any]:
    event = get_event(event_id, db_path)
    if event is None:
        raise ValueError(f"SemanticEvent not found: {event_id}")

    observations = get_event_observations(event_id, db_path)
    transcripts = [
        {
            "id": observation.id,
            "start_time": observation.start_time,
            "end_time": observation.end_time,
            "content": observation.content,
            "confidence": observation.confidence,
        }
        for observation in observations
        if observation.modality == Modality.TRANSCRIPT
    ]
    frames = [
        {
            "id": observation.id,
            "timestamp": observation.timestamp,
            "path": observation.content,
            "confidence": observation.confidence,
        }
        for observation in observations
        if observation.modality == Modality.FRAME
    ]
    ocr = [
        {
            "id": observation.id,
            "timestamp": observation.timestamp,
            "text": observation.content,
            "confidence": observation.confidence,
            "metadata": observation.metadata,
        }
        for observation in observations
        if observation.modality == Modality.OCR
    ]
    images = [
        {
            "id": observation.id,
            "path": observation.content,
            "confidence": observation.confidence,
            "metadata": observation.metadata,
        }
        for observation in observations
        if observation.modality == Modality.IMAGE
    ]
    documents = [
        {
            "id": observation.id,
            "text": observation.content,
            "confidence": observation.confidence,
            "metadata": observation.metadata,
        }
        for observation in observations
        if observation.modality == Modality.DOCUMENT
    ]
    entities = [
        {
            "id": entity.id,
            "name": entity.name,
            "normalized_name": entity.normalized_name,
            "type": entity.entity_type,
            "confidence": entity.confidence,
            "metadata": entity.metadata,
        }
        for entity in get_entities_for_event(event_id, db_path)
    ]

    node_ids = {event_id}
    node_ids.update(observation.id for observation in observations)
    node_ids.update(entity["id"] for entity in entities)
    relationships_by_id = {}
    for node_id in node_ids:
        neighbors = get_neighbors(node_id, db_path)
        for edge in neighbors["edges"]:
            relationships_by_id[edge.id] = _edge_dict(edge)

    return {
        "event": _event_dict(event),
        "transcripts": transcripts,
        "frames": frames,
        "ocr": ocr,
        "images": images,
        "documents": documents,
        "entities": entities,
        "relationships": list(relationships_by_id.values()),
    }
