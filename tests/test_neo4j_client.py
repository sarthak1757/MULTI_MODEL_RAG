from __future__ import annotations

import pytest

from app.graph.neo4j_client import Neo4jGraphClient


def test_client_reports_when_neo4j_is_not_configured() -> None:
    client = Neo4jGraphClient(uri="", username="neo4j", password="", database="neo4j")

    assert client.configured is False
    with pytest.raises(RuntimeError, match="Neo4j is not configured"):
        client.verify_connectivity()


def test_client_is_configured_only_with_all_connection_values() -> None:
    client = Neo4jGraphClient(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="local-password",
        database="neo4j",
    )

    assert client.configured is True
