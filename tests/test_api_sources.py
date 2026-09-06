from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.models import Modality, Observation, SemanticEvent, Source, SourceStatus, SourceType
from app.storage.database import (
    get_observation,
    get_source,
    initialize_database,
    insert_event,
    insert_observation,
    insert_source,
    list_events_for_source,
    list_observations_for_source,
)


def test_expected_api_routes_are_registered() -> None:
    import app.main as main

    routes = {route.path for route in main.app.routes}

    assert "/api/health" in routes
    assert "/api/sources" in routes
    assert "/api/sources/{source_id}" in routes
    assert "/api/sources/{source_id}/events" in routes
    assert "/api/sources/upload" in routes
    assert "/api/sources/{source_id}/process" in routes
    assert "/api/query" in routes
    assert "/api/media/observations/{observation_id}" in routes


def test_existing_source_with_no_events_returns_empty_list(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    source = insert_source(
        Source(
            id="source-without-events",
            filename="empty.mp4",
            source_type=SourceType.VIDEO,
            path="data/uploads/empty.mp4",
            status=SourceStatus.UPLOADED,
        ),
        db_path,
    )
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)

    client = TestClient(main.app)

    source_response = client.get(f"/api/sources/{source.id}")
    events_response = client.get(f"/api/sources/{source.id}/events")

    assert source_response.status_code == 200
    assert events_response.status_code == 200
    assert events_response.json() == []


