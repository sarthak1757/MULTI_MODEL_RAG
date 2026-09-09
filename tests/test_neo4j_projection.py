from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.graph.neo4j_projection import project_source
from app.models import EdgeMethod, Entity, EvidenceEdge, Modality, Observation, SemanticEvent, Source, SourceStatus, SourceType
from app.storage.database import (
    initialize_database,
    insert_edge,
    insert_entity,
    insert_event,
    insert_observation,
    insert_source,
    link_entity_to_event,
    link_event_observation,
)


class RecordingCypherWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append((query, parameters or {}))
        return []


def test_project_source_writes_nodes_and_evidence_relationships(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    source = insert_source(
        Source(
            id="source-1",
            filename="demo.mp4",
            source_type=SourceType.VIDEO,
            path="data/uploads/demo.mp4",
            status=SourceStatus.READY,
        ),
        db_path,
    )
    observation = insert_observation(
        Observation(
            id="observation-1",
            modality=Modality.TRANSCRIPT,
            content="Redis reduces database load.",
            source_id=source.id,
            source_path=source.path,
            start_time=10.0,
            end_time=12.0,
        ),
        db_path,
    )
    event = insert_event(
        SemanticEvent(
            id="event-1",
            title="Redis caching",
            summary="The speaker explains Redis caching.",
            source_id=source.id,
            start_time=10.0,
            end_time=12.0,
        ),
        db_path,
    )
    entity = insert_entity(Entity(id="entity-1", name="Redis", normalized_name="redis"), db_path)
    link_event_observation(event.id, observation.id, db_path)
    link_entity_to_event(event.id, entity.id, db_path=db_path)
    insert_edge(
        EvidenceEdge(
            id="edge-1",
            source_node_id=event.id,
            target_node_id=observation.id,
            relation="HAS_TRANSCRIPT",
            method=EdgeMethod.PROVENANCE,
            evidence_observation_ids=[observation.id],
        ),
        db_path,
    )
    writer = RecordingCypherWriter()

    summary = project_source(source.id, writer, db_path)

    assert summary == {
        "source_id": source.id,
        "sources_projected": 1,
        "observations_projected": 1,
        "events_projected": 1,
        "entities_projected": 1,
        "evidence_edges_projected": 1,
    }
    queries = "\n".join(query for query, _ in writer.calls)
    assert "CREATE CONSTRAINT source_id_unique" in queries
    assert "MERGE (node:Source" in queries
    assert "MERGE (node:Observation" in queries
    assert "MERGE (node:Event" in queries
    assert "MERGE (node:Entity" in queries
    assert "[:HAS_OBSERVATION]" in queries
    assert "[:INVOLVES]" in queries
    assert "[edge:EVIDENCE" in queries
    evidence_parameters = next(parameters for query, parameters in writer.calls if "[edge:EVIDENCE" in query)
    assert evidence_parameters["rows"][0]["relation"] == "HAS_TRANSCRIPT"


def test_project_source_rejects_unknown_source(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)

    with pytest.raises(ValueError, match="Source not found"):
        project_source("missing", RecordingCypherWriter(), db_path)
