from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH, ensure_data_dirs
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

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_connection(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    ensure_data_dirs()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: Path = DATABASE_PATH) -> None:
    ensure_data_dirs()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(db_path) as connection:
        connection.executescript(schema)


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _from_json(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _to_iso(value: datetime) -> str:
    return value.isoformat()


def _observation_from_row(row: sqlite3.Row) -> Observation:
    data = dict(row)
    data["metadata"] = _from_json(data.get("metadata"), {})
    data["modality"] = Modality(data["modality"])
    return Observation(**data)


def _event_from_row(row: sqlite3.Row) -> SemanticEvent:
    data = dict(row)
    data["entities"] = _from_json(data.get("entities"), [])
    return SemanticEvent(**data)


def _entity_from_row(row: sqlite3.Row) -> Entity:
    data = dict(row)
    data["metadata"] = _from_json(data.get("metadata"), {})
    return Entity(**data)


def _edge_from_row(row: sqlite3.Row) -> EvidenceEdge:
    data = dict(row)
    data["method"] = EdgeMethod(data["method"])
    data["evidence_observation_ids"] = _from_json(data.get("evidence_observation_ids"), [])
    data["metadata"] = _from_json(data.get("metadata"), {})
    return EvidenceEdge(**data)


def _source_from_row(row: sqlite3.Row) -> Source:
    data = dict(row)
    data["source_type"] = SourceType(data["source_type"])
    data["status"] = SourceStatus(data["status"])
    data["metadata"] = _from_json(data.get("metadata"), {})
    return Source(**data)


def insert_source(source: Source, db_path: Path = DATABASE_PATH) -> Source:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO sources (
                id, filename, source_type, path, duration, status, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.filename,
                source.source_type.value,
                source.path,
                source.duration,
                source.status.value,
                _to_json(source.metadata),
                _to_iso(source.created_at),
            ),
        )
    return source


def update_source_status(
    source_id: str,
    status: SourceStatus,
    db_path: Path = DATABASE_PATH,
    metadata: dict[str, Any] | None = None,
    duration: float | None = None,
) -> None:
    existing = get_source(source_id, db_path)
    merged_metadata = existing.metadata if existing else {}
    if metadata:
        merged_metadata = {**merged_metadata, **metadata}

    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE sources
            SET status = ?,
                duration = COALESCE(?, duration),
                metadata = ?
            WHERE id = ?
            """,
            (status.value, duration, _to_json(merged_metadata), source_id),
        )


def get_source(source_id: str, db_path: Path = DATABASE_PATH) -> Source | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()
    return _source_from_row(row) if row else None


def list_sources(db_path: Path = DATABASE_PATH) -> list[Source]:
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()
    return [_source_from_row(row) for row in rows]


def delete_source(source_id: str, db_path: Path = DATABASE_PATH) -> bool:
    source = get_source(source_id, db_path)
    if source is None:
        return False

    with get_connection(db_path) as connection:
        observation_rows = connection.execute(
            "SELECT id FROM observations WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        event_rows = connection.execute(
            "SELECT id FROM semantic_events WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        node_ids = [row["id"] for row in observation_rows] + [row["id"] for row in event_rows]

        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            connection.execute(
                f"""
                DELETE FROM evidence_edges
                WHERE source_node_id IN ({placeholders})
                   OR target_node_id IN ({placeholders})
                """,
                (*node_ids, *node_ids),
            )

        connection.execute(
            """
            DELETE FROM event_observations
            WHERE event_id IN (
                SELECT id FROM semantic_events WHERE source_id = ?
            )
               OR observation_id IN (
                SELECT id FROM observations WHERE source_id = ?
            )
            """,
            (source_id, source_id),
        )
        connection.execute(
            """
            DELETE FROM event_entities
            WHERE event_id IN (
                SELECT id FROM semantic_events WHERE source_id = ?
            )
            """,
            (source_id,),
        )
        connection.execute("DELETE FROM semantic_events WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM observations WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    return True


def insert_observation(observation: Observation, db_path: Path = DATABASE_PATH) -> Observation:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO observations (
                id, modality, content, source_id, source_path, start_time, end_time,
                timestamp, confidence, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id,
                observation.modality.value,
                observation.content,
                observation.source_id,
                observation.source_path,
                observation.start_time,
                observation.end_time,
                observation.timestamp,
                observation.confidence,
                _to_json(observation.metadata),
                _to_iso(observation.created_at),
            ),
        )
    return observation


def get_observation(observation_id: str, db_path: Path = DATABASE_PATH) -> Observation | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
    return _observation_from_row(row) if row else None


def list_observations(db_path: Path = DATABASE_PATH) -> list[Observation]:
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM observations ORDER BY created_at").fetchall()
    return [_observation_from_row(row) for row in rows]


def list_observations_for_source(
    source_id: str,
    db_path: Path = DATABASE_PATH,
) -> list[Observation]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM observations
            WHERE source_id = ?
            ORDER BY COALESCE(start_time, timestamp, 0), created_at
            """,
            (source_id,),
        ).fetchall()
    return [_observation_from_row(row) for row in rows]


def insert_event(event: SemanticEvent, db_path: Path = DATABASE_PATH) -> SemanticEvent:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO semantic_events (
                id, title, summary, source_id, start_time, end_time,
                entities, confidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.title,
                event.summary,
                event.source_id,
                event.start_time,
                event.end_time,
                _to_json(event.entities),
                event.confidence,
                _to_iso(event.created_at),
            ),
        )
    return event


