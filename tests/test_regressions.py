"""Regression tests for bugs found during the local functional check."""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.generation.answer import (
    GENERATION_FAILED_ANSWER,
    INSUFFICIENT_EVIDENCE_ANSWER,
    answer_question,
    calculate_confidence,
)
from app.graph.neo4j_projection import project_source
from app.models import Modality, Observation, SemanticEvent, Source, SourceStatus, SourceType
from app.semantic.gemini_client import GeminiClient
from app.storage.database import (
    clear_source_data,
    get_source,
    initialize_database,
    insert_event,
    insert_observation,
    insert_source,
    link_event_observation,
    list_events_for_source,
    list_observations_for_source,
    update_source_status,
)


def _source(db_path: Path, source_type: SourceType = SourceType.IMAGE) -> Source:
    initialize_database(db_path)
    return insert_source(
        Source(
            id="source-1",
            filename="slide.png",
            source_type=source_type,
            path=str(db_path.parent / "slide.png"),
            status=SourceStatus.UPLOADED,
        ),
        db_path,
    )


def _bundle(**overrides: list[dict[str, Any]]) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "event": {"id": "event-1", "title": "t", "summary": "s", "start_time": None, "end_time": None, "confidence": 0.65},
        "transcripts": [],
        "ocr": [],
        "frames": [],
        "images": [],
        "documents": [],
        "entities": [],
        "relationships": [],
    }
    bundle.update(overrides)
    return bundle


def _retrieval(score: float, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "query": "q",
        "results": [
            {
                "rank": 1,
                "score": score,
                "event": {"id": "event-1", "title": "t", "summary": "s"},
                "retrieval_path": {"type": "vector"},
                "evidence_bundle": bundle or _bundle(documents=[{"id": "d", "text": "page text", "confidence": 1.0, "metadata": {"page": 1}}]),
            }
        ],
        "graph": {"enabled": False, "status": "skipped"},
    }


class FakeClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls = 0

    def generate_json(self, prompt: str) -> str:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


# --- source status / reprocessing -------------------------------------------------


