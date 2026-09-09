from __future__ import annotations

from pathlib import Path

from app.graph import sync


def test_sync_skips_cleanly_when_neo4j_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(sync, "NEO4J_URI", "")
    monkeypatch.setattr(sync, "NEO4J_PASSWORD", "")

    summary = sync.sync_source_if_configured("source-1")

    assert summary == {"enabled": False, "status": "skipped"}


def test_sync_projects_source_when_neo4j_is_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setattr(sync, "NEO4J_PASSWORD", "local-password")
    calls: list[object] = []

    class FakeClient:
        configured = True

        def __init__(self, *args) -> None:
            calls.append(args)

        def verify_connectivity(self) -> None:
            calls.append("verified")

        def close(self) -> None:
            calls.append("closed")

    def fake_project_source(source_id, client, db_path):
        assert source_id == "source-1"
        assert isinstance(client, FakeClient)
        assert db_path == tmp_path / "test.sqlite3"
        return {"source_id": source_id, "events_projected": 2}

    monkeypatch.setattr(sync, "project_source", fake_project_source)

    summary = sync.sync_source_if_configured(
        "source-1",
        db_path=tmp_path / "test.sqlite3",
        client_factory=FakeClient,
    )

    assert summary == {
        "enabled": True,
        "status": "ready",
        "source_id": "source-1",
        "events_projected": 2,
    }
    assert calls[-2:] == ["verified", "closed"]


def test_sync_reports_graph_error_without_raising(monkeypatch) -> None:
    monkeypatch.setattr(sync, "NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setattr(sync, "NEO4J_PASSWORD", "local-password")

    class FailingClient:
        configured = True

        def __init__(self, *args) -> None:
            pass

        def verify_connectivity(self) -> None:
            raise RuntimeError("database is unavailable")

        def close(self) -> None:
            pass

    summary = sync.sync_source_if_configured("source-1", client_factory=FailingClient)

    assert summary == {"enabled": True, "status": "failed", "error": "database is unavailable"}
