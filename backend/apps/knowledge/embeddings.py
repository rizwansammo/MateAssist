"""Embedding provider (D-060).

Local `bge-small-en-v1.5`, 384 dimensions. Zero per-token cost in perpetuity and
tenant runbook text never leaves infrastructure you control - which matters more
here than usual, because the text being embedded is other companies' internal IT
procedures.

Behind an interface so the model is swappable, but note that swapping it is not
free: EMBEDDING_DIM is baked into the vector() column and the HNSW index, so a
change means re-embedding every chunk of every tenant.

ASYMMETRY WARNING
    bge models are trained asymmetrically: queries get an instruction prefix,
    stored passages do not. Getting this backwards does not error - it silently
    degrades recall, which is the worst kind of bug in a retrieval system. That
    is why the prefix lives in exactly one place, here.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _load_model():
    """Load once per process.

    The model is ~130 MB and takes seconds to initialise; a Celery worker that
    reloaded it per task would spend most of its life loading. Double-checked
    locking because the prefork pool can enter this concurrently.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading embedding model %s", settings.EMBEDDING_MODEL)
            _model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
    return _model


class LocalEmbeddings:
    """sentence-transformers on CPU."""

    def __init__(self):
        self.dimensions = settings.EMBEDDING_DIM
        self.model_name = settings.EMBEDDING_MODEL

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _load_model()
        vectors = model.encode(
            texts,
            batch_size=16,
            # Cosine distance on unit vectors reduces to a dot product, and the
            # HNSW index is built with vector_cosine_ops - so normalising here
            # is what makes the index and the metric agree.
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        produced = vectors.shape[1]
        if produced != self.dimensions:
            raise ValueError(
                f"{self.model_name} produced {produced}-dim vectors but "
                f"EMBEDDING_DIM is {self.dimensions}. The database column and HNSW "
                f"index are built for {self.dimensions}; storing these would fail or, "
                f"worse, silently corrupt retrieval."
            )
        return [v.tolist() for v in vectors]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Stored chunks. No prefix - see the asymmetry warning above."""
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """A user's question. Prefixed, because bge was trained that way."""
        prefix = settings.EMBEDDING_QUERY_PREFIX.strip()
        prefixed = f"{prefix} {text.strip()}" if prefix else text.strip()
        return self._encode([prefixed])[0]


def get_embedding_provider() -> EmbeddingProvider:
    """Single construction point, so a future provider swap touches one line."""
    return LocalEmbeddings()
