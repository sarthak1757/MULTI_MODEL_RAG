from pathlib import Path

from app.models import (
    EdgeMethod,
    Entity,
    EvidenceEdge,
    Modality,
    Observation,
    SemanticEvent,
    Source,
    SourceStatus,
    SourceType,
)
from app.storage.database import (
    get_entities_for_event,
    get_entity_by_normalized_name,
    get_event_observations,
    get_neighbors,
    get_source,
    initialize_database,
    insert_edge,
    insert_entity,
    insert_event,
    insert_observation,
    insert_source,
    link_entity_to_event,
    link_event_observation,
    list_sources,
    update_source_status,
)


def test_database_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)

    observation = insert_observation(
        Observation(
            modality=Modality.TRANSCRIPT,
            content="Speaker introduces the demo.",
            source_id="demo-video",
            source_path="data/uploads/demo.mp4",
            start_time=0.0,
            end_time=3.5,
            confidence=0.95,
            metadata={"speaker": "host"},
        ),
        db_path,
    )
    event = insert_event(
        SemanticEvent(
            title="Demo introduction",
            summary="The host introduces the demo.",
            source_id="demo-video",
            start_time=0.0,
            end_time=3.5,
            entities=["host", "demo"],
            confidence=0.9,
        ),
        db_path,
    )
    link_event_observation(event.id, observation.id, db_path)
    entity = insert_entity(
        Entity(
            name="Redis",
            normalized_name="redis",
            entity_type="technology",
            confidence=0.92,
            metadata={"source": "test"},
        ),
        db_path,
    )
    link_entity_to_event(event.id, entity.id, confidence=0.88, db_path=db_path)

    edge = insert_edge(
        EvidenceEdge(
            source_node_id=event.id,
            target_node_id=entity.id,
            relation="mentions",
            confidence=1.0,
            method=EdgeMethod.ENTITY_MATCH,
            evidence_observation_ids=[observation.id],
        ),
        db_path,
    )

    event_observations = get_event_observations(event.id, db_path)
    event_entities = get_entities_for_event(event.id, db_path)
    redis = get_entity_by_normalized_name("redis", db_path)
    neighbors = get_neighbors(event.id, db_path)

    assert event_observations == [observation]
    assert event_entities == [entity]
    assert redis == entity
    assert neighbors["edges"] == [edge]
    assert neighbors["nodes"][entity.id] == entity


def test_source_registry_helpers(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)

    source = insert_source(
        Source(
            id="source-1",
            filename="demo.mp4",
            source_type=SourceType.VIDEO,
            path="data/uploads/demo.mp4",
            duration=12.5,
            status=SourceStatus.UPLOADED,
        ),
        db_path,
    )
    update_source_status(
        source.id,
        SourceStatus.READY,
        db_path,
        metadata={"events": 2},
    )

    stored = get_source(source.id, db_path)

    assert stored is not None
    assert stored.filename == "demo.mp4"
    assert stored.status == SourceStatus.READY
    assert stored.metadata == {"events": 2}
    assert list_sources(db_path)[0].id == source.id
