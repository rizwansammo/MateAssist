"""Relevance gating (D-138).

The bug: saying "Hi" produced a reply captioned **Sources: VPN Runbook (demo)**.
The greeting did not come from the runbook, so the citation was false - and a
citation that appears on everything stops being evidence.

These tests are network-free and database-free. They exercise the decision, not
the search; the search itself is measured by `manage.py retrieval_probe` against
a real corpus, because a threshold fitted to fixtures would prove nothing.
"""

import pytest
from django.test import override_settings

from apps.chat.retrieval import KEYWORD_FLOOR, Hit, focus, gate


def hit(similarity=0.0, keyword_match=False, chunk_id=1):
    return Hit(
        chunk_id=chunk_id,
        document_id=1,
        document_title="VPN Runbook",
        text="Restart the GlobalProtect service.",
        from_image=False,
        source_page=1,
        score=0.0164,  # the RRF score: constant for a top hit, hence useless
        similarity=similarity,
        keyword_match=keyword_match,
    )


# ------------------------------------------------- the reason for `similarity`


def test_the_fused_score_carries_no_relevance_signal():
    """Documents why a second field was needed at all.

    Reciprocal Rank Fusion scores by position: the top hit is always 1/(60+1)
    whether the match was perfect or nonsense. Gating on it would compile, run,
    and do nothing - the worst kind of bug, because the feature would look
    implemented.
    """
    perfect = hit(similarity=0.95)
    useless = hit(similarity=0.11)

    assert perfect.score == useless.score == pytest.approx(0.0164, abs=0.001)
    assert perfect.relevance > useless.relevance


# ------------------------------------------------------------- the two levels


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_small_talk_is_neither_grounded_nor_cited():
    """Measured: greetings score 0.376-0.502 against the indexed corpus."""
    grounded, citable = gate([hit(similarity=0.40)])

    assert grounded == []
    assert citable == []


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_a_real_question_is_both_grounded_and_cited():
    """Measured: in-corpus questions score 0.557-0.736."""
    grounded, citable = gate([hit(similarity=0.68)])

    assert len(grounded) == 1
    assert len(citable) == 1


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_a_borderline_question_keeps_grounding_and_loses_only_its_chip():
    """The whole point of two levels.

    Between the bars, the model still sees the runbook - so the answer stays
    correct - and the UI simply does not claim a source it is unsure of. The
    mistake costs a chip, never an answer.
    """
    grounded, citable = gate([hit(similarity=0.51)])

    assert len(grounded) == 1, "grounding must survive a borderline match"
    assert citable == [], "but nothing is claimed as a source"


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_citable_is_always_a_subset_of_grounded():
    """A source can never be cited without having been shown to the model -
    that would be a citation for text the answer could not have used."""
    hits = [hit(similarity=s, chunk_id=i) for i, s in enumerate([0.2, 0.45, 0.51, 0.7, 0.9])]

    grounded, citable = gate(hits)

    assert {h.chunk_id for h in citable} <= {h.chunk_id for h in grounded}


# --------------------------------------------------- the keyword-only case ---


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_a_literal_term_match_is_not_treated_as_zero_relevance():
    """The case hybrid retrieval exists for.

    "0x80070035" embeds poorly - a cosine similarity against surrounding prose
    is meaningless - but full-text search finds it exactly. A chunk that only
    FTS matched has no similarity score, and treating that as 0.0 would gate out
    the strongest evidence available.
    """
    keyword_only = hit(similarity=0.0, keyword_match=True)

    assert keyword_only.relevance == KEYWORD_FLOOR
    grounded, _ = gate([keyword_only])
    assert grounded == [], "the floor alone is below the grounding bar"


@override_settings(RETRIEVAL_GROUND_MIN=0.40, RETRIEVAL_CITE_MIN=0.53)
def test_the_keyword_floor_can_carry_a_chunk_into_grounding():
    """With a looser grounding bar the literal match is enough to show the
    model, while still not enough to claim as a source on its own."""
    grounded, citable = gate([hit(similarity=0.0, keyword_match=True)])

    assert len(grounded) == 1
    assert citable == [], "a term match alone does not earn a citation"


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_a_strong_vector_match_is_not_dragged_down_by_the_floor():
    """`relevance` takes the better of the two signals, never the keyword floor
    in place of a good cosine score."""
    strong = hit(similarity=0.80, keyword_match=True)

    assert strong.relevance == 0.80
    grounded, citable = gate([strong])
    assert len(grounded) == len(citable) == 1


