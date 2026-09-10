from __future__ import annotations

from typing import Any, Callable

from app.config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from app.graph.neo4j_client import Neo4jGraphClient
from app.graph.rag import expand_related_events


ClientFactory = Callable[[str, str, str, str], Neo4jGraphClient]


def get_graph_expansion_if_configured(
    source_id: str,
    seed_event_ids: list[str],
    related_events_per_seed: int = 2,
    client_factory: ClientFactory = Neo4jGraphClient,
) -> dict[str, Any]:
    """Return optional, provenance-preserving graph expansion for vector seeds."""
    if not seed_event_ids:
        return {"enabled": False, "status": "skipped", "contexts": {}}

    client = client_factory(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    if not client.configured:
        return {"enabled": False, "status": "skipped", "contexts": {}}

    try:
        client.verify_connectivity()
        contexts = expand_related_events(source_id, seed_event_ids, client, related_events_per_seed)
        return {"enabled": True, "status": "ready", "contexts": contexts}
    except Exception as exc:
        return {
            "enabled": True,
            "status": "failed",
            "error": str(exc)[:300] or exc.__class__.__name__,
            "contexts": {},
        }
    finally:
        client.close()
