from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import DATABASE_PATH
from app.models import Modality, Observation, SemanticEvent, Source, SourceStatus, SourceType
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


def ingest_pdf(
    pdf_path: str | Path,
    db_path: Path = DATABASE_PATH,
    source_id: str | None = None,
) -> dict[str, Any]:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"PDF file does not exist: {path}")

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF ingestion. Install dependencies with: pip install -r requirements.txt") from exc

    initialize_database(db_path)
    source_id = source_id or str(uuid4())
    existing_source = get_source(source_id, db_path)
    insert_source(
        Source(
            id=source_id,
            filename=existing_source.filename if existing_source else path.name,
            source_type=SourceType.PDF,
            path=str(path),
            status=SourceStatus.PROCESSING,
        ),
        db_path,
    )

    page_count = 0
    events_created = 0
    with fitz.open(str(path)) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
            page_count += 1
            observation = insert_observation(
                Observation(
                    modality=Modality.DOCUMENT,
                    content=text,
                    source_id=source_id,
                    source_path=str(path),
                    metadata={"page": index, "filename": path.name},
                ),
                db_path,
            )
            event = insert_event(
                SemanticEvent(
                    title=f"{path.name} — Page {index}",
                    summary=text[:1200],
                    source_id=source_id,
                    entities=[],
                    confidence=0.65,
                ),
                db_path,
            )
            link_event_observations(event.id, [observation.id], db_path)
            for edge in build_event_membership_edges(event, [observation]):
                insert_edge(edge, db_path)
            events_created += 1

    update_source_status(source_id, SourceStatus.READY, db_path, metadata={"pages": page_count})
    return {"source_id": source_id, "pages": page_count, "events_created": events_created}
