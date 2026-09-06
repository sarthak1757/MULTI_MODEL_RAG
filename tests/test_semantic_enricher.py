from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from app.models import Modality, Observation, SemanticEvent
from app.semantic.enricher import enrich_source
from app.semantic.gemini_client import GeminiClient, MissingGeminiAPIKeyError
from app.storage.database import (
    get_entities_for_event,
    get_event,
    get_event_observations,
    initialize_database,
    insert_event,
    insert_observation,
    link_event_observations,
    list_edges,
)


class FakeGeminiClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def generate_json(self, prompt: str) -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def make_event_fixture(tmp_path: Path) -> tuple[Path, str, SemanticEvent, Observation, Observation]:
    db_path = tmp_path / "test.sqlite3"
    source_id = "source-1"
    initialize_database(db_path)

    transcript = insert_observation(
        Observation(
            modality=Modality.TRANSCRIPT,
            content="Redis reduces load on PostgreSQL.",
            source_id=source_id,
            source_path="data/uploads/test.mp4",
            start_time=10.0,
            end_time=14.0,
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
            metadata={"parent_frame_id": "frame-1"},
        ),
        db_path,
    )
    event = insert_event(
        SemanticEvent(
            title="Redis reduces load.",
            summary="Redis reduces load on PostgreSQL.",
            source_id=source_id,
            start_time=10.0,
            end_time=14.0,
            confidence=0.9,
        ),
        db_path,
    )
    link_event_observations(event.id, [transcript.id, ocr.id], db_path)
    return db_path, source_id, event, transcript, ocr


def response_payload(transcript_id: str, ocr_id: str, relationship_confidence: float = 0.85) -> str:
    return json.dumps(
        {
            "title": "Redis Caching Reduces Database Load",
            "summary": "The event discusses Redis reducing load on PostgreSQL.",
            "entities": [
                {
                    "name": "Redis",
                    "type": "technology",
                    "confidence": 0.95,
                    "evidence_observation_ids": [transcript_id, ocr_id],
                },
                {
                    "name": "PostgreSQL",
                    "type": "technology",
                    "confidence": 0.9,
                    "evidence_observation_ids": [transcript_id],
                },
            ],
            "relationships": [
                {
                    "source": "Redis",
                    "relation": "RELATED_TO",
                    "target": "PostgreSQL",
                    "confidence": relationship_confidence,
                    "evidence_observation_ids": [transcript_id],
                }
            ],
        }
    )


def test_semantic_enrichment_creates_entities_links_edges_and_updates_event(tmp_path: Path) -> None:
    db_path, source_id, event, transcript, ocr = make_event_fixture(tmp_path)
    client = FakeGeminiClient([response_payload(transcript.id, ocr.id)])

    summary = enrich_source(source_id, event_id=event.id, client=client, db_path=db_path)
    updated_event = get_event(event.id, db_path)
    entities = get_entities_for_event(event.id, db_path)
    edges = list_edges(db_path)

    assert summary["events_enriched"] == 1
    assert updated_event is not None
    assert updated_event.title == "Redis Caching Reduces Database Load"
    assert updated_event.summary == "The event discusses Redis reducing load on PostgreSQL."
    assert updated_event.entities == ["PostgreSQL", "Redis"]
    assert {entity.normalized_name for entity in entities} == {"redis", "postgresql"}
    assert len([edge for edge in edges if edge.method.value == "llm"]) == 1
    assert edges[-1].evidence_observation_ids == [transcript.id]


def test_low_confidence_relationship_is_ignored(tmp_path: Path) -> None:
    db_path, source_id, event, transcript, ocr = make_event_fixture(tmp_path)
    client = FakeGeminiClient([response_payload(transcript.id, ocr.id, relationship_confidence=0.4)])

    enrich_source(source_id, event_id=event.id, client=client, db_path=db_path)

    assert [edge for edge in list_edges(db_path) if edge.method.value == "llm"] == []


def test_missing_api_key_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(MissingGeminiAPIKeyError, match="GEMINI_API_KEY is missing"):
        GeminiClient()


def test_gemini_model_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    assert GeminiClient().model == "gemini-3.6-flash"

    monkeypatch.setenv("GEMINI_MODEL", "custom-model")

    assert GeminiClient().model == "custom-model"


def test_gemini_http_error_is_concise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = GeminiClient(max_rate_limit_retries=0)
    error_payload = json.dumps(
        {
            "error": {
                "message": "Model gemini-old is not found or is not supported for generateContent."
            }
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            hdrs=None,
            fp=FakeHTTPErrorBody(error_payload),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as error:
        client.generate_json("prompt")

    message = str(error.value)
    assert "HTTP 404" in message
    assert "gemini-3.6-flash" in message
    assert "Model gemini-old is not found" in message
    assert len(message) < 400


class FakeHTTPErrorBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass


def test_invalid_json_skips_event_without_update(tmp_path: Path) -> None:
    db_path, source_id, event, _transcript, _ocr = make_event_fixture(tmp_path)
    client = FakeGeminiClient(["not json", "still not json"])

    summary = enrich_source(source_id, event_id=event.id, client=client, db_path=db_path)
    unchanged_event = get_event(event.id, db_path)

    assert summary["events_enriched"] == 0
    assert len(summary["errors"]) == 1
    assert unchanged_event == event
    assert get_entities_for_event(event.id, db_path) == []
    assert list_edges(db_path) == []


def test_enrichment_does_not_change_event_membership(tmp_path: Path) -> None:
    db_path, source_id, event, transcript, ocr = make_event_fixture(tmp_path)
    client = FakeGeminiClient([response_payload(transcript.id, ocr.id)])

    before_ids = [observation.id for observation in get_event_observations(event.id, db_path)]
    enrich_source(source_id, event_id=event.id, client=client, db_path=db_path)
    after_ids = [observation.id for observation in get_event_observations(event.id, db_path)]

    assert after_ids == before_ids
