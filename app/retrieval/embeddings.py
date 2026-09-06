from __future__ import annotations

from typing import Iterable

import numpy as np

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_model = None


def get_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for local embeddings. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc
        _model = SentenceTransformer(model_name)
    return _model


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = vectors.astype("float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def embed_texts(texts: Iterable[str]) -> np.ndarray:
    text_list = list(texts)
    if not text_list:
        return np.zeros((0, 0), dtype="float32")
    model = get_model()
    embeddings = model.encode(text_list, convert_to_numpy=True, show_progress_bar=False)
    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)
    return _normalize(embeddings)


def embed_events(event_documents: Iterable[str]) -> np.ndarray:
    return embed_texts(event_documents)


def embed_query(query: str) -> np.ndarray:
    return embed_text(query)