def test_successful_status_clears_previous_error(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    source = _source(db_path)
    update_source_status(source.id, SourceStatus.FAILED, db_path, metadata={"error": "boom"})
    assert get_source(source.id, db_path).metadata["error"] == "boom"

    update_source_status(source.id, SourceStatus.READY, db_path)

    assert "error" not in get_source(source.id, db_path).metadata


def test_clear_source_data_keeps_source_row(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    source = _source(db_path)
    observation = insert_observation(
        Observation(modality=Modality.OCR, content="text", source_id=source.id, source_path=source.path), db_path
    )
    event = insert_event(SemanticEvent(title="e", summary="s", source_id=source.id), db_path)
    link_event_observation(event.id, observation.id, db_path)

    clear_source_data(source.id, db_path)

    assert get_source(source.id, db_path) is not None
    assert list_observations_for_source(source.id, db_path) == []
    assert list_events_for_source(source.id, db_path) == []


def test_reprocessing_an_image_does_not_duplicate_events(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    source = _source(db_path)
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)

    def fake_ingest_image(path, db_path, source_id=None):
        observation = insert_observation(
            Observation(modality=Modality.IMAGE, content=str(path), source_id=source_id, source_path=str(path)), db_path
        )
        event = insert_event(SemanticEvent(title="Image", summary="s", source_id=source_id), db_path)
        link_event_observation(event.id, observation.id, db_path)
        return {"image_observations": 1, "ocr_observations": 0, "events_created": 1}

    monkeypatch.setattr(main, "ingest_image", fake_ingest_image)
    monkeypatch.setattr(main, "enrich_source", lambda *_a, **_k: {"events_enriched": 1})
    monkeypatch.setattr(main, "build_index", lambda *_a, **_k: {"events_indexed": 1})
    monkeypatch.setattr(main, "sync_source_if_configured", lambda *_a, **_k: {"enabled": False, "status": "skipped"})

    client = TestClient(main.app)
    for _ in range(3):
        assert client.post(f"/api/sources/{source.id}/process").json()["status"] == "ready"

    assert len(list_events_for_source(source.id, db_path)) == 1
    assert len(list_observations_for_source(source.id, db_path)) == 1


# --- query API payload ------------------------------------------------------------------


def test_query_api_returns_pdf_text_retrieval_path_and_graph_status(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    source = _source(db_path, SourceType.PDF)
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    retrieval = _retrieval(0.7)
    monkeypatch.setattr(
        main,
        "answer_question",
        lambda source_id, question: {
            "answer": "a",
            "confidence": 0.5,
            "used_modalities": ["document"],
            "citations": [],
            "error": None,
            "retrieval": retrieval,
        },
    )

    body = TestClient(main.app).post("/api/query", json={"source_id": source.id, "question": "q"}).json()

    assert body["evidence"][0]["documents"] == [{"page": 1, "text": "page text"}]
    assert body["evidence"][0]["retrieval_path"] == {"type": "vector"}
    assert body["graph"] == {"enabled": False, "status": "skipped"}


# --- answer generation --------------------------------------------------------------------


def test_low_retrieval_score_short_circuits_without_calling_llm(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *a, **k: _retrieval(0.05))
    client = FakeClient('{"answer": "made up", "citations": [{"event_id": "event-1"}]}')

    result = answer_question("source-1", "unrelated?", client=client)

    assert client.calls == 0
    assert result["answer"] == INSUFFICIENT_EVIDENCE_ANSWER
    assert result["confidence"] == 0.0
    assert result["retrieval"]["results"]  # evidence is still returned for display


def test_answer_without_citations_has_zero_confidence(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *a, **k: _retrieval(0.7))

    result = answer_question("source-1", "q", client=FakeClient('{"answer": "Not in the evidence.", "citations": []}'))

    assert result["confidence"] == 0.0


def test_generation_failure_is_not_reported_as_missing_evidence(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *a, **k: _retrieval(0.7))

    result = answer_question("source-1", "q", client=FakeClient(RuntimeError("503")))

    assert result["answer"] == GENERATION_FAILED_ANSWER
    assert result["answer"] != INSUFFICIENT_EVIDENCE_ANSWER
    assert "Answer generation failed" in result["error"]


def test_pdf_and_image_evidence_count_towards_confidence() -> None:
    document = {"id": "d", "text": "t", "confidence": 1.0, "metadata": {}}
    pdf = calculate_confidence(_retrieval(0.67, _bundle(documents=[document])))
    empty = calculate_confidence(_retrieval(0.67, _bundle()))
    image = calculate_confidence(
        _retrieval(
            0.61,
            _bundle(
                images=[{"id": "i", "path": "p", "confidence": 1.0, "metadata": {}}],
                ocr=[{"id": "o", "timestamp": None, "text": "t", "confidence": 0.8, "metadata": {}}],
            ),
        )
    )

    assert pdf > empty + 0.15  # full modality credit for a document-only source
    assert image > 0.5


# --- Gemini client -------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [503, 500])
def test_gemini_retries_transient_server_errors(monkeypatch, status_code: int) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.semantic.gemini_client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(request.full_url, status_code, "busy", hdrs=None, fp=io.BytesIO(b"{}"))
        return Response(b'{"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert GeminiClient().generate_json("prompt") == "{}"
    assert calls["n"] == 2


# --- Neo4j projection ------------------------------------------------------------------------


def test_projection_prunes_nodes_from_an_earlier_run(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    source = _source(db_path)
    observation = insert_observation(
        Observation(modality=Modality.IMAGE, content="x", source_id=source.id, source_path=source.path), db_path
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    class Writer:
        def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            calls.append((query, parameters or {}))
            return []

    project_source(source.id, Writer(), db_path)

    prune = next(parameters for query, parameters in calls if "DETACH DELETE" in query)
    assert prune["source_id"] == source.id
    assert prune["keep_ids"] == [observation.id]
