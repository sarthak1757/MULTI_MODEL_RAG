from __future__ import annotations

from typing import Any


class Neo4jGraphClient:
    """A lazily connected Neo4j client.

    Keeping the driver optional allows the existing SQLite-only application and
    test suite to continue working until a Neo4j instance is deliberately
    configured.
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str,
    ) -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self._driver: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self.uri and self.username and self.password)

    def _get_driver(self) -> Any:
        if not self.configured:
            raise RuntimeError(
                "Neo4j is not configured. Set NEO4J_URI, NEO4J_USERNAME, and "
                "NEO4J_PASSWORD in .env."
            )
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError(
                    "The neo4j package is required. Install dependencies with: "
                    "pip install -r requirements.txt"
                ) from exc
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
            )
        return self._driver

    def verify_connectivity(self) -> None:
        """Fail clearly if the configured Neo4j database cannot be reached."""
        driver = self._get_driver()
        driver.verify_connectivity()

    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a read-only Cypher query and return JSON-friendly records."""
        with self._get_driver().session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher write query and return JSON-friendly records."""
        with self._get_driver().session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
