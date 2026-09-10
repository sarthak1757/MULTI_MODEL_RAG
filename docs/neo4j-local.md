# Run Neo4j locally

Neo4j is an optional graph projection for this application. SQLite remains the
system of record while we build and validate the graph integration.

## Prerequisites

Install Docker Desktop, then make sure Docker is running:

```bash
docker compose version
```

## Configure credentials

Copy the project environment template if you have not already done so:

```bash
cp .env.example .env
```

Set a local-only password with at least eight characters in `.env`:

```dotenv
NEO4J_PASSWORD=replace-with-a-long-local-password
```

Do not commit `.env`. It is already ignored by Git.

## Start and stop the database

```bash
docker compose -f compose.neo4j.yml up -d
docker compose -f compose.neo4j.yml ps
docker compose -f compose.neo4j.yml down
```

The named volumes retain graph data after `down`. To intentionally remove all
local Neo4j data, use `docker compose -f compose.neo4j.yml down -v`.

## Connect

Open Neo4j Browser at http://localhost:7474 and sign in with:

```text
username: neo4j
password: the NEO4J_PASSWORD value from .env
```

The Python app uses Bolt rather than the Browser HTTP endpoint:

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_DATABASE=neo4j
```

## First Cypher query

In Neo4j Browser, run:

```cypher
RETURN 'Neo4j is ready' AS status;
```

Cypher is Neo4j's graph-query language. `RETURN` is comparable to selecting a
literal value in SQL. We will add labels, nodes, relationships, constraints,
and graph queries in the next commits.

## Inspect a projected source

After processing a source with Neo4j configured, the application exposes its
subgraph at:

```text
GET http://localhost:8000/api/sources/<source-id>/graph
```

The API also uses the graph for optional GraphRAG expansion. FAISS first finds
semantic event seeds, then Neo4j adds same-source events connected through
shared entities. The answer model still receives only events with their own
SQLite-backed transcript, OCR, frame, image, or document evidence.
