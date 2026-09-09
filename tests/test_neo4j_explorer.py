from __future__ import annotations

from app.graph import explorer


def test_explorer_skips_when_neo4j_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(explorer, "NEO4J_URI", "")
    monkeypatch.setattr(explorer, "NEO4J_PASSWORD", "")

    assert explorer.get_source_graph_if_configured("source-1") == {
        "enabled": False,
        "status": "skipped",
        "graph": None,
    }


def test_explorer_returns_not_synced_for_absent_projection(monkeypatch) -> None:
    monkeypatch.setattr(explorer, "NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setattr(explorer, "NEO4J_PASSWORD", "local-password")
    monkeypatch.setattr(explorer, "read_source_graph", lambda *_args: None)

    class FakeClient:
        configured = True

        def __init__(self, *_args) -> None:
            pass

        def verify_connectivity(self) -> None:
            pass

        def close(self) -> None:
            pass

    assert explorer.get_source_graph_if_configured("source-1", client_factory=FakeClient) == {
        "enabled": True,
        "status": "not_synced",
        "graph": None,
    }
