"""Hybrid retrieval (D-056).

Vector search alone fails on exact tokens - error codes, hostnames, command
names - because an embedding of "0x80070035" is not meaningfully close to an
embedding of the surrounding prose. Keyword search alone fails on paraphrase:
"my VPN keeps dropping" matches nothing in a document that says "the tunnel
disconnects".

Reciprocal Rank Fusion combines the two on RANK rather than score, which is what
makes it work at all: a cosine similarity of 0.67 and a ts_rank of 0.08 are not
comparable numbers, but "first" and "third" are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import connection

from apps.knowledge.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    document_title: str
    text: str
    from_image: bool
    source_page: int
    score: float

    @property
    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.document_title,
            "page": self.source_page,
            "from_image": self.from_image,
        }


def _vector_search(vector, limit: int) -> list[tuple[int, int]]:
    """Returns (chunk_id, rank) pairs, best first."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id
            FROM knowledge_documentchunk c
            JOIN knowledge_document d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL AND d.status = 'INDEXED'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            [str(vector), limit],
        )
        return [(row[0], rank) for rank, row in enumerate(cursor.fetchall(), start=1)]


def _keyword_search(query: str, limit: int) -> list[tuple[int, int]]:
    """PostgreSQL full-text search over the same corpus.

    websearch_to_tsquery rather than plainto_tsquery: it understands quoted
    phrases and negation, which is how people actually type into a search box.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id
            FROM knowledge_documentchunk c
            JOIN knowledge_document d ON d.id = c.document_id
            WHERE d.status = 'INDEXED'
              AND to_tsvector('english', c.text) @@ websearch_to_tsquery('english', %s)
            ORDER BY ts_rank(to_tsvector('english', c.text),
                             websearch_to_tsquery('english', %s)) DESC
            LIMIT %s
            """,
            [query, query, limit],
        )
        return [(row[0], rank) for rank, row in enumerate(cursor.fetchall(), start=1)]


def _fuse(*ranked_lists, k: int) -> dict[int, float]:
    """Reciprocal Rank Fusion: score = sum(1 / (k + rank)).

    k dampens the influence of top ranks so one search strategy being confidently
    wrong cannot dominate the other being roughly right.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for chunk_id, rank in ranked:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def retrieve(query: str, *, top_n: int | None = None) -> list[Hit]:
    """Retrieve passages for a question, scoped to the current tenant.

    Scoping is by RLS, not by a WHERE clause: these are raw queries with no
    tenant filter, and they are safe precisely because the database refuses to
    return another tenant's rows (D-020). That property is asserted by a test.
    """
    query = (query or "").strip()
    if not query:
        return []

    top_k = settings.RETRIEVAL_TOP_K
    top_n = top_n or settings.RETRIEVAL_TOP_N

    try:
        vector = get_embedding_provider().embed_query(query)
        vector_hits = _vector_search(vector, top_k)
    except Exception:  # noqa: BLE001
        # Degrade to keyword-only rather than failing the user's question.
        logger.exception("vector search failed; falling back to keyword only")
        vector_hits = []

    try:
        keyword_hits = _keyword_search(query, top_k)
    except Exception:  # noqa: BLE001
        logger.exception("keyword search failed; continuing with vectors only")
        keyword_hits = []

    fused = _fuse(vector_hits, keyword_hits, k=settings.RETRIEVAL_RRF_K)
    if not fused:
        return []

    best = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:top_n]
    ids = [chunk_id for chunk_id, _ in best]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, c.document_id, d.title, c.text, c.from_image, c.source_page
            FROM knowledge_documentchunk c
            JOIN knowledge_document d ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            [ids],
        )
        rows = {row[0]: row for row in cursor.fetchall()}

    hits = []
    for chunk_id, score in best:
        row = rows.get(chunk_id)
        if row is None:
            continue  # RLS filtered it, or it was deleted mid-query
        hits.append(
            Hit(
                chunk_id=row[0],
                document_id=row[1],
                document_title=row[2],
                text=row[3],
                from_image=row[4],
                source_page=row[5],
                score=score,
            )
        )
    return hits
