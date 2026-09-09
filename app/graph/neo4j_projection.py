from __future__ import annotations

import argparse
from typing import Any, Protocol

from app.config import DATABASE_PATH, NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from app.graph.neo4j_client import Neo4jGraphClient
from app.models import Entity, EvidenceEdge, Observation, SemanticEvent, Source
from app.storage.database import (
    get_entities_for_event,
    get_source,
    initialize_database,
    list_edges,
    list_events_for_source,
    list_observations_for_source,
)


class CypherWriter(Protocol):
    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (node:Source) REQUIRE node.id IS UNIQUE",
    "CREATE CONSTRAINT observation_id_unique IF NOT EXISTS FOR (node:Observation) REQUIRE node.id IS UNIQUE",
    "CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (node:Event) REQUIRE node.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (node:Entity) REQUIRE node.id IS UNIQUE",
)


def _source_properties(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "filename": source.filename,
        "source_type": source.source_type.value,
        "path": source.path,
        "duration": source.duration,
        "status": source.status.value,
        "metadata": source.metadata,
        "created_at": source.created_at.isoformat(),
    }


def _observation_properties(observation: Observation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "modality": observation.modality.value,
        "content": observation.content,
        "source_id": observation.source_id,
        "source_path": observation.source_path,
        "start_time": observation.start_time,
        "end_time": observation.end_time,
        "timestamp": observation.timestamp,
        "confidence": observation.confidence,
        "metadata": observation.metadata,
        "created_at": observation.created_at.isoformat(),
    }


def _event_properties(event: SemanticEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "source_id": event.source_id,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "entities": event.entities,
        "confidence": event.confidence,
        "created_at": event.created_at.isoformat(),
    }


def _entity_properties(entity: Entity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "name": entity.name,
        "normalized_name": entity.normalized_name,
        "entity_type": entity.entity_type,
        "confidence": entity.confidence,
        "metadata": entity.metadata,
        "created_at": entity.created_at.isoformat(),
    }


def _edge_properties(edge: EvidenceEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relation": edge.relation,
        "confidence": edge.confidence,
        "method": edge.method.value,
        "evidence_observation_ids": edge.evidence_observation_ids,
        "metadata": edge.metadata,
        "created_at": edge.created_at.isoformat(),
    }


def ensure_graph_schema(client: CypherWriter) -> None:
    """Create node identity constraints required for idempotent projections."""
    for query in CONSTRAINT_QUERIES:
        client.execute_write(query)


def project_source(source_id: str, client: CypherWriter, db_path=DATABASE_PATH) -> dict[str, int | str]:
    """Project one source's SQLite evidence graph into Neo4j.

    SQLite remains the authoritative store. Every write uses `MERGE`, making the
    operation safe to repeat after ingestion retries or application restarts.
    """
    initialize_database(db_path)
    source = get_source(source_id, db_path)
    if source is None:
        raise ValueError(f"Source not found: {source_id}")

    observations = list_observations_for_source(source_id, db_path)
    events = list_events_for_source(source_id, db_path)
    event_observation_ids: list[dict[str, str]] = []
    event_entities: list[dict[str, Any]] = []
    entities_by_id: dict[str, Entity] = {}

    from app.storage.database import get_event_observations

    for event in events:
        for observation in get_event_observations(event.id, db_path):
            event_observation_ids.append({"event_id": event.id, "observation_id": observation.id})
        for entity in get_entities_for_event(event.id, db_path):
            entities_by_id[entity.id] = entity
            event_entities.append({"event_id": event.id, "entity_id": entity.id})

    node_ids = {source.id}
    node_ids.update(observation.id for observation in observations)
    node_ids.update(event.id for event in events)
    node_ids.update(entities_by_id)
    edges = [
        edge
        for edge in list_edges(db_path)
        if edge.source_node_id in node_ids and edge.target_node_id in node_ids
    ]

    ensure_graph_schema(client)
    client.execute_write(
        "UNWIND $rows AS row MERGE (node:Source {id: row.id}) SET node += row",
        {"rows": [_source_properties(source)]},
    )
    client.execute_write(
        "UNWIND $rows AS row MERGE (node:Observation {id: row.id}) SET node += row",
        {"rows": [_observation_properties(observation) for observation in observations]},
    )
    client.execute_write(
        "UNWIND $rows AS row MERGE (node:Event {id: row.id}) SET node += row",
        {"rows": [_event_properties(event) for event in events]},
    )
    client.execute_write(
        "UNWIND $rows AS row MERGE (node:Entity {id: row.id}) SET node += row",
        {"rows": [_entity_properties(entity) for entity in entities_by_id.values()]},
    )
    client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (source:Source {id: $source_id})
        MATCH (observation:Observation {id: row.id})
        MERGE (source)-[:HAS_OBSERVATION]->(observation)
        """,
        {"source_id": source.id, "rows": [{"id": observation.id} for observation in observations]},
    )
    client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (source:Source {id: $source_id})
        MATCH (event:Event {id: row.id})
        MERGE (source)-[:HAS_EVENT]->(event)
        """,
        {"source_id": source.id, "rows": [{"id": event.id} for event in events]},
    )
    client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (event:Event {id: row.event_id})
        MATCH (observation:Observation {id: row.observation_id})
        MERGE (event)-[:HAS_OBSERVATION]->(observation)
        """,
        {"rows": event_observation_ids},
    )
    client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (event:Event {id: row.event_id})
        MATCH (entity:Entity {id: row.entity_id})
        MERGE (event)-[:INVOLVES]->(entity)
        """,
        {"rows": event_entities},
    )
    client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (source {id: row.source_node_id})
        MATCH (target {id: row.target_node_id})
        MERGE (source)-[edge:EVIDENCE {id: row.id}]->(target)
        SET edge += row
        """,
        {"rows": [_edge_properties(edge) for edge in edges]},
    )

    return {
        "source_id": source_id,
        "sources_projected": 1,
        "observations_projected": len(observations),
        "events_projected": len(events),
        "entities_projected": len(entities_by_id),
        "evidence_edges_projected": len(edges),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Project one source's evidence graph from SQLite into Neo4j.")
    parser.add_argument("source_id")
    args = parser.parse_args()

    client = Neo4jGraphClient(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    try:
        client.verify_connectivity()
        print(project_source(args.source_id, client))
    finally:
        client.close()


if __name__ == "__main__":
    main()
