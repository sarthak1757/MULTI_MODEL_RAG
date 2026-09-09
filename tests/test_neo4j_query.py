from __future__ import annotations

from typing import Any

from app.graph.query import EVIDENCE_EDGES_QUERY, EVENTS_QUERY, OBSERVATIONS_QUERY, SOURCE_QUERY, read_source_graph


class FakeCypherReader:
    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if query == SOURCE_QUERY:
            return [{"source": {"id": "source-1", "filename": "demo.mp4", "status": "ready"}}]
        if query == EVENTS_QUERY:
            return [
                {
                    "event": {"id": "event-1", "title": "Redis caching", "summary": "Caching lowers database load."},
                    "entities": [{"id": "entity-1", "name": "Redis", "normalized_name": "redis"}],
                }
            ]
        if query == OBSERVATIONS_QUERY:
            return [
                {
                    "event_id": "event-1",
                    "observations": [{"id": "observation-1", "modality": "transcript", "content": "Redis caches data."}],
                }
            ]
        if query == EVIDENCE_EDGES_QUERY:
            assert parameters == {"node_ids": ["source-1", "event-1", "entity-1", "observation-1"]}
            return [
                {
                    "source_node_id": "event-1",
                    "target_node_id": "observation-1",
                    "edge": {"id": "edge-1", "relation": "HAS_TRANSCRIPT", "method": "provenance"},
                }
            ]
        raise AssertionError(f"Unexpected query: {query}")


def test_read_source_graph_returns_labeled_nodes_and_relationships() -> None:
    graph = read_source_graph("source-1", FakeCypherReader())

    assert graph is not None
    assert graph["source"]["id"] == "source-1"
    assert {node["label"] for node in graph["nodes"]} == {"Source", "Event", "Entity", "Observation"}
    relations = {relationship["relation"] for relationship in graph["relationships"]}
    assert {"HAS_EVENT", "HAS_OBSERVATION", "INVOLVES", "HAS_TRANSCRIPT"}.issubset(relations)
    evidence = next(relationship for relationship in graph["relationships"] if relationship["id"] == "edge-1")
    assert evidence["properties"] == {"method": "provenance"}


def test_read_source_graph_returns_none_when_source_is_not_in_neo4j() -> None:
    class EmptyReader:
        def execute_read(self, query: str, parameters=None):
            assert query == SOURCE_QUERY
            return []

    assert read_source_graph("missing", EmptyReader()) is None
