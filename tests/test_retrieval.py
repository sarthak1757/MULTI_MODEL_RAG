from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.models import EdgeMethod, Entity, EvidenceEdge, Modality, Observation, SemanticEvent
from app.retrieval.evidence_bundle import build_evidence_bundle
from app.retrieval.hybrid import retrieve
from app.retrieval.vector_store import event_search_document
from app.storage.database import (
    initialize_database,
    insert_edge,
    insert_entity,
    insert_event,
    insert_observation,
    link_entity_to_event,
    link_event_observations,
)


class FakeIndex:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.vectors = np.zeros((0, dimension), dtype="float32")

    def add(self, vectors: np.ndarray) -> None:
        self.vectors = np.asarray(vectors, dtype="float32")

    def search(self, query: np.ndarray, top_k: int):
        scores = query @ self.vectors.T
        order = np.argsort(-scores[0])[:top_k]
        return scores[:, order], order.reshape(1, -1).astype("int64")


class FakeFaiss:
    IndexFlatIP = FakeIndex
    indexes: dict[str, FakeIndex] = {}

    @classmethod
    def write_index(cls, index: FakeIndex, path: str) -> None:
        cls.indexes[path] = index
        Path(path).write_text("fake index", encoding="utf-8")

    @classmethod
    def read_index(cls, path: str) -> FakeIndex:
        return cls.indexes[path]


def fake_embedding_for_text(text: str) -> np.ndarray:
    lower = text.lower()
    if "redis" in lower:
        return np.array([1.0, 0.0], dtype="float32")
    if "english" in lower:
        return np.array([0.0, 1.0], dtype="float32")
    return np.array([0.7, 0.7], dtype="float32") / np.sqrt(0.98)


def fake_embed_events(documents) -> np.ndarray:
    return np.vstack([fake_embedding_for_text(document) for document in documents]).astype("float32")


def fake_embed_query(query: str) -> np.ndarray:
    return fake_embedding_for_text(query)


def patch_vector_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.retrieval.vector_store._load_faiss", lambda: FakeFaiss)
    monkeypatch.setattr("app.retrieval.vector_store.embeddings.embed_events", fake_embed_events)
    monkeypatch.setattr("app.retrieval.vector_store.embeddings.embed_query", fake_embed_query)


