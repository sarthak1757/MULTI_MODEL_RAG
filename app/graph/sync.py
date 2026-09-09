from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.config import DATABASE_PATH, NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from app.graph.neo4j_client import Neo4jGraphClient
from app.graph.neo4j_projection import project_source


ClientFactory = Callable[[str, str, str, str], Neo4jGraphClient]


def sync_source_if_configured(
    source_id: str,
    db_path: Path = DATABASE_PATH,
    client_factory: ClientFactory = Neo4jGraphClient,
) -> dict[str, Any]:
    """Synchronize a ready source to Neo4j without making it a hard dependency.

    A graph failure is reported separately from ingestion because SQLite and the
    local vector index remain the application's durable, queryable baseline.
    """
    client = client_factory(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    if not client.configured:
        return {"enabled": False, "status": "skipped"}

    try:
        client.verify_connectivity()
        summary = project_source(source_id, client, db_path)
        return {"enabled": True, "status": "ready", **summary}
    except Exception as exc:
        return {"enabled": True, "status": "failed", "error": str(exc)[:300] or exc.__class__.__name__}
    finally:
        client.close()
