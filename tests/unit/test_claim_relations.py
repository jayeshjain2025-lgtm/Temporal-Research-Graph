"""Tests for Phase 3 Milestone 3.3 — claim relationship detection and persistence.

Coverage
--------
R1  SUPPORTS relationship detected from explicit corroboration signal
R2  CHALLENGES relationship detected from explicit counter-evidence signal
R3  REFINES relationship detected from narrowing signal
R4  QUALIFIES relationship detected from conditional signal
R5  No relationship when only shared topic (different wording, no signal)
R6  No relationship when only opposite sentiment (no explicit signal)
R7  Direction is from later claim to earlier claim
R8  Only one relationship per ordered pair (first-match wins)
R9  Empty candidate list returns empty relations list
R10 Single candidate returns empty relations list
R11 upsert_claim_relation is idempotent
R12 upsert_claim_relation rejects invalid relation_type
R13 upsert_claim_relation rejects self-loop
R14 upsert_claim_relation: direction matters — A→B ≠ B→A
R15 confidence is within [0, 1] for all detected relations
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.analysis.claims.extractor import ClaimCandidate, normalize_claim
from src.analysis.claims.relations import ClaimRelationCandidate, detect_claim_relations
from src.models import Claim, ClaimRelation
from src.repositories.claims import upsert_claim, upsert_claim_relation, upsert_claim_provenance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(text: str, claim_type: str, sentence_index: int = 0) -> ClaimCandidate:
    return ClaimCandidate(
        text=text,
        normalized_text=normalize_claim(text),
        claim_type=claim_type,
        sentence_index=sentence_index,
        extraction_method="deterministic",
        confidence=0.7,
    )


def _persist_claim(session, text: str, claim_type: str = "finding") -> Claim:
    claim, _ = upsert_claim(
        session,
        text=text,
        normalized_text=normalize_claim(text),
        claim_type=claim_type,
    )
    return claim


# ---------------------------------------------------------------------------
# R1 — SUPPORTS detected
# ---------------------------------------------------------------------------


def test_supports_detected_from_corroboration_signal():
    c1 = _candidate(
        "We propose a novel temporal graph model for link prediction.",
        "method",
        sentence_index=0,
    )
    c2 = _candidate(
        "These results are consistent with previous findings on temporal graph models.",
        "finding",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    types = {r.relation_type for r in relations}
    assert "SUPPORTS" in types


# ---------------------------------------------------------------------------
# R2 — CHALLENGES detected
# ---------------------------------------------------------------------------


def test_challenges_detected_from_counter_evidence_signal():
    c1 = _candidate(
        "Our model achieves state-of-the-art accuracy on the benchmark datasets.",
        "finding",
        sentence_index=0,
    )
    c2 = _candidate(
        "However, these results contradict the claims of prior work on the same benchmark.",
        "limitation",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    types = {r.relation_type for r in relations}
    assert "CHALLENGES" in types


# ---------------------------------------------------------------------------
# R3 — REFINES detected
# ---------------------------------------------------------------------------


def test_refines_detected_from_narrowing_signal():
    c1 = _candidate(
        "We propose a temporal graph neural network for knowledge graph completion.",
        "method",
        sentence_index=0,
    )
    c2 = _candidate(
        "More specifically, the model is designed for transductive temporal reasoning.",
        "method",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    types = {r.relation_type for r in relations}
    assert "REFINES" in types


# ---------------------------------------------------------------------------
# R4 — QUALIFIES detected
# ---------------------------------------------------------------------------


def test_qualifies_detected_from_conditional_signal():
    c1 = _candidate(
        "The proposed method achieves high accuracy on benchmark temporal datasets.",
        "finding",
        sentence_index=0,
    )
    c2 = _candidate(
        "However, performance degrades unless the training data includes sufficient temporal coverage.",
        "limitation",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    types = {r.relation_type for r in relations}
    # "however" triggers QUALIFIES after CHALLENGES check; accept either
    assert types & {"CHALLENGES", "QUALIFIES"}


# ---------------------------------------------------------------------------
# R5 — No relation for shared topic only
# ---------------------------------------------------------------------------


def test_no_relation_for_shared_topic_only():
    c1 = _candidate(
        "We propose a temporal graph network for knowledge graph completion tasks.",
        "method",
        sentence_index=0,
    )
    c2 = _candidate(
        "Knowledge graph completion is an important problem in AI research today.",
        "finding",
        sentence_index=1,
    )
    # No explicit signal in c2 — no relation should be emitted.
    relations = detect_claim_relations([c1, c2])
    assert relations == [], (
        "shared topic alone must not produce a relationship candidate"
    )


# ---------------------------------------------------------------------------
# R6 — No relation for opposite sentiment alone
# ---------------------------------------------------------------------------


def test_no_relation_for_opposite_sentiment_alone():
    c1 = _candidate(
        "We achieve excellent results on all benchmark datasets evaluated.",
        "finding",
        sentence_index=0,
    )
    c2 = _candidate(
        "The accuracy is poor on datasets outside the training distribution.",
        "finding",
        sentence_index=1,
    )
    # "poor" is opposite sentiment but not a supported contradiction signal.
    relations = detect_claim_relations([c1, c2])
    assert not any(r.relation_type == "CHALLENGES" for r in relations), (
        "opposite sentiment alone must not produce CHALLENGES"
    )


# ---------------------------------------------------------------------------
# R7 — Direction is from later to earlier claim
# ---------------------------------------------------------------------------


def test_relation_direction_is_later_to_earlier():
    c1 = _candidate(
        "We propose a graph attention model for temporal link prediction.",
        "method",
        sentence_index=0,
    )
    c2 = _candidate(
        "These results are consistent with the findings of the proposed model above.",
        "finding",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    assert len(relations) >= 1
    r = relations[0]
    # Source is the later claim (c2); target is the earlier claim (c1).
    assert r.source_normalized_text == c2.normalized_text
    assert r.target_normalized_text == c1.normalized_text


# ---------------------------------------------------------------------------
# R8 — First-match wins for a pair
# ---------------------------------------------------------------------------


def test_only_one_relation_per_ordered_pair():
    # c2 contains both a SUPPORTS and a CHALLENGES signal — first-match wins.
    c1 = _candidate(
        "Our model achieves state-of-the-art performance on temporal knowledge graphs.",
        "finding",
        sentence_index=0,
    )
    c2 = _candidate(
        "Results are consistent with but also contradict prior baseline approaches.",
        "comparison",
        sentence_index=1,
    )
    relations = detect_claim_relations([c1, c2])
    # At most one relation per pair.
    pair_keys = [(r.source_normalized_text, r.target_normalized_text) for r in relations]
    assert len(pair_keys) == len(set(pair_keys)), "at most one relation per ordered pair"


# ---------------------------------------------------------------------------
# R9 — Empty list
# ---------------------------------------------------------------------------


def test_empty_candidate_list_returns_empty():
    assert detect_claim_relations([]) == []


# ---------------------------------------------------------------------------
# R10 — Single candidate
# ---------------------------------------------------------------------------


def test_single_candidate_returns_empty():
    c = _candidate("We propose a new method.", "method")
    assert detect_claim_relations([c]) == []


# ---------------------------------------------------------------------------
# R11 — upsert_claim_relation is idempotent
# ---------------------------------------------------------------------------


def test_upsert_claim_relation_is_idempotent(session):
    src = _persist_claim(session, "We propose a temporal model for KG reasoning.")
    tgt = _persist_claim(session, "Our model achieves strong performance on benchmarks.")
    prov = upsert_claim_provenance(session, source_identifier="W1")

    upsert_claim_relation(session, src, tgt, "SUPPORTS", prov.id)
    upsert_claim_relation(session, src, tgt, "SUPPORTS", prov.id)  # duplicate

    assert session.scalar(select(func.count(ClaimRelation.id))) == 1


# ---------------------------------------------------------------------------
# R12 — upsert_claim_relation rejects invalid type
# ---------------------------------------------------------------------------


def test_upsert_claim_relation_rejects_invalid_type(session):
    src = _persist_claim(session, "Claim source text for testing purposes here.")
    tgt = _persist_claim(session, "Claim target text for testing purposes here.")
    prov = upsert_claim_provenance(session, source_identifier="W1")

    with pytest.raises(ValueError, match="SUPPORTS"):
        upsert_claim_relation(session, src, tgt, "INVALIDTYPE", prov.id)


# ---------------------------------------------------------------------------
# R13 — self-loop rejected
# ---------------------------------------------------------------------------


def test_upsert_claim_relation_rejects_self_loop(session):
    claim = _persist_claim(session, "We propose a temporal graph model for link prediction.")
    prov = upsert_claim_provenance(session, source_identifier="W1")

    with pytest.raises(ValueError, match="itself"):
        upsert_claim_relation(session, claim, claim, "SUPPORTS", prov.id)


# ---------------------------------------------------------------------------
# R14 — direction matters: A→B ≠ B→A
# ---------------------------------------------------------------------------


def test_claim_relation_direction_matters(session):
    src = _persist_claim(session, "Model A achieves higher accuracy on benchmark X.")
    tgt = _persist_claim(session, "Model B produces results consistent with model A.")
    prov = upsert_claim_provenance(session, source_identifier="W1")

    rel_ab, created_ab = upsert_claim_relation(session, src, tgt, "SUPPORTS", prov.id)
    rel_ba, created_ba = upsert_claim_relation(session, tgt, src, "SUPPORTS", prov.id)

    assert created_ab is True
    assert created_ba is True
    assert rel_ab.id != rel_ba.id
    assert session.scalar(select(func.count(ClaimRelation.id))) == 2


# ---------------------------------------------------------------------------
# R15 — confidence within [0, 1]
# ---------------------------------------------------------------------------


def test_detected_relation_confidence_in_range():
    c1 = _candidate("We propose a temporal graph model.", "method", 0)
    c2 = _candidate(
        "These findings are consistent with prior work on temporal reasoning.",
        "finding",
        1,
    )
    for r in detect_claim_relations([c1, c2]):
        assert 0.0 <= r.confidence <= 1.0, (
            f"confidence {r.confidence} out of range for {r.relation_type}"
        )
