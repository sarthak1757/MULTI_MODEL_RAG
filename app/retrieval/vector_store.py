from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from app.config import DATABASE_PATH, INDEXES_DIR
from app.models import Modality, Observation, SemanticEvent
from app.retrieval import embeddings
from app.storage.database import (
    get_event_observations,
    initialize_database,
    list_events_for_source,
)

INDEX_FILE = "events.faiss"
MAPPING_FILE = "event_mapping.json"


def event_search_document(event: SemanticEvent, observations: list[Observation]) -> str:
    transcripts = [
        observation.content
        for observation in observations
        if observation.modality == Modality.TRANSCRIPT
    ]
    ocr = [
        observation.content
        for observation in observations
        if observation.modality == Modality.OCR
    ]
    documents = [
        observation.content
        for observation in observations
        if observation.modality == Modality.DOCUMENT
    ]
    return "\n".join(
        [
            f"Title: {event.title}",
            f"Summary: {event.summary}",
            f"Entities: {', '.join(event.entities)}",
            f"Transcript: {' '.join(transcripts)}",
            f"OCR: {' '.join(ocr)}",
            f"Document: {' '.join(documents)}",
        ]
    ).strip()


def _source_index_dir(source_id: str, index_root: Path = INDEXES_DIR) -> Path:
    return index_root / source_id


def _load_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "faiss-cpu is required for vector search. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc
    return faiss


def build_index(
    source_id: str,
    db_path: Path = DATABASE_PATH,
    index_root: Path = INDEXES_DIR,
) -> dict[str, Any]:
    initialize_database(db_path)
    events = list_events_for_source(source_id, db_path)
    if not events:
        raise ValueError(f"No SemanticEvents found for source_id: {source_id}")

    documents = [
        event_search_document(event, get_event_observations(event.id, db_path))
        for event in events
    ]
    vectors = embeddings.embed_events(documents)
    if vectors.size == 0:
        raise ValueError(f"No event documents could be embedded for source_id: {source_id}")

    faiss = _load_faiss()
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.asarray(vectors, dtype="float32"))

    index_dir = _source_index_dir(source_id, index_root)
    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / INDEX_FILE))
    mapping = [{"row": row, "event_id": event.id} for row, event in enumerate(events)]
    (index_dir / MAPPING_FILE).write_text(json.dumps(mapping, indent=2), encoding="utf-8")

    return {
        "source_id": source_id,
        "events_indexed": len(events),
        "index_path": str(index_dir / INDEX_FILE),
        "mapping_path": str(index_dir / MAPPING_FILE),
    }


def _read_mapping(index_dir: Path) -> list[dict[str, Any]]:
    mapping_path = index_dir / MAPPING_FILE
    if not mapping_path.exists():
        raise FileNotFoundError(f"Missing event mapping: {mapping_path}")
    return json.loads(mapping_path.read_text(encoding="utf-8"))


def search(
    source_id: str,
    query: str,
    top_k: int = 3,
    db_path: Path = DATABASE_PATH,
    index_root: Path = INDEXES_DIR,
) -> list[dict[str, Any]]:
    index_dir = _source_index_dir(source_id, index_root)
    index_path = index_dir / INDEX_FILE
    if not index_path.exists():
        raise FileNotFoundError(
            f"Missing FAISS index for source_id {source_id}. Build it with: "
            f"python -m app.retrieval.vector_store build {source_id}"
        )

    faiss = _load_faiss()
    index = faiss.read_index(str(index_path))
    mapping = _read_mapping(index_dir)
    if not mapping:
        return []

    query_vector = embeddings.embed_query(query).reshape(1, -1).astype("float32")
    scores, rows = index.search(query_vector, min(top_k, len(mapping)))
    events_by_id = {event.id: event for event in list_events_for_source(source_id, db_path)}

    results: list[dict[str, Any]] = []
    for score, row in zip(scores[0], rows[0]):
        if row < 0 or row >= len(mapping):
            continue
        event_id = mapping[int(row)]["event_id"]
        event = events_by_id.get(event_id)
        if event is None:
            continue
        results.append(
            {
                "event_id": event.id,
                "score": float(score),
                "title": event.title,
                "summary": event.summary,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/search local FAISS event indexes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Build an event FAISS index for a source.")
    build_parser.add_argument("source_id")
    args = parser.parse_args()

    if args.command == "build":
        print(json.dumps(build_index(args.source_id), indent=2))


if __name__ == "__main__":
    main()
