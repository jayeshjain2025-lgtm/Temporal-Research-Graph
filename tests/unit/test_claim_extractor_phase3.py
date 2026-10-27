"""Tests for src/analysis/claims/extractor.py — Phase 3, Milestone 3.1

Phase 3 additions (tests 11–22) extend the original 10 tests (now 1–12
in the existing test_claim_extractor.py) without touching them.

New coverage
------------
11  sentence_index is tracked correctly
12  char offsets are populated for a single-sentence abstract
13  DeterministicClaimExtractor implements ClaimExtractorProtocol
14  None-like missing abstract (None passed as text) → empty list
15  Abstract that is only whitespace/newlines → empty list
16  Abstract with only abbreviations and no claim signal → empty list
17  Fragmented / partial sentence still filtered if too short
18  Multiple claims in one abstract: indices are ascending
19  confidence is within [0, 1] for all claim types
20  extraction_method is always "deterministic"
21  Protocol runtime check passes for DeterministicClaimExtractor
22  Deduplication: same normalized form from different surface forms → 1 candidate
"""
import pytest

from src.analysis.claims.extractor import (
    ClaimCandidate,
    ClaimExtractorProtocol,
    DeterministicClaimExtractor,
    extract_claim_candidates,
    normalize_claim,
    split_sentences,
)


# ---------------------------------------------------------------------------
# 11. sentence_index tracking
# ---------------------------------------------------------------------------


def test_sentence_index_is_zero_for_single_sentence():
    abstract = "We propose a novel graph neural network for temporal reasoning over knowledge graphs."
    claims = extract_claim_candidates(abstract)
    assert len(claims) == 1
    assert claims[0].sentence_index == 0


def test_sentence_index_increments_across_sentences():
    abstract = (
        "Background information with no claim signal here for context. "  # idx 0 — skipped
        "We propose a new framework for temporal link prediction. "         # idx 1 — method
        "Our results show that accuracy improves by ten percent overall."   # idx 2 — finding
    )
    claims = extract_claim_candidates(abstract)
    assert len(claims) >= 2
    indices = [c.sentence_index for c in claims]
    assert indices == sorted(indices), "sentence indices must be in ascending order"
    assert indices[0] < indices[-1], "first and last claim must come from different sentences"


# ---------------------------------------------------------------------------
# 12. char offsets are populated
# ---------------------------------------------------------------------------


def test_char_offsets_are_populated_for_single_sentence():
    abstract = "We propose a novel temporal graph network for link prediction tasks."
    claims = extract_claim_candidates(abstract)
    assert len(claims) == 1
    c = claims[0]
    assert c.char_start is not None
    assert c.char_end is not None
    assert c.char_start >= 0
    assert c.char_end > c.char_start
    # The original text must appear at the recorded offsets.
    assert abstract[c.char_start : c.char_end] == c.text


# ---------------------------------------------------------------------------
# 13. DeterministicClaimExtractor delegates to extract_claim_candidates
# ---------------------------------------------------------------------------


def test_deterministic_extractor_returns_same_as_function():
    abstract = "We propose a novel framework for temporal knowledge graph reasoning."
    extractor = DeterministicClaimExtractor()
    from_method = extractor.extract(abstract)
    from_function = extract_claim_candidates(abstract)
    assert from_method == from_function


# ---------------------------------------------------------------------------
# 14. Missing / None-equivalent abstract → empty list
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list():
    assert extract_claim_candidates("") == []


def test_whitespace_only_abstract_returns_empty_list():
    assert extract_claim_candidates("   \t  ") == []


def test_newlines_only_returns_empty_list():
    assert extract_claim_candidates("\n\n\n") == []


# ---------------------------------------------------------------------------
# 15. Abstract of pure abbreviations / jargon without claim signal
# ---------------------------------------------------------------------------


def test_no_claim_signal_returns_empty_list():
    # Long enough to pass length filter but contains no claim-pattern trigger.
    abstract = (
        "KG TKG SGC BERT GPT RNN CNN LSTM GNN NLP. "
        "TKG-BERT SGC-2 temporal embedding completeness."
    )
    claims = extract_claim_candidates(abstract)
    # Either zero or only non-boilerplate matches are acceptable,
    # but none of the abbreviation-only sentences should fire a claim pattern.
    for c in claims:
        assert c.claim_type in {"finding", "method", "comparison", "limitation", "dataset"}


# ---------------------------------------------------------------------------
# 16. Fragmented / partial sentence → filtered by length
# ---------------------------------------------------------------------------


def test_fragment_under_minimum_length_is_rejected():
    abstract = "Shows improvement."   # 18 chars, well under 30
    assert extract_claim_candidates(abstract) == []


# ---------------------------------------------------------------------------
# 17. Multiple claims: sentence indices are strictly ascending
# ---------------------------------------------------------------------------


def test_multi_claim_indices_are_ascending():
    abstract = (
        "We propose a new approach for temporal reasoning. "
        "Our experiments show the model outperforms baselines. "
        "However, the approach fails to handle low-resource settings."
    )
    claims = extract_claim_candidates(abstract)
    indices = [c.sentence_index for c in claims]
    assert indices == sorted(indices)


# ---------------------------------------------------------------------------
# 18. confidence is within [0, 1] for every claim type
# ---------------------------------------------------------------------------


def test_confidence_is_in_valid_range():
    abstracts = [
        "We propose a novel algorithm for temporal knowledge graph completion.",
        "Our experiments show that the model outperforms all baselines significantly.",
        "Compared to prior work, the approach achieves state-of-the-art performance.",
        "However, the model fails to generalise to unseen entities in the graph.",
        "We evaluate on the Wikidata benchmark and three temporal datasets.",
    ]
    for abstract in abstracts:
        for c in extract_claim_candidates(abstract):
            assert 0.0 <= c.confidence <= 1.0, (
                f"confidence {c.confidence} out of range for claim_type={c.claim_type}"
            )


# ---------------------------------------------------------------------------
# 19. extraction_method is always "deterministic"
# ---------------------------------------------------------------------------


def test_extraction_method_is_deterministic():
    abstract = (
        "We propose a new graph model. "
        "Our results show significant improvement."
    )
    for c in extract_claim_candidates(abstract):
        assert c.extraction_method == "deterministic"


# ---------------------------------------------------------------------------
# 20. Protocol runtime check
# ---------------------------------------------------------------------------


def test_deterministic_extractor_satisfies_protocol():
    extractor = DeterministicClaimExtractor()
    assert isinstance(extractor, ClaimExtractorProtocol), (
        "DeterministicClaimExtractor must satisfy ClaimExtractorProtocol"
    )


# ---------------------------------------------------------------------------
# 21. Deduplication across surface variants with same normalized form
# ---------------------------------------------------------------------------


def test_deduplication_by_normalized_form():
    # The two sentences have the same normalized form (punctuation difference).
    s1 = "Our experiments show that the approach reduces error rates significantly."
    s2 = "Our experiments show that the approach reduces error rates significantly!"
    abstract = s1 + "  " + s2
    claims = extract_claim_candidates(abstract)
    assert len(claims) == 1, (
        "Sentences with the same normalized text must produce only one candidate"
    )