# ------------------------------------------------------------------ shape ----


def test_gating_nothing_returns_nothing():
    assert gate([]) == ([], [])


@override_settings(RETRIEVAL_GROUND_MIN=0.50, RETRIEVAL_CITE_MIN=0.53)
def test_order_is_preserved_so_the_best_passage_stays_first():
    hits = [hit(similarity=0.9, chunk_id=1), hit(similarity=0.6, chunk_id=2)]
    grounded, citable = gate(hits)

    assert [h.chunk_id for h in grounded] == [1, 2]
    assert [h.chunk_id for h in citable] == [1, 2]


# ------------------------------------------------ document focus (D-139) -----


def doc_hit(document_id, similarity, chunk_id=None):
    h = hit(similarity=similarity, chunk_id=chunk_id or document_id * 10)
    h.document_id = document_id
    h.document_title = f"Runbook {document_id}"
    return h


@override_settings(RETRIEVAL_FOCUS_MARGIN=0.04)
def test_a_clear_winner_drops_the_other_document_entirely():
    """The blending failure, prevented at the source.

    Ask "my VPN won't connect" with two VPN runbooks indexed and retrieval
    interleaves both - GlobalProtect's service restart beside AnyConnect's
    profile deletion. A model handed that material writes one tidy procedure out
    of two incompatible ones, where every step is true and the combination is
    fiction. Removing the runner-up makes that impossible rather than merely
    discouraged.
    """
    hits = [
        doc_hit(1, 0.74, chunk_id=1),
        doc_hit(2, 0.66, chunk_id=2),  # the other VPN client
        doc_hit(1, 0.68, chunk_id=3),
    ]

    focused = focus(hits)

    assert {h.document_id for h in focused} == {1}
    assert len(focused) == 2, "both of the winner's passages survive"


@override_settings(RETRIEVAL_FOCUS_MARGIN=0.04)
def test_a_close_call_keeps_both_documents():
    """Silently discarding a document on a coin-flip would drop the right answer
    half the time. Ambiguity is handled by showing both, labelled."""
    hits = [doc_hit(1, 0.70, chunk_id=1), doc_hit(2, 0.69, chunk_id=2)]

    focused = focus(hits)

    assert {h.document_id for h in focused} == {1, 2}


@override_settings(RETRIEVAL_FOCUS_MARGIN=0.04)
def test_a_document_is_scored_by_its_best_passage_not_its_share_of_them():
    """A long runbook mentioning the topic in passing would otherwise outvote a
    short one that answers the question exactly."""
    hits = [
        doc_hit(1, 0.80, chunk_id=1),  # one excellent passage
        doc_hit(2, 0.60, chunk_id=2),  # four mediocre ones
        doc_hit(2, 0.59, chunk_id=3),
        doc_hit(2, 0.58, chunk_id=4),
        doc_hit(2, 0.57, chunk_id=5),
    ]

    assert {h.document_id for h in focus(hits)} == {1}


def test_focus_leaves_a_single_document_untouched():
    hits = [doc_hit(1, 0.7, chunk_id=1), doc_hit(1, 0.6, chunk_id=2)]
    assert focus(hits) == hits


def test_focus_handles_nothing_and_one_hit():
    assert focus([]) == []
    single = [doc_hit(1, 0.7)]
    assert focus(single) == single


@override_settings(RETRIEVAL_FOCUS_MARGIN=0.04, RETRIEVAL_GROUND_MIN=0.53)
def test_focus_runs_before_gate_so_a_strong_loser_cannot_survive():
    """Order matters. Gating first would let a 0.66 passage from the losing
    runbook through on its own merits, which is exactly the material that must
    not reach the model."""
    hits = [doc_hit(1, 0.74, chunk_id=1), doc_hit(2, 0.66, chunk_id=2)]

    grounded, _ = gate(focus(hits))
    assert {h.document_id for h in grounded} == {1}

    # The wrong order, shown failing, so the reason is not lost.
    grounded_wrong_order, _ = gate(hits)
    assert {h.document_id for h in grounded_wrong_order} == {1, 2}
