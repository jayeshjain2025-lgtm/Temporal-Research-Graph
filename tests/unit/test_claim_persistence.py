"""Tests for Phase 3 Milestone 3.2 — claim persistence and provenance.

Coverage
--------
P1  upsert_claim creates a new row and returns created=True
P2  upsert_claim returns created=False and same object on duplicate normalized_text
P3  upsert_claim rejects empty text
P4  upsert_claim rejects empty normalized_text
P5  link_paper_claim is idempotent (two calls → one row)
P6  link_paper_claim rejects invalid relation_type
P7  upsert_claim_provenance stores evidence_text and confidence
P8  upsert_claim_provenance rejects invalid source_type
P9  upsert_claim_provenance rejects invalid extraction_method
P10 upsert_claim_provenance rejects out-of-range confidence
P11 Multiple papers reporting the same claim → one Claim row, two PaperClaim rows
P12 extract_and_persist_claims skips paper with no abstract
P13 extract_and_persist_claims is idempotent (run twice → same DB counts)
P14 extract_and_persist_claims populates claims + provenance correctly
P15 PaperClaim foreign key: inserting with nonexistent paper_id raises IntegrityError
P16 claim_type stored on Claim row
"""
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.analysis.claims.pipeline import extract_and_persist_claims
from src.models import Claim, PaperClaim, Provenance, Paper
from src.repositories.claims import (
    link_paper_claim,
    upsert_claim,
    upsert_claim_provenance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paper(session, external_id="W999", abstract="We propose a new method."):
    p = Paper(
        external_id=external_id,
        title="Test Paper",
        abstract=abstract,
        publication_date=date(2023, 1, 1),
        publication_year=2023,
        source="test",
    )
    session.add(p)
    session.flush()
    return p


def _make_claim(session, text="Our model improves accuracy.", norm=None):
    from src.analysis.claims.extractor import normalize_claim
    normalized = norm or normalize_claim(text)
    claim, created = upsert_claim(session, text=text, normalized_text=normalized, claim_type="finding")
    return claim, created


# ---------------------------------------------------------------------------
# P1 — upsert_claim creates new row
# ---------------------------------------------------------------------------


def test_upsert_claim_creates_new_row(session):
    claim, created = _make_claim(session)
    assert created is True
    assert session.scalar(select(func.count(Claim.id))) == 1
    assert claim.id is not None


# ---------------------------------------------------------------------------
# P2 — upsert_claim deduplicates by normalized_text
# ---------------------------------------------------------------------------


def test_upsert_claim_deduplicates_by_normalized_text(session):
    _, _ = _make_claim(session, text="Our model improves accuracy.", norm="our model improves accuracy")
    claim2, created2 = upsert_claim(
        session,
        text="Our model improves accuracy!",       # different surface form
        normalized_text="our model improves accuracy",  # same normalised form
        claim_type="finding",
    )
    assert created2 is False
    assert session.scalar(select(func.count(Claim.id))) == 1
    # Original text is preserved
    assert claim2.text == "Our model improves accuracy."


# ---------------------------------------------------------------------------
# P3 — empty text rejected
# ---------------------------------------------------------------------------


def test_upsert_claim_rejects_empty_text(session):
    with pytest.raises(ValueError, match="non-empty"):
        upsert_claim(session, text="", normalized_text="some norm", claim_type=None)


# ---------------------------------------------------------------------------
# P4 — empty normalized_text rejected
# ---------------------------------------------------------------------------


def test_upsert_claim_rejects_empty_normalized_text(session):
    with pytest.raises(ValueError, match="non-empty"):
        upsert_claim(session, text="Some text here.", normalized_text="", claim_type=None)


# ---------------------------------------------------------------------------
# P5 — link_paper_claim is idempotent
# ---------------------------------------------------------------------------


def test_link_paper_claim_is_idempotent(session):
    paper = _make_paper(session)
    claim, _ = _make_claim(session)
    prov = upsert_claim_provenance(session, source_identifier=paper.external_id)

    link_paper_claim(session, paper, claim, "MAKES_CLAIM", prov.id)
    link_paper_claim(session, paper, claim, "MAKES_CLAIM", prov.id)  # second call

    assert session.scalar(select(func.count(PaperClaim.id))) == 1


# ---------------------------------------------------------------------------
# P6 — link_paper_claim rejects invalid relation_type
# ---------------------------------------------------------------------------


def test_link_paper_claim_rejects_invalid_relation_type(session):
    paper = _make_paper(session)
    claim, _ = _make_claim(session)
    prov = upsert_claim_provenance(session, source_identifier=paper.external_id)

    with pytest.raises(ValueError, match="MAKES_CLAIM"):
        link_paper_claim(session, paper, claim, "INVALID_TYPE", prov.id)


# ---------------------------------------------------------------------------
# P7 — provenance stores evidence_text and confidence
# ---------------------------------------------------------------------------


def test_provenance_stores_evidence_and_confidence(session):
    prov = upsert_claim_provenance(
        session,
        source_identifier="W123",
        evidence_text="We propose a novel approach.",
        confidence=0.75,
    )
    assert prov.id is not None
    assert prov.evidence_text == "We propose a novel approach."
    assert abs(prov.confidence - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# P8 — provenance rejects invalid source_type
# ---------------------------------------------------------------------------


def test_provenance_rejects_invalid_source_type(session):
    with pytest.raises(ValueError, match="source_type"):
        upsert_claim_provenance(session, source_identifier="W1", source_type="html")


# ---------------------------------------------------------------------------
# P9 — provenance rejects invalid extraction_method
# ---------------------------------------------------------------------------


def test_provenance_rejects_invalid_extraction_method(session):
    with pytest.raises(ValueError, match="extraction_method"):
        upsert_claim_provenance(
            session, source_identifier="W1", extraction_method="gpt4"
        )


# ---------------------------------------------------------------------------
# P10 — provenance rejects out-of-range confidence
# ---------------------------------------------------------------------------


def test_provenance_rejects_out_of_range_confidence(session):
    with pytest.raises(ValueError, match="confidence"):
        upsert_claim_provenance(session, source_identifier="W1", confidence=1.5)


# ---------------------------------------------------------------------------
# P11 — multiple papers can report the same claim
# ---------------------------------------------------------------------------


def test_multiple_papers_same_claim(session):
    p1 = _make_paper(session, external_id="W1")
    p2 = _make_paper(session, external_id="W2")
    claim, _ = _make_claim(session)

    prov1 = upsert_claim_provenance(session, source_identifier="W1")
    prov2 = upsert_claim_provenance(session, source_identifier="W2")

    link_paper_claim(session, p1, claim, "MAKES_CLAIM", prov1.id)
    link_paper_claim(session, p2, claim, "SUPPORTS", prov2.id)

    assert session.scalar(select(func.count(Claim.id))) == 1
    assert session.scalar(select(func.count(PaperClaim.id))) == 2


# ---------------------------------------------------------------------------
# P12 — pipeline skips paper with no abstract
# ---------------------------------------------------------------------------


def test_pipeline_skips_no_abstract(session):
    paper = _make_paper(session, abstract=None)
    result = extract_and_persist_claims(session, paper)
    assert result.skipped_no_abstract is True
    assert result.claims_created == 0
    assert session.scalar(select(func.count(Claim.id))) == 0


def test_pipeline_skips_whitespace_abstract(session):
    paper = _make_paper(session, abstract="   \n  ")
    result = extract_and_persist_claims(session, paper)
    assert result.skipped_no_abstract is True


# ---------------------------------------------------------------------------
# P13 — pipeline is idempotent
# ---------------------------------------------------------------------------


def test_pipeline_is_idempotent(session):
    abstract = (
        "We propose a novel temporal graph model for link prediction. "
        "Our results show significant improvements over baseline methods."
    )
    paper = _make_paper(session, abstract=abstract)

    r1 = extract_and_persist_claims(session, paper)
    session.flush()

    claim_count_1 = session.scalar(select(func.count(Claim.id)))
    link_count_1 = session.scalar(select(func.count(PaperClaim.id)))

    r2 = extract_and_persist_claims(session, paper)
    session.flush()

    claim_count_2 = session.scalar(select(func.count(Claim.id)))
    link_count_2 = session.scalar(select(func.count(PaperClaim.id)))

    assert claim_count_1 == claim_count_2, "second run must not create duplicate claims"
    assert link_count_1 == link_count_2, "second run must not create duplicate links"
    assert r2.claims_created == 0, "second run must find all claims already existing"
    assert r2.claims_reused == r1.claims_created, "all claims from first run must be reused"


# ---------------------------------------------------------------------------
# P14 — pipeline populates claims and provenance
# ---------------------------------------------------------------------------


def test_pipeline_creates_claims_and_provenance(session):
    abstract = "We propose a novel approach for temporal knowledge graph reasoning."
    paper = _make_paper(session, abstract=abstract)

    result = extract_and_persist_claims(session, paper)

    assert result.candidates_found >= 1
    assert result.claims_created >= 1
    assert result.errors == []

    claim_count = session.scalar(select(func.count(Claim.id)))
    prov_count = session.scalar(select(func.count(Provenance.id)))
    link_count = session.scalar(select(func.count(PaperClaim.id)))

    assert claim_count >= 1
    assert prov_count >= 1
    assert link_count >= 1


# ---------------------------------------------------------------------------
# P15 — PaperClaim FK enforced
# ---------------------------------------------------------------------------


def test_paper_claim_fk_enforced(session):
    # SQLite does not enforce FK constraints by default; enable them explicitly.
    session.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys = ON"))
    claim, _ = _make_claim(session)
    # Attempt to insert a PaperClaim row with a nonexistent paper_id.
    bad_link = PaperClaim(paper_id=99999, claim_id=claim.id, relation_type="MAKES_CLAIM")
    session.add(bad_link)
    with pytest.raises(IntegrityError):
        session.flush()


# ---------------------------------------------------------------------------
# P16 — claim_type stored on Claim row
# ---------------------------------------------------------------------------


def test_claim_type_stored_on_claim(session):
    abstract = "We propose a new architecture for temporal link prediction tasks."
    paper = _make_paper(session, abstract=abstract)
    extract_and_persist_claims(session, paper)

    claims = session.scalars(select(Claim)).all()
    assert all(c.claim_type is not None for c in claims), (
        "every extracted claim must have a claim_type"
    )
