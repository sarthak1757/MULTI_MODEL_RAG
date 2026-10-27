---
title: Multimodal RAG
sdk: docker
app_port: 7860
---

# Multimodal RAG: Ask Questions About Videos, Images and PDFs

**Live app:** `<ADD HUGGING FACE SPACE URL>`
**Demo video:** `<ADD VIDEO URL>`

## Problem Statement

Useful information is locked inside recordings, screenshots and documents: a lecture video, a slide image, a PDF. Searching them means scrubbing through video or reading everything. Plain "chat with your file" tools also tend to give answers that are not tied to evidence, so you cannot tell what is true.

## Target Users

- Students who want to find a specific moment or fact in lecture recordings, slides and notes.
- Researchers and analysts who review recorded meetings, demos or reports.
- Anyone who needs answers from mixed media (video, image, PDF) with proof of where each answer came from.

## Solution

The app turns each uploaded file into **timestamped observations** (speech transcript, video frames, OCR text, PDF text). It aligns them on a timeline and groups them into **semantic events**. Events are indexed for search and linked in an **evidence graph**. When a user asks a question, the app retrieves the most relevant events, gathers their supporting evidence, and asks an LLM to answer **using only that evidence**. The answer is shown next to the source frames and transcript lines it used.

## Key Features

1. **Upload video, image or PDF.** Supported types: `.mp4 .mov .mkv .png .jpg .jpeg .pdf`.
2. **Automatic processing.** Speech-to-text, frame extraction, OCR, and event building, with a progress view.
3. **Ask questions** about a selected source and get an answer with cited evidence (frames, transcript, OCR text).
4. **Event timeline** showing what happens and when, with filters per source.
5. **GraphRAG explorer.** Entities and relationships between events can be explored, and optional Neo4j expansion finds related events through shared entities.
6. **Source management.** List, filter and delete sources.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Pydantic |
| Storage | SQLite (system of record), FAISS (vector index) |
| Graph (optional) | Neo4j |
| Speech / OCR / vision | faster-whisper, EasyOCR, OpenCV, PyMuPDF |
| Embeddings | sentence-transformers |
| LLM | Google Gemini API |
| Frontend | React, TypeScript, Vite |
| Deployment | Docker, Hugging Face Spaces |

## Architecture

```
Upload (video / image / PDF)
        |
        v
Ingestion: transcript, frames, OCR text, PDF text   -> Observations
        |
        v
Timeline alignment + event builder                  -> Semantic events
        |
        v
Gemini enrichment (titles, summaries, entities)
        |
        +--> FAISS vector index  (semantic search)
        +--> SQLite evidence graph (provenance + time links)
        +--> Neo4j projection    (optional, entity links)
        |
        v
Question -> Hybrid retrieval -> Evidence bundle -> Gemini answer (grounded in evidence)
```

Main folders:

- `app/ingestion/` reads each media type and creates observations.
- `app/processing/` aligns observations in time and builds events and graph edges.
- `app/semantic/` calls Gemini to enrich events.
- `app/retrieval/` builds the FAISS index and runs hybrid retrieval.
- `app/graph/` handles the optional Neo4j projection and GraphRAG expansion.
- `app/generation/` builds the final grounded answer.
- `app/storage/` holds the SQLite schema and helpers.
- `frontend/` is the React research console.

Design decision: SQLite is the source of truth. Every graph-expanded event is re-read from SQLite with its own evidence before it reaches the LLM, so answers stay evidence-first. If Neo4j is not configured or is unavailable, the app falls back to FAISS-only retrieval.

## Local Setup

Requirements: Python 3.11+, Node 20+, ffmpeg.

```bash
git clone https://github.com/sarthak1757/MULTI_MODEL_RAG.git
cd MULTI_MODEL_RAG

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your Gemini key in .env
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev                 # opens http://localhost:5173
```

Run the tests with `pip install -r requirements-dev.txt` and then `pytest`.

## Environment Variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Required | Purpose |
|----------|----------|---------|
| `GEMINI_API_KEY` | Yes | Key for semantic enrichment and answer generation |
| `GEMINI_MODEL` | No | Gemini model name (see `.env.example`) |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | No | Enable the optional Neo4j graph. Leave unset to use SQLite and FAISS only |
| `CORS_ORIGINS` | No | Extra allowed origins (comma separated) if the frontend is hosted elsewhere |
| `VITE_API_BASE_URL` | No | Frontend build setting for the API URL (defaults to `http://localhost:8000`) |
| `WHISPER_MODEL_SIZE`, `FRAME_INTERVAL_SECONDS`, `EASYOCR_LANGUAGES`, `DATABASE_PATH` | No | Processing settings with defaults |

## Deployment

The app is deployed as a single Docker container on **Hugging Face Spaces**: FastAPI serves both the API and the built React app, so there is one URL.

- Live URL: `<ADD HUGGING FACE SPACE URL>`
- `GEMINI_API_KEY` is stored as a Space secret, not in the code.
- The free tier has a temporary disk, so uploaded data is cleared when the Space restarts. Upload a short file to try it.
- To self-host: `docker build -t multimodal-rag .` then `docker run -p 7860:7860 -e GEMINI_API_KEY=your_key multimodal-rag`.

## Optional: Neo4j

See [docs/neo4j-local.md](docs/neo4j-local.md) to run Neo4j locally with Docker Compose.

## Project Background and Credits

`<ADD: when and why you built this, and whether it was solo. Example: "Started as a hackathon MVP in September 2026 and extended for this end-term project. Built solo.">`

Built with open-source libraries: FastAPI, FAISS, sentence-transformers, faster-whisper, EasyOCR, OpenCV, PyMuPDF, React and Neo4j. AI tools were used during development for coding assistance.
