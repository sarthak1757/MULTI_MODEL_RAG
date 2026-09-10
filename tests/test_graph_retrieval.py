from __future__ import annotations

from app.graph import graph_rag


def test_graph_expansion_skips_when_neo4j_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(graph_rag, "NEO4J_URI", "")
    monkeypatch.setattr(graph_rag, "NEO4J_PASSWORD", "")

    assert graph_rag.get_graph_expansion_if_configured("source-1", ["event-1"]) == {
        "enabled": False,
        "status": "skipped",
        "contexts": {},
    }


def test_graph_expansion_uses_connected_neo4j_client(monkeypatch) -> None:
    monkeypatch.setattr(graph_rag, "NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setattr(graph_rag, "NEO4J_PASSWORD", "local-password")
    monkeypatch.setattr(
        graph_rag,
        "expand_related_events",
        lambda source_id, event_ids, client, limit: {"event-1": {"entities": [], "related_events": []}},
    )

    class FakeClient:
        configured = True

        def __init__(self, *_args) -> None:
            self.closed = False

        def verify_connectivity(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    result = graph_rag.get_graph_expansion_if_configured("source-1", ["event-1"], client_factory=FakeClient)

    assert result == {
        "enabled": True,
        "status": "ready",
        "contexts": {"event-1": {"entities": [], "related_events": []}},
    }