def test_query_route_uses_existing_answer_pipeline(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    source = insert_source(
        Source(
            id="ready-source",
            filename="ready.mp4",
            source_type=SourceType.VIDEO,
            path="data/uploads/ready.mp4",
            status=SourceStatus.READY,
        ),
        db_path,
    )
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    monkeypatch.setattr(
        main,
        "answer_question",
        lambda source_id, question: {
            "answer": f"Answer for {question}",
            "confidence": 0.7,
            "used_modalities": ["transcript"],
            "citations": [],
            "error": None,
            "retrieval": {
                "results": [
                    {
                        "score": 0.8,
                        "evidence_bundle": {
                            "event": {
                                "id": "event-1",
                                "title": "Event",
                                "start_time": 1.0,
                                "end_time": 2.0,
                            },
                            "transcripts": [{"content": "hello"}],
                            "ocr": [],
                            "entities": [],
                            "frames": [],
                            "images": [],
                        },
                    }
                ]
            },
        },
    )

    client = TestClient(main.app)
    response = client.post("/api/query", json={"source_id": source.id, "question": "test?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Answer for test?"
    assert response.json()["evidence"][0]["event_id"] == "event-1"


def test_missing_source_returns_404(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)

    client = TestClient(main.app)

    assert client.get("/api/sources/missing").status_code == 404


def test_delete_source_removes_database_records_and_media(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    data_root = tmp_path / "data"
    upload_root = data_root / "uploads"
    frame_root = data_root / "frames"
    index_root = data_root / "indexes"
    upload_root.mkdir(parents=True)
    frame_root.mkdir(parents=True)
    index_root.mkdir(parents=True)
    upload_path = upload_root / "delete-me.mp4"
    frame_path = frame_root / "frame.jpg"
    index_path = index_root / "source-to-delete" / "events.faiss"
    upload_path.write_bytes(b"video")
    frame_path.write_bytes(b"frame")
    index_path.parent.mkdir()
    index_path.write_text("fake index", encoding="utf-8")
    initialize_database(db_path)

    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    monkeypatch.setattr(main, "DATA_DIR", data_root)
    monkeypatch.setattr(main, "INDEXES_DIR", index_root)

    source = insert_source(
        Source(
            id="source-to-delete",
            filename="delete-me.mp4",
            source_type=SourceType.VIDEO,
            path=str(upload_path),
            status=SourceStatus.READY,
        ),
        db_path,
    )
    observation = insert_observation(
        Observation(
            id="frame-observation",
            modality=Modality.FRAME,
            content=str(frame_path),
            source_id=source.id,
            source_path=str(upload_path),
            timestamp=1.0,
        ),
        db_path,
    )
    insert_event(
        SemanticEvent(
            id="event-to-delete",
            title="Event",
            summary="Summary",
            source_id=source.id,
        ),
        db_path,
    )

    client = TestClient(main.app)
    response = client.delete(f"/api/sources/{source.id}")

    assert response.status_code == 204
    assert get_source(source.id, db_path) is None
    assert get_observation(observation.id, db_path) is None
    assert list_observations_for_source(source.id, db_path) == []
    assert list_events_for_source(source.id, db_path) == []
    assert not upload_path.exists()
    assert not frame_path.exists()
    assert not index_path.parent.exists()


def test_delete_missing_source_returns_404(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    monkeypatch.setattr(main, "DATABASE_PATH", db_path)

    client = TestClient(main.app)

    assert client.delete("/api/sources/missing").status_code == 404


def test_env_example_contains_only_gemini_placeholders() -> None:
    lines = Path(".env.example").read_text(encoding="utf-8").splitlines()

    assert lines == [
        "GEMINI_API_KEY=your_gemini_api_key_here",
        "GEMINI_MODEL=gemini-3.6-flash",
    ]


def test_upload_process_uses_one_canonical_source_id(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    index_root = tmp_path / "indexes"
    upload_root = tmp_path / "uploads"
    initialize_database(db_path)

    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    monkeypatch.setattr(main, "UPLOADS_DIR", upload_root)

    def fake_ingest_video(path, db_path, source_id=None, **_kwargs):
        assert source_id is not None
        insert_observation(
            Observation(
                modality=Modality.TRANSCRIPT,
                content="Transcript for uploaded video.",
                source_id=source_id,
                source_path=str(path),
                start_time=0.0,
                end_time=2.0,
            ),
            db_path,
        )
        return {"source_id": source_id, "transcript_segments": 1, "frames": 0, "ocr_observations": 0, "duration": 2.0}

    def fake_process_source(source_id, db_path):
        insert_event(
            SemanticEvent(
                title="Uploaded event",
                summary="Transcript for uploaded video.",
                source_id=source_id,
                start_time=0.0,
                end_time=2.0,
            ),
            db_path,
        )
        return {"events_created": 1, "temporal_edges": 0}

    def fake_enrich_source(source_id, db_path):
        return {"events_enriched": 1}

    def fake_build_index(source_id, db_path):
        index_dir = index_root / source_id
        index_dir.mkdir(parents=True)
        (index_dir / "events.faiss").write_text("fake", encoding="utf-8")
        return {"events_indexed": 1}

    monkeypatch.setattr(main, "ingest_video", fake_ingest_video)
    monkeypatch.setattr(main, "process_source", fake_process_source)
    monkeypatch.setattr(main, "enrich_source", fake_enrich_source)
    monkeypatch.setattr(main, "build_index", fake_build_index)

    client = TestClient(main.app)
    upload_response = client.post(
        "/api/sources/upload",
        files={"file": ("demo.mp4", b"fake video", "video/mp4")},
    )
    assert upload_response.status_code == 200
    source_id = upload_response.json()["source_id"]

    process_response = client.post(f"/api/sources/{source_id}/process")
    assert process_response.status_code == 200
    assert process_response.json()["status"] == "ready"

    assert get_source(source_id, db_path).status == SourceStatus.READY
    assert [observation.source_id for observation in list_observations_for_source(source_id, db_path)] == [source_id]
    assert [event.source_id for event in list_events_for_source(source_id, db_path)] == [source_id]
    assert (index_root / source_id / "events.faiss").exists()
    assert client.get(f"/api/sources/{source_id}").status_code == 200
    assert client.get(f"/api/sources/{source_id}/events").status_code == 200


def test_failed_source_does_not_corrupt_ready_source(tmp_path: Path, monkeypatch) -> None:
    import app.main as main

    db_path = tmp_path / "test.sqlite3"
    upload_root = tmp_path / "uploads"
    initialize_database(db_path)
    ready_source = insert_source(
        Source(
            id="ready-source",
            filename="test.mp4",
            source_type=SourceType.VIDEO,
            path="data/uploads/test.mp4",
            duration=12.0,
            status=SourceStatus.READY,
        ),
        db_path,
    )

    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    monkeypatch.setattr(main, "UPLOADS_DIR", upload_root)
    monkeypatch.setattr(main, "ingest_video", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("transcription failed")))

    client = TestClient(main.app)
    upload_response = client.post(
        "/api/sources/upload",
        files={"file": ("bad.mp4", b"fake video", "video/mp4")},
    )
    failed_id = upload_response.json()["source_id"]

    process_response = client.post(f"/api/sources/{failed_id}/process")

    assert process_response.status_code == 200
    assert process_response.json()["status"] == "failed"
    assert get_source(failed_id, db_path).status == SourceStatus.FAILED
    assert get_source(failed_id, db_path).metadata["error"] == "transcription failed"
    assert get_source(ready_source.id, db_path).status == SourceStatus.READY

    sources = client.get("/api/sources").json()
    statuses = {source["id"]: source["status"] for source in sources}
    assert statuses[ready_source.id] == "ready"
    assert statuses[failed_id] == "failed"
