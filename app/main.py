from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import DATABASE_PATH, DATA_DIR, INDEXES_DIR, UPLOADS_DIR
from app.generation.answer import answer_question
from app.graph.sync import sync_source_if_configured
from app.ingestion.image import ingest_image
from app.ingestion.pdf import ingest_pdf
from app.ingestion.pipeline import ingest_video
from app.models import Modality, Source, SourceStatus, SourceType
from app.processing.event_builder import process_source
from app.retrieval.vector_store import build_index
from app.semantic.enricher import enrich_source
from app.storage.database import (
    delete_source,
    get_event_observations,
    get_observation,
    get_source,
    initialize_database,
    insert_source,
    list_events,
    list_events_for_source,
    list_observations_for_source,
    list_sources,
    update_source_status,
)

app = FastAPI(
    title="Multimodal RAG",
    description="Event-centric multimodal RAG API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}
ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS


class QueryRequest(BaseModel):
    source_id: str
    question: str


def _source_type_for_suffix(suffix: str) -> SourceType:
    if suffix in VIDEO_EXTENSIONS:
        return SourceType.VIDEO
    if suffix in IMAGE_EXTENSIONS:
        return SourceType.IMAGE
    if suffix in PDF_EXTENSIONS:
        return SourceType.PDF
    raise ValueError("Unsupported file type.")


def _source_type_for_existing_path(path: str) -> SourceType:
    try:
        return _source_type_for_suffix(Path(path).suffix.lower())
    except ValueError:
        return SourceType.VIDEO


def _safe_upload_path(filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type.")
    stem = Path(filename).stem[:80] or "source"
    safe_stem = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in stem)
    return UPLOADS_DIR / f"{safe_stem}_{uuid4().hex[:12]}{suffix}"


def _source_payload(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "source_id": source.id,
        "filename": source.filename,
        "source_type": source.source_type.value,
        "duration": source.duration,
        "status": source.status.value,
        "error_message": source.metadata.get("error"),
        "created_at": source.created_at.isoformat(),
    }


def _fallback_sources() -> list[Source]:
    sources: dict[str, Source] = {}
    for event in list_events(DATABASE_PATH):
        if event.source_id in sources:
            continue
        observations = list_observations_for_source(event.source_id, DATABASE_PATH)
        first_path = observations[0].source_path if observations else event.source_id
        sources[event.source_id] = Source(
            id=event.source_id,
            filename=Path(first_path).name,
            source_type=_source_type_for_existing_path(first_path),
            path=first_path,
            duration=max(
                [candidate.end_time for candidate in list_events_for_source(event.source_id, DATABASE_PATH) if candidate.end_time is not None],
                default=None,
            ),
            status=SourceStatus.READY,
        )
    return list(sources.values())


def _all_sources() -> list[Source]:
    registered = {source.id: source for source in list_sources(DATABASE_PATH)}
    for source in _fallback_sources():
        registered.setdefault(source.id, source)
    return list(registered.values())


def _find_source(source_id: str) -> Source | None:
    source = get_source(source_id, DATABASE_PATH)
    if source is not None:
        return source
    return next((candidate for candidate in _fallback_sources() if candidate.id == source_id), None)


def _modalities_for_event(event_id: str) -> list[str]:
    observations = get_event_observations(event_id, DATABASE_PATH)
    return sorted({observation.modality.value for observation in observations})


def _concise_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message[:300] if message else exc.__class__.__name__


def _delete_path_under_data(path: Path) -> None:
    resolved = path.resolve()
    data_root = DATA_DIR.resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return
    if resolved.is_file():
        resolved.unlink(missing_ok=True)
    elif resolved.is_dir():
        shutil.rmtree(resolved, ignore_errors=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sources")
def api_sources() -> list[dict[str, Any]]:
    initialize_database(DATABASE_PATH)
    return [_source_payload(source) for source in _all_sources()]


@app.get("/api/sources/{source_id}")
def api_source(source_id: str) -> dict[str, Any]:
    initialize_database(DATABASE_PATH)
    source = _find_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return _source_payload(source)


@app.delete("/api/sources/{source_id}", status_code=204)
def api_delete_source(source_id: str) -> None:
    initialize_database(DATABASE_PATH)
    source = get_source(source_id, DATABASE_PATH)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    observations = list_observations_for_source(source_id, DATABASE_PATH)
    if not delete_source(source_id, DATABASE_PATH):
        raise HTTPException(status_code=404, detail="Source not found.")

    _delete_path_under_data(Path(source.path))
    _delete_path_under_data(INDEXES_DIR / source_id)
    for observation in observations:
        if observation.modality in {Modality.FRAME, Modality.IMAGE}:
            _delete_path_under_data(Path(observation.content))


@app.post("/api/sources/upload")
def api_upload_source(file: UploadFile = File(...)) -> dict[str, Any]:
    initialize_database(DATABASE_PATH)
    try:
        destination = _safe_upload_path(file.filename or "source")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    source_id = str(uuid4())
    source = insert_source(
        Source(
            id=source_id,
            filename=file.filename or destination.name,
            source_type=_source_type_for_suffix(destination.suffix.lower()),
            path=str(destination),
            status=SourceStatus.UPLOADED,
        ),
        DATABASE_PATH,
    )
    return _source_payload(source)


@app.post("/api/sources/{source_id}/process")
def api_process_source(source_id: str) -> dict[str, Any]:
    initialize_database(DATABASE_PATH)
    source = get_source(source_id, DATABASE_PATH)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    update_source_status(source_id, SourceStatus.PROCESSING, DATABASE_PATH)
    stats: dict[str, Any] = {}
    try:
        source_path = Path(source.path)
        if source.source_type == SourceType.VIDEO:
            ingest_summary = ingest_video(source_path, db_path=DATABASE_PATH, source_id=source_id)
            processing_summary = process_source(source_id, db_path=DATABASE_PATH)
            enrichment_summary = enrich_source(source_id, db_path=DATABASE_PATH)
            index_summary = build_index(source_id, db_path=DATABASE_PATH)
            stats = {
                "transcripts": ingest_summary["transcript_segments"],
                "frames": ingest_summary["frames"],
                "ocr": ingest_summary["ocr_observations"],
                "events": processing_summary["events_created"],
                "temporal_edges": processing_summary["temporal_edges"],
                "enriched_events": enrichment_summary["events_enriched"],
                "index_events": index_summary["events_indexed"],
            }
            update_source_status(source_id, SourceStatus.READY, DATABASE_PATH, duration=ingest_summary.get("duration"))
        elif source.source_type == SourceType.IMAGE:
            ingest_summary = ingest_image(source_path, db_path=DATABASE_PATH, source_id=source_id)
            enrichment_summary = enrich_source(source_id, db_path=DATABASE_PATH)
            index_summary = build_index(source_id, db_path=DATABASE_PATH)
            stats = {
                "images": ingest_summary["image_observations"],
                "ocr": ingest_summary["ocr_observations"],
                "events": ingest_summary["events_created"],
                "enriched_events": enrichment_summary["events_enriched"],
                "index_events": index_summary["events_indexed"],
            }
            update_source_status(source_id, SourceStatus.READY, DATABASE_PATH)
        elif source.source_type == SourceType.PDF:
            ingest_summary = ingest_pdf(source_path, db_path=DATABASE_PATH, source_id=source_id)
            enrichment_summary = enrich_source(source_id, db_path=DATABASE_PATH)
            index_summary = build_index(source_id, db_path=DATABASE_PATH)
            stats = {
                "pages": ingest_summary["pages"],
                "events": ingest_summary["events_created"],
                "enriched_events": enrichment_summary["events_enriched"],
                "index_events": index_summary["events_indexed"],
            }
            update_source_status(source_id, SourceStatus.READY, DATABASE_PATH)
        else:
            raise ValueError("Unsupported source type.")

        stats["graph"] = sync_source_if_configured(source_id, db_path=DATABASE_PATH)
    except Exception as exc:
        error = _concise_error(exc)
        update_source_status(source_id, SourceStatus.FAILED, DATABASE_PATH, metadata={"error": error})
        return {"source_id": source_id, "status": "failed", "error": error, "stats": stats}

    return {"source_id": source_id, "status": "ready", "stats": stats}


@app.post("/api/query")
def api_query(request: QueryRequest) -> dict[str, Any]:
    initialize_database(DATABASE_PATH)
    source = _find_source(request.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    try:
        payload = answer_question(request.source_id, request.question)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Index not built for this source.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_concise_error(exc)) from exc

    evidence = []
    for result in payload["retrieval"].get("results", []):
        bundle = result["evidence_bundle"]
        event = bundle["event"]
        evidence.append(
            {
                "event_id": event["id"],
                "title": event["title"],
                "start_time": event["start_time"],
                "end_time": event["end_time"],
                "score": result["score"],
                "transcript": "\n\n".join(item["content"] for item in bundle["transcripts"]),
                "ocr": [
                    {
                        "timestamp": item["timestamp"],
                        "text": item["text"],
                        "confidence": item["confidence"],
                    }
                    for item in bundle["ocr"]
                ],
                "entities": [entity["name"] for entity in bundle["entities"]],
                "frames": [
                    {
                        "observation_id": item["id"],
                        "timestamp": item.get("timestamp"),
                    }
                    for item in (bundle["frames"] + bundle.get("images", []))[:3]
                ],
            }
        )

    return {
        "answer": payload["answer"],
        "confidence": payload["confidence"],
        "used_modalities": payload["used_modalities"],
        "citations": payload["citations"],
        "error": payload.get("error"),
        "evidence": evidence,
    }


@app.get("/api/media/observations/{observation_id}")
def api_observation_media(observation_id: str) -> FileResponse:
    initialize_database(DATABASE_PATH)
    observation = get_observation(observation_id, DATABASE_PATH)
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found.")
    if observation.modality not in {Modality.FRAME, Modality.IMAGE}:
        raise HTTPException(status_code=400, detail="Observation is not image media.")

    media_path = Path(observation.content).resolve()
    data_root = DATA_DIR.resolve()
    try:
        media_path.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Media path is outside the data directory.") from exc
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return FileResponse(media_path)


@app.get("/api/sources/{source_id}/events")
def api_source_events(source_id: str) -> list[dict[str, Any]]:
    initialize_database(DATABASE_PATH)
    source = _find_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return [
        {
            "id": event.id,
            "title": event.title,
            "summary": event.summary,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "confidence": event.confidence,
            "modalities": _modalities_for_event(event.id),
            "entities": event.entities,
        }
        for event in list_events_for_source(source_id, DATABASE_PATH)
    ]