def get_event(event_id: str, db_path: Path = DATABASE_PATH) -> SemanticEvent | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM semantic_events WHERE id = ?",
            (event_id,),
        ).fetchone()
    return _event_from_row(row) if row else None


def update_event_semantics(
    event_id: str,
    title: str,
    summary: str,
    entities: list[str],
    db_path: Path = DATABASE_PATH,
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE semantic_events
            SET title = ?, summary = ?, entities = ?
            WHERE id = ?
            """,
            (title, summary, _to_json(entities), event_id),
        )


def list_events(db_path: Path = DATABASE_PATH) -> list[SemanticEvent]:
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM semantic_events ORDER BY created_at").fetchall()
    return [_event_from_row(row) for row in rows]


def list_events_for_source(source_id: str, db_path: Path = DATABASE_PATH) -> list[SemanticEvent]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM semantic_events
            WHERE source_id = ?
            ORDER BY COALESCE(start_time, 0), created_at
            """,
            (source_id,),
        ).fetchall()
    return [_event_from_row(row) for row in rows]


def insert_entity(entity: Entity, db_path: Path = DATABASE_PATH) -> Entity:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO entities (
                id, name, normalized_name, entity_type, confidence, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity.id,
                entity.name,
                entity.normalized_name,
                entity.entity_type,
                entity.confidence,
                _to_json(entity.metadata),
                _to_iso(entity.created_at),
            ),
        )
    return entity


def get_entity(entity_id: str, db_path: Path = DATABASE_PATH) -> Entity | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
    return _entity_from_row(row) if row else None


def get_entity_by_normalized_name(
    normalized_name: str,
    db_path: Path = DATABASE_PATH,
) -> Entity | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM entities WHERE normalized_name = ?",
            (normalized_name,),
        ).fetchone()
    return _entity_from_row(row) if row else None


def link_entity_to_event(
    event_id: str,
    entity_id: str,
    confidence: float | None = None,
    db_path: Path = DATABASE_PATH,
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO event_entities (event_id, entity_id, confidence)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, entity_id) DO UPDATE SET
                confidence = excluded.confidence
            """,
            (event_id, entity_id, confidence),
        )


def get_entities_for_event(event_id: str, db_path: Path = DATABASE_PATH) -> list[Entity]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT entities.*
            FROM entities
            JOIN event_entities
              ON entities.id = event_entities.entity_id
            WHERE event_entities.event_id = ?
            ORDER BY entities.normalized_name
            """,
            (event_id,),
        ).fetchall()
    return [_entity_from_row(row) for row in rows]


def link_event_observation(
    event_id: str,
    observation_id: str,
    db_path: Path = DATABASE_PATH,
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO event_observations (event_id, observation_id)
            VALUES (?, ?)
            """,
            (event_id, observation_id),
        )


def link_event_observations(
    event_id: str,
    observation_ids: Iterable[str],
    db_path: Path = DATABASE_PATH,
) -> None:
    with get_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO event_observations (event_id, observation_id)
            VALUES (?, ?)
            """,
            [(event_id, observation_id) for observation_id in observation_ids],
        )


def get_event_observations(event_id: str, db_path: Path = DATABASE_PATH) -> list[Observation]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT observations.*
            FROM observations
            JOIN event_observations
              ON observations.id = event_observations.observation_id
            WHERE event_observations.event_id = ?
            ORDER BY COALESCE(observations.timestamp, observations.start_time, 0), observations.created_at
            """,
            (event_id,),
        ).fetchall()
    return [_observation_from_row(row) for row in rows]


def insert_edge(edge: EvidenceEdge, db_path: Path = DATABASE_PATH) -> EvidenceEdge:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO evidence_edges (
                id, source_node_id, target_node_id, relation, confidence, method,
                evidence_observation_ids, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge.id,
                edge.source_node_id,
                edge.target_node_id,
                edge.relation,
                edge.confidence,
                edge.method.value,
                _to_json(edge.evidence_observation_ids),
                _to_json(edge.metadata),
                _to_iso(edge.created_at),
            ),
        )
    return edge


def get_edge(edge_id: str, db_path: Path = DATABASE_PATH) -> EvidenceEdge | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM evidence_edges WHERE id = ?",
            (edge_id,),
        ).fetchone()
    return _edge_from_row(row) if row else None


def list_edges(db_path: Path = DATABASE_PATH) -> list[EvidenceEdge]:
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM evidence_edges ORDER BY created_at").fetchall()
    return [_edge_from_row(row) for row in rows]


def get_neighbors(node_id: str, db_path: Path = DATABASE_PATH) -> dict[str, Any]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM evidence_edges
            WHERE source_node_id = ? OR target_node_id = ?
            ORDER BY created_at
            """,
            (node_id, node_id),
        ).fetchall()

        edges = [_edge_from_row(row) for row in rows]
        neighbor_ids = sorted(
            {
                edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
                for edge in edges
            }
        )

        nodes: dict[str, Observation | SemanticEvent | Entity] = {}
        for neighbor_id in neighbor_ids:
            observation = get_observation(neighbor_id, db_path)
            if observation is not None:
                nodes[neighbor_id] = observation
                continue

            event = get_event(neighbor_id, db_path)
            if event is not None:
                nodes[neighbor_id] = event
                continue

            entity = get_entity(neighbor_id, db_path)
            if entity is not None:
                nodes[neighbor_id] = entity

    return {"edges": edges, "nodes": nodes}


if __name__ == "__main__":
    initialize_database()
    print(f"Initialized database at {DATABASE_PATH}")
