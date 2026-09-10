from __future__ import annotations

from typing import Any

from app.graph.rag import RELATED_EVENTS_QUERY, expand_related_events


class FakeCypherReader:
    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        assert query == RELATED_EVENTS_QUERY
        assert parameters == {"source_id": "source-1", "seed_event_ids": ["event-1"]}
        return [
            {
                "seed_event_id": "event-1",
                "entity": {"id": "entity-redis", "name": "Redis", "normalized_name": "redis"},
                "related_event": {"id": "event-2", "title": "Redis operations", "summary": "Operations advice."},
            },
            {
                "seed_event_id": "event-1",
                "entity": {"id": "entity-database", "name": "Database", "normalized_name": "database"},
                "related_event": {"id": "event-2", "title": "Redis operations", "summary": "Operations advice."},
            },
        ]


def test_expand_related_events_groups_results_by_seed_and_shared_entity() -> None:
    contexts = expand_related_events("source-1", ["event-1"], FakeCypherReader())

    assert {entity["name"] for entity in contexts["event-1"]["entities"]} == {"Redis", "Database"}
    related_event = contexts["event-1"]["related_events"][0]
    assert related_event["id"] == "event-2"
    assert related_event["shared_entities"] == ["Database", "Redis"]


def test_expand_related_events_avoids_a_database_query_without_seeds() -> None:
    class FailingReader:
        def execute_read(self, *_args, **_kwargs):
            raise AssertionError("No query should run")

    assert expand_related_events("source-1", [], FailingReader()) == {}
