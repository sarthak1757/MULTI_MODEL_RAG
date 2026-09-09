from __future__ import annotations

from typing import Any, Protocol


class CypherReader(Protocol):
    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


SOURCE_QUERY = """
MATCH (source:Source {id: $source_id})
RETURN source {
    .id, .filename, .source_type, .status, .duration, .created_at
} AS source
"""

EVENTS_QUERY = """
MATCH (source:Source {id: $source_id})-[:HAS_EVENT]->(event:Event)
OPTIONAL MATCH (event)-[:INVOLVES]->(entity:Entity)
RETURN event {
    .id, .title, .summary, .start_time, .end_time, .confidence
} AS event,
collect(entity {
    .id, .name, .normalized_name, .entity_type, .confidence
}) AS entities
ORDER BY event.start_time, event.id
"""

OBSERVATIONS_QUERY = """
MATCH (source:Source {id: $source_id})-[:HAS_EVENT]->(event:Event)
OPTIONAL MATCH (event)-[:HAS_OBSERVATION]->(observation:Observation)
RETURN event.id AS event_id,
collect(observation {
    .id, .modality, .content, .start_time, .end_time, .timestamp, .confidence
}) AS observations
ORDER BY event_id
"""

EVIDENCE_EDGES_QUERY = """
MATCH (source)-[edge:EVIDENCE]->(target)
WHERE source.id IN $node_ids AND target.id IN $node_ids
RETURN source.id AS source_node_id,
target.id AS target_node_id,
edge {
    .id, .relation, .confidence, .method, .evidence_observation_ids, .created_at
} AS edge
ORDER BY edge.created_at, edge.id
"""


def _add_node(nodes: dict[str, dict[str, Any]], label: str, properties: dict[str, Any] | None) -> None:
    if properties is None or not properties.get("id"):
        return
    nodes[properties["id"]] = {"id": properties["id"], "label": label, "properties": properties}


def _add_relationship(
    relationships: dict[str, dict[str, Any]],
    relationship_id: str,
    source_node_id: str,
    target_node_id: str,
    relation: str,
    properties: dict[str, Any] | None = None,
) -> None:
    relationships[relationship_id] = {
        "id": relationship_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relation": relation,
        "properties": properties or {},
    }


def read_source_graph(source_id: str, client: CypherReader) -> dict[str, Any] | None:
    """Return a frontend-friendly source subgraph from Neo4j."""
    source_rows = client.execute_read(SOURCE_QUERY, {"source_id": source_id})
    if not source_rows or source_rows[0].get("source") is None:
        return None

    nodes: dict[str, dict[str, Any]] = {}
    relationships: dict[str, dict[str, Any]] = {}
    source = source_rows[0]["source"]
    _add_node(nodes, "Source", source)

    for row in client.execute_read(EVENTS_QUERY, {"source_id": source_id}):
        event = row.get("event")
        _add_node(nodes, "Event", event)
        if event is None or not event.get("id"):
            continue
        _add_relationship(
            relationships,
            f"source-event:{source_id}:{event['id']}",
            source_id,
            event["id"],
            "HAS_EVENT",
        )
        for entity in row.get("entities", []):
            _add_node(nodes, "Entity", entity)
            if entity and entity.get("id"):
                _add_relationship(
                    relationships,
                    f"event-entity:{event['id']}:{entity['id']}",
                    event["id"],
                    entity["id"],
                    "INVOLVES",
                )

    for row in client.execute_read(OBSERVATIONS_QUERY, {"source_id": source_id}):
        event_id = row.get("event_id")
        for observation in row.get("observations", []):
            _add_node(nodes, "Observation", observation)
            if observation and observation.get("id"):
                _add_relationship(
                    relationships,
                    f"source-observation:{source_id}:{observation['id']}",
                    source_id,
                    observation["id"],
                    "HAS_OBSERVATION",
                )
                if event_id:
                    _add_relationship(
                        relationships,
                        f"event-observation:{event_id}:{observation['id']}",
                        event_id,
                        observation["id"],
                        "HAS_OBSERVATION",
                    )

    for row in client.execute_read(EVIDENCE_EDGES_QUERY, {"node_ids": list(nodes)}):
        edge = row.get("edge")
        if edge is None or not edge.get("id"):
            continue
        _add_relationship(
            relationships,
            edge["id"],
            row["source_node_id"],
            row["target_node_id"],
            edge["relation"],
            {
                key: value
                for key, value in edge.items()
                if key not in {"id", "relation"}
            },
        )

    return {
        "source": source,
        "nodes": list(nodes.values()),
        "relationships": list(relationships.values()),
    }
