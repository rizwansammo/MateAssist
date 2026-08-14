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

    # How well this chunk actually matched, as opposed to where it ranked.
    #
    # `score` above is the fused RANK score, and it carries no relevance signal
    # at all: the top hit of any search scores 1/(k+1) - 0.0164 with the default
    # k=60 - whether the match was perfect or nonsense. Thresholding it would
    # silently do nothing, which is why these two fields exist (D-138).
    similarity: float = 0.0  # cosine, 0..1. Absent (0.0) if only FTS found it.
    keyword_match: bool = False  # FTS matched real lexemes from the query.

    @property
    def relevance(self) -> float:
        """One number for gating.

        A chunk found only by keyword search has no cosine similarity, but a
        full-text match means the query's own words literally appear in it -
        which is exactly the case hybrid retrieval exists to catch (error codes,
        hostnames, command names embed poorly). Treating that as zero relevance
        would gate out the strongest evidence there is.
        """
        if self.keyword_match:
            return max(self.similarity, KEYWORD_FLOOR)
        return self.similarity

    @property
    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.document_title,
            "page": self.source_page,
            "from_image": self.from_image,
        }


# Relevance credited to a chunk that full-text search matched but vector search
# did not rank. Deliberately above the grounding floor and below the citation
# bar: a literal term match is good enough to show the model, and on its own not
# good enough to claim a source in the UI.
KEYWORD_FLOOR = 0.45


def _vector_search(vector, limit: int) -> list[tuple[int, int, float]]:
    """Returns (chunk_id, rank, cosine_similarity), best first.

    `<=>` is cosine DISTANCE in pgvector - 0 means identical - so similarity is
    1 - distance. The value was previously computed by the index and thrown
    away; carrying it is what makes relevance gating possible.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, 1 - (c.embedding <=> %s::vector) AS similarity
            FROM knowledge_documentchunk c
            JOIN knowledge_document d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL AND d.status = 'INDEXED'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            [str(vector), str(vector), limit],
        )
        return [
            (row[0], rank, float(row[1])) for rank, row in enumerate(cursor.fetchall(), start=1)
        ]


def _keyword_search(query: str, limit: int) -> list[tuple[int, int]]:
    """PostgreSQL full-text search over the same corpus.

    websearch_to_tsquery rather than plainto_tsquery: it understands quoted
    phrases and negation, which is how people actually type into a search box.

    Note that a greeting produces no rows here at all - "hi" and "thanks" are
    either stopwords or lexemes absent from any runbook - so FTS presence is
    itself a relevance signal, not just an ordering.
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


def focus(hits: list[Hit]) -> list[Hit]:
    """Keep only the winning document's passages, when there is a clear winner.

    **The failure this prevents.** Retrieval returns the best CHUNKS, not the
    best document. Ask "my VPN won't connect" with two VPN runbooks indexed and
    the top six passages interleave both - GlobalProtect's service restart next
    to AnyConnect's profile deletion. Handed that material, a model writes one
    coherent procedure out of two incompatible ones. Every individual step is
    true; the combination is fiction, and it reads perfectly.

    Dropping the runner-up before the prompt is assembled makes blending
    impossible rather than merely discouraged - the wrong material is not in the
    room. A prompt instruction would be a request; this is a guarantee.

    A document is scored by its BEST passage, not its passage count. A long
    runbook that mentions the topic in passing would otherwise outvote a short
    one that answers the question exactly.

    When the margin is close the question is genuinely ambiguous - both clients
    plausibly apply - and silently discarding one would drop the right answer on
    a coin-flip. Both are kept, and the reference block labels them so the model
    can see they are different documents.
    """
    if len(hits) < 2:
        return hits

    best_per_document: dict[int, float] = {}
    for hit in hits:
        current = best_per_document.get(hit.document_id, 0.0)
        best_per_document[hit.document_id] = max(current, hit.relevance)

    if len(best_per_document) < 2:
        return hits

    ranked = sorted(best_per_document.items(), key=lambda item: item[1], reverse=True)
    (winner_id, winner_score), (_runner_id, runner_score) = ranked[0], ranked[1]

    if winner_score - runner_score < settings.RETRIEVAL_FOCUS_MARGIN:
        return hits  # too close to call - keep both, labelled

    return [hit for hit in hits if hit.document_id == winner_id]


def gate(hits: list[Hit]) -> tuple[list[Hit], list[Hit]]:
    """Split retrieved passages into (show the model, claim as a source).

    Two levels, because the two mistakes cost different things (D-138).

    *Grounding* uses the looser bar. Dropping a passage here means the model
    answers without the runbook that had the answer - a wrong answer, which is
    the failure this whole pipeline exists to prevent.

    *Citation* uses the stricter bar. Showing a source that did not contribute
    is a false claim, and once a user learns the "Sources" chip appears on
    "Hi" it stops being evidence and becomes decoration - which quietly
    destroys the value of every citation that IS earned.

    So a borderline question keeps its grounding and loses only its chip.
    """
    ground_min = settings.RETRIEVAL_GROUND_MIN
    cite_min = settings.RETRIEVAL_CITE_MIN

    grounded = [hit for hit in hits if hit.relevance >= ground_min]
    citable = [hit for hit in grounded if hit.relevance >= cite_min]
    return grounded, citable


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

    similarity: dict[int, float] = {}
    try:
        vector = get_embedding_provider().embed_query(query)
        vector_rows = _vector_search(vector, top_k)
        similarity = {chunk_id: value for chunk_id, _rank, value in vector_rows}
        vector_hits = [(chunk_id, rank) for chunk_id, rank, _value in vector_rows]
    except Exception:  # noqa: BLE001
        # Degrade to keyword-only rather than failing the user's question.
        logger.exception("vector search failed; falling back to keyword only")
        vector_hits = []

    try:
        keyword_hits = _keyword_search(query, top_k)
    except Exception:  # noqa: BLE001
        logger.exception("keyword search failed; continuing with vectors only")
        keyword_hits = []

    matched_by_keyword = {chunk_id for chunk_id, _rank in keyword_hits}

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
                similarity=similarity.get(chunk_id, 0.0),
                keyword_match=chunk_id in matched_by_keyword,
            )
        )
    return hits
