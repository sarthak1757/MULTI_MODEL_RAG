from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.config import DATABASE_PATH, NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from app.graph.neo4j_client import Neo4jGraphClient
from app.graph.query import read_source_graph


ClientFactory = Callable[[str, str, str, str], Neo4jGraphClient]


def get_source_graph_if_configured(
    source_id: str,
    client_factory: ClientFactory = Neo4jGraphClient,
) -> dict[str, Any]:
    """Read a source subgraph while keeping Neo4j optional for API consumers."""
    client = client_factory(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    if not client.configured:
        return {"enabled": False, "status": "skipped", "graph": None}

    try:
        client.verify_connectivity()
        graph = read_source_graph(source_id, client)
        if graph is None:
            return {"enabled": True, "status": "not_synced", "graph": None}
        return {"enabled": True, "status": "ready", "graph": graph}
    except Exception as exc:
        return {
            "enabled": True,
            "status": "failed",
            "error": str(exc)[:300] or exc.__class__.__name__,
            "graph": None,
        }
    finally:
        client.close()
