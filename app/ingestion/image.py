from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import DATABASE_PATH
from app.ingestion.ocr import ocr_frame
from app.models import EdgeMethod, EvidenceEdge, Modality, Observation, SemanticEvent, Source, SourceStatus, SourceType
from app.processing.graph_builder import build_event_membership_edges
from app.storage.database import (
    initialize_database,
    get_source,
    insert_edge,
    insert_event,
    insert_observation,
    insert_source,
    link_event_observations,
    update_source_status,
)


def ingest_image(
    image_path: str | Path,
    db_path: Path = DATABASE_PATH,
    source_id: str | None = None,
) -> dict[str, Any]:
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image file does not exist: {path}")

    initialize_database(db_path)
    source_id = source_id or str(uuid4())
    existing_source = get_source(source_id, db_path)
    insert_source(
        Source(
            id=source_id,
            filename=existing_source.filename if existing_source else path.name,
            source_type=SourceType.IMAGE,
            path=str(path),
            status=SourceStatus.PROCESSING,
        ),
        db_path,
    )

    image_observation = insert_observation(
        Observation(
            modality=Modality.IMAGE,
            content=str(path),
            source_id=source_id,
            source_path=str(path),
            confidence=1.0,
            metadata={"filename": path.name},
        ),
        db_path,
    )

    ocr_observation = ocr_frame(image_observation, source_id, str(path))
    observations = [image_observation]
    if ocr_observation is not None:
        ocr_observation = insert_observation(ocr_observation, db_path)
        observations.append(ocr_observation)
        insert_edge(
            EvidenceEdge(
                source_node_id=ocr_observation.id,
                target_node_id=image_observation.id,
                relation="EXTRACTED_FROM",
                confidence=1.0,
                method=EdgeMethod.PROVENANCE,
                evidence_observation_ids=[ocr_observation.id, image_observation.id],
                metadata={"source_id": source_id},
            ),
            db_path,
        )

    summary_text = ocr_observation.content if ocr_observation else f"Image source: {path.name}"
    event = insert_event(
        SemanticEvent(
            title=f"Image: {path.name}",
            summary=summary_text,
            source_id=source_id,
            confidence=0.7 if ocr_observation else 0.4,
        ),
        db_path,
    )
    link_event_observations(event.id, [observation.id for observation in observations], db_path)
    for edge in build_event_membership_edges(event, observations):
        insert_edge(edge, db_path)

    update_source_status(source_id, SourceStatus.READY, db_path, metadata={"ocr_observations": int(ocr_observation is not None)})
    return {
        "source_id": source_id,
        "image_observations": 1,
        "ocr_observations": int(ocr_observation is not None),
        "events_created": 1,
    }