def make_retrieval_fixture(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    source_id = "source-1"
    initialize_database(db_path)

    redis_event = insert_event(
        SemanticEvent(
            title="Redis Caching",
            summary="Redis reduces load on PostgreSQL.",
            source_id=source_id,
            start_time=10.0,
            end_time=15.0,
            entities=["Redis", "PostgreSQL"],
            confidence=0.9,
        ),
        db_path,
    )
    english_event = insert_event(
        SemanticEvent(
            title="English For Global Problems",
            summary="English helps people discuss global problems.",
            source_id=source_id,
            start_time=20.0,
            end_time=25.0,
            entities=["English"],
            confidence=0.8,
        ),
        db_path,
    )

    transcript = insert_observation(
        Observation(
            modality=Modality.TRANSCRIPT,
            content="Redis reduces load on PostgreSQL.",
            source_id=source_id,
            source_path="data/uploads/test.mp4",
            start_time=10.0,
            end_time=15.0,
        ),
        db_path,
    )
    frame = insert_observation(
        Observation(
            modality=Modality.FRAME,
            content="data/frames/source-1/frame_10.jpg",
            source_id=source_id,
            source_path="data/uploads/test.mp4",
            timestamp=10.0,
        ),
        db_path,
    )
    ocr = insert_observation(
        Observation(
            modality=Modality.OCR,
            content="Redis",
            source_id=source_id,
            source_path="data/uploads/test.mp4",
            timestamp=10.0,
            metadata={"parent_frame_id": frame.id},
        ),
        db_path,
    )
    link_event_observations(redis_event.id, [transcript.id, frame.id, ocr.id], db_path)

    redis = insert_entity(
        Entity(name="Redis", normalized_name="redis", entity_type="technology", confidence=0.95),
        db_path,
    )
    postgres = insert_entity(
        Entity(name="PostgreSQL", normalized_name="postgresql", entity_type="technology", confidence=0.9),
        db_path,
    )
    link_entity_to_event(redis_event.id, redis.id, 0.95, db_path)
    link_entity_to_event(redis_event.id, postgres.id, 0.9, db_path)
    insert_edge(
        EvidenceEdge(
            source_node_id=redis_event.id,
            target_node_id=transcript.id,
            relation="HAS_TRANSCRIPT",
            confidence=1.0,
            method=EdgeMethod.PROVENANCE,
            evidence_observation_ids=[transcript.id],
        ),
        db_path,
    )
    insert_edge(
        EvidenceEdge(
            source_node_id=redis.id,
            target_node_id=postgres.id,
            relation="RELATED_TO",
            confidence=0.85,
            method=EdgeMethod.LLM,
            evidence_observation_ids=[transcript.id],
        ),
        db_path,
    )

    return SimpleNamespace(
        db_path=db_path,
        source_id=source_id,
        redis_event=redis_event,
        english_event=english_event,
        transcript=transcript,
        frame=frame,
        ocr=ocr,
        redis=redis,
        postgres=postgres,
    )


def test_search_document_construction(tmp_path: Path) -> None:
    fixture = make_retrieval_fixture(tmp_path)
    document = event_search_document(
        fixture.redis_event,
        [fixture.transcript, fixture.frame, fixture.ocr],
    )

    assert "Title: Redis Caching" in document
    assert "Summary: Redis reduces load on PostgreSQL." in document
    assert "Entities: Redis, PostgreSQL" in document
    assert "Transcript: Redis reduces load on PostgreSQL." in document
    assert "OCR: Redis" in document
    assert fixture.frame.content not in document


def test_index_build_mapping_and_top_k_retrieval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_retrieval_fixture(tmp_path)
    patch_vector_dependencies(monkeypatch)

    from app.retrieval.vector_store import build_index, search

    summary = build_index(fixture.source_id, db_path=fixture.db_path, index_root=tmp_path / "indexes")
    results = search(
        fixture.source_id,
        "How does Redis reduce database load?",
        top_k=1,
        db_path=fixture.db_path,
        index_root=tmp_path / "indexes",
    )
    mapping = json.loads(Path(summary["mapping_path"]).read_text(encoding="utf-8"))

    assert summary["events_indexed"] == 2
    assert mapping[0]["event_id"] == fixture.redis_event.id
    assert results[0]["event_id"] == fixture.redis_event.id


def test_evidence_bundle_construction(tmp_path: Path) -> None:
    fixture = make_retrieval_fixture(tmp_path)

    bundle = build_evidence_bundle(fixture.redis_event.id, fixture.db_path)

    assert bundle["event"]["id"] == fixture.redis_event.id
    assert bundle["transcripts"][0]["id"] == fixture.transcript.id
    assert bundle["frames"][0]["path"] == fixture.frame.content
    assert bundle["ocr"][0]["text"] == fixture.ocr.content
    assert {entity["name"] for entity in bundle["entities"]} == {"Redis", "PostgreSQL"}
    assert {relationship["relation"] for relationship in bundle["relationships"]} >= {
        "HAS_TRANSCRIPT",
        "RELATED_TO",
    }


def test_hybrid_retrieve_returns_evidence_bundles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_retrieval_fixture(tmp_path)
    patch_vector_dependencies(monkeypatch)

    from app.retrieval.vector_store import build_index

    build_index(fixture.source_id, db_path=fixture.db_path, index_root=tmp_path / "indexes")
    payload = retrieve(
        fixture.source_id,
        "Redis database load",
        top_k=1,
        db_path=fixture.db_path,
        index_root=tmp_path / "indexes",
    )

    assert payload["query"] == "Redis database load"
    assert payload["results"][0]["rank"] == 1
    assert payload["results"][0]["event"]["id"] == fixture.redis_event.id
    assert payload["results"][0]["evidence_bundle"]["transcripts"][0]["id"] == fixture.transcript.id
    assert payload["graph"] == {"enabled": False, "status": "skipped"}


def test_hybrid_retrieve_adds_graph_connected_events_with_direct_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_retrieval_fixture(tmp_path)
    patch_vector_dependencies(monkeypatch)
    monkeypatch.setattr(
        "app.retrieval.hybrid.get_graph_expansion_if_configured",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "status": "ready",
            "contexts": {
                fixture.redis_event.id: {
                    "entities": [{"id": fixture.redis.id, "name": "Redis"}],
                    "related_events": [
                        {
                            "id": fixture.english_event.id,
                            "shared_entities": ["Redis"],
                        }
                    ],
                }
            },
        },
    )

    from app.retrieval.vector_store import build_index

    build_index(fixture.source_id, db_path=fixture.db_path, index_root=tmp_path / "indexes")
    payload = retrieve(
        fixture.source_id,
        "Redis database load",
        top_k=1,
        db_path=fixture.db_path,
        index_root=tmp_path / "indexes",
    )

    assert [result["event"]["id"] for result in payload["results"]] == [
        fixture.redis_event.id,
        fixture.english_event.id,
    ]
    assert payload["results"][1]["retrieval_path"] == {
        "type": "graph_expansion",
        "shared_entities": ["Redis"],
    }
    assert payload["results"][1]["evidence_bundle"]["event"]["id"] == fixture.english_event.id


def test_empty_and_missing_source_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_vector_dependencies(monkeypatch)
    initialize_database(tmp_path / "test.sqlite3")

    from app.retrieval.vector_store import build_index, search

    with pytest.raises(ValueError, match="No SemanticEvents"):
        build_index("missing-source", db_path=tmp_path / "test.sqlite3", index_root=tmp_path / "indexes")

    with pytest.raises(FileNotFoundError, match="Missing FAISS index"):
        search(
            "missing-source",
            "question",
            db_path=tmp_path / "test.sqlite3",
            index_root=tmp_path / "indexes",
        )
