# Multimodal RAG

Hackathon MVP foundation for an event-centric multimodal RAG system.

## Architecture

Raw media -> Observations -> Timeline Alignment -> Semantic Events -> Vector Index + Evidence Graph -> Hybrid Retrieval -> Evidence Bundle -> LLM answer.

The evidence graph is not intended to be an LLM-generated graph. Structural and provenance relationships should be deterministic, temporal relationships should come from timestamp alignment, semantic relationships can later use embeddings or entity overlap, and only higher-level inferred relationships should use an LLM.

## Current Scope

This stage provides only the project foundation:

- FastAPI app with `GET /health`
- Pydantic models for observations, semantic events, evidence edges, and event-observation links
- SQLite schema matching the core data model
- Lightweight SQLite helpers for insert/retrieve operations and graph neighborhood lookups
- Data directories for future uploads, frames, processed artifacts, and indexes

Video ingestion, OCR, embeddings, FAISS, LLM calls, and Streamlit are intentionally not implemented yet.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Initialize The Database

```bash
python -m app.storage.database
```

Or from Python:

```python
from app.storage.database import initialize_database

initialize_database()
```

## Run The API

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Optional Neo4j Graph Store

The current application uses SQLite as its system of record. Neo4j is an
optional graph projection for relationship traversal and GraphRAG features.
See [the local Neo4j guide](docs/neo4j-local.md) to run it with Docker Compose.

## Stage 1 Video Ingestion

Install dependencies, then run:

```bash
python -m app.ingestion.pipeline path/to/video.mp4
```

Optional frame interval override:

```bash
python -m app.ingestion.pipeline path/to/video.mp4 --frame-interval 5
```

This creates transcript, frame, and OCR observations, then adds deterministic `OCR --EXTRACTED_FROM--> Frame` provenance edges.
