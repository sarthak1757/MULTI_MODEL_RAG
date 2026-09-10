from __future__ import annotations

from typing import Any, Protocol


class CypherReader(Protocol):
    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


RELATED_EVENTS_QUERY = """
MATCH (seed:Event)
WHERE seed.id IN $seed_event_ids AND seed.source_id = $source_id
MATCH (seed)-[:INVOLVES]->(entity:Entity)<-[:INVOLVES]-(related:Event)
WHERE related.source_id = $source_id AND related.id <> seed.id
RETURN seed.id AS seed_event_id,
entity { .id, .name, .normalized_name, .entity_type } AS entity,
related { .id, .title, .summary, .start_time, .end_time, .confidence } AS related_event
ORDER BY seed_event_id, related_event.start_time, related_event.id
"""


def expand_related_events(
    source_id: str,
    seed_event_ids: list[str],
    client: CypherReader,
    related_events_per_seed: int = 2,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Find same-source events connected to vector-search seeds through entities."""
    if not seed_event_ids or related_events_per_seed < 1:
        return {}

    contexts: dict[str, dict[str, Any]] = {}
    for row in client.execute_read(
        RELATED_EVENTS_QUERY,
        {"source_id": source_id, "seed_event_ids": seed_event_ids},
    ):
        seed_event_id = row.get("seed_event_id")
        entity = row.get("entity")
        related_event = row.get("related_event")
        if not seed_event_id or not entity or not related_event:
            continue

        context = contexts.setdefault(seed_event_id, {"entities": {}, "related_events": {}})
        context["entities"][entity["id"]] = entity
        related = context["related_events"].setdefault(
            related_event["id"],
            {**related_event, "shared_entities": {}},
        )
        related["shared_entities"][entity["id"]] = entity["name"]

    normalized: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for seed_event_id, context in contexts.items():
        related_events = []
        for related_event in context["related_events"].values():
            related_events.append(
                {
                    key: value
                    for key, value in related_event.items()
                    if key != "shared_entities"
                }
                | {"shared_entities": sorted(related_event["shared_entities"].values())}
            )
        normalized[seed_event_id] = {
            "entities": list(context["entities"].values()),
            "related_events": related_events[:related_events_per_seed],
        }
    return normalized
