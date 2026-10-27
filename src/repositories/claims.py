"""Claim persistence helpers — Phase 3, Milestone 3.2.

All functions follow the same ``get_or_create`` / ``provenance()`` pattern
established in ``src/repositories/upsert.py``.

Public API
----------
upsert_claim(session, text, normalized_text, claim_type)  -> Claim
link_paper_claim(session, paper, claim, relation_type, provenance_id) -> None
upsert_claim_provenance(session, *, source_identifier, ...) -> Provenance
upsert_claim_relation(session, source, target, relation_type, provenance_id) -> None
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Claim, ClaimRelation, PaperClaim, Paper, Provenance
from src.repositories.upsert import get_or_create


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

# Valid values from the CHECK constraint in 001_initial_schema.sql
_VALID_SOURCE_TYPES = frozenset({"metadata", "abstract", "full_text", "inferred"})
_VALID_EXTRACTION_METHODS = frozenset({"deterministic", "manual", "NLP", "inferred"})


def upsert_claim_provenance(
    session: Session,
    *,
    source_identifier: str,
    source_url: str | None = None,
    source_type: str = "abstract",
    evidence_text: str | None = None,
    extraction_method: str = "deterministic",
    confidence: float | None = None,
) -> Provenance:
    """Create and flush a new provenance record for a claim extraction event.

    A fresh row is always created (provenance is an append-only audit log).
    ``confidence`` is a heuristic estimate; callers must not treat it as
    a calibrated scientific probability.

    Parameters
    ----------
    source_identifier:
        The paper's ``external_id`` (e.g. an OpenAlex work ID).
    source_type:
        One of ``metadata``, ``abstract``, ``full_text``, ``inferred``.
    extraction_method:
        One of ``deterministic``, ``manual``, ``NLP``, ``inferred``.
    confidence:
        Heuristic score in [0, 1], or ``None`` when unavailable.

    Raises
    ------
    ValueError
        If ``source_type`` or ``extraction_method`` is not in the allowed set.
    """
    if source_type not in _VALID_SOURCE_TYPES:
        raise ValueError(f"source_type {source_type!r} not in {_VALID_SOURCE_TYPES}")
    if extraction_method not in _VALID_EXTRACTION_METHODS:
        raise ValueError(f"extraction_method {extraction_method!r} not in {_VALID_EXTRACTION_METHODS}")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence {confidence} must be in [0, 1]")

    prov = Provenance(
        source_type=source_type,
        source_identifier=source_identifier,
        source_url=source_url,
        evidence_text=evidence_text,
        extraction_method=extraction_method,
        confidence=confidence,
    )
    session.add(prov)
    session.flush()
    return prov


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def upsert_claim(
    session: Session,
    *,
    text: str,
    normalized_text: str,
    claim_type: str | None = None,
) -> tuple[Claim, bool]:
    """Return the canonical ``Claim`` for *normalized_text*, creating it if absent.

    Deduplication is by exact ``normalized_text`` match (the UNIQUE column).
    When an existing claim is found, ``text`` and ``claim_type`` are NOT
    overwritten; the original extraction is preserved.

    Returns
    -------
    (Claim, created)
        ``created`` is ``True`` when a new row was inserted.
    """
    if not text or not normalized_text:
        raise ValueError("text and normalized_text must be non-empty strings")

    existing = session.scalar(select(Claim).where(Claim.normalized_text == normalized_text))
    if existing is not None:
        return existing, False

    claim = Claim(text=text, normalized_text=normalized_text, claim_type=claim_type)
    session.add(claim)
    session.flush()
    return claim, True


# ---------------------------------------------------------------------------
# Paper → Claim links
# ---------------------------------------------------------------------------

# Valid values from the CHECK constraint on paper_claims.relation_type
_VALID_PAPER_CLAIM_RELATIONS = frozenset({"MAKES_CLAIM", "SUPPORTS", "CONTRADICTS"})


def link_paper_claim(
    session: Session,
    paper: Paper,
    claim: Claim,
    relation_type: str,
    provenance_id: int | None,
) -> None:
    """Create a ``PaperClaim`` link if one does not already exist.

    Idempotent: calling twice with the same arguments is safe.

    Parameters
    ----------
    relation_type:
        One of ``MAKES_CLAIM``, ``SUPPORTS``, ``CONTRADICTS``.

    Raises
    ------
    ValueError
        If ``relation_type`` is not in the allowed set.
    """
    if relation_type not in _VALID_PAPER_CLAIM_RELATIONS:
        raise ValueError(
            f"relation_type {relation_type!r} not in {_VALID_PAPER_CLAIM_RELATIONS}"
        )
    get_or_create(
        session,
        PaperClaim,
        {"paper_id": paper.id, "claim_id": claim.id, "relation_type": relation_type},
        {"provenance_id": provenance_id},
    )


# ---------------------------------------------------------------------------
# Claim → Claim relationships
# ---------------------------------------------------------------------------

# Allowed types for claim_relations (no DB CHECK constraint, enforced here).
_VALID_CLAIM_RELATIONS = frozenset({"SUPPORTS", "CHALLENGES", "REFINES", "QUALIFIES"})


def upsert_claim_relation(
    session: Session,
    source_claim: Claim,
    target_claim: Claim,
    relation_type: str,
    provenance_id: int | None,
) -> tuple[ClaimRelation, bool]:
    """Return the ``ClaimRelation`` for (source, target, type), creating if absent.

    Idempotent via the ``uq_claim_relation`` unique constraint added in
    migration 004.  Direction is meaningful: ``source SUPPORTS target``
    is not the same relationship as ``target SUPPORTS source``.

    Parameters
    ----------
    relation_type:
        One of ``SUPPORTS``, ``CHALLENGES``, ``REFINES``, ``QUALIFIES``.

    Raises
    ------
    ValueError
        When relation_type is not in the allowed set, or when source and
        target are the same claim (self-loops are not meaningful).
    """
    if relation_type not in _VALID_CLAIM_RELATIONS:
        raise ValueError(
            f"relation_type {relation_type!r} not in {_VALID_CLAIM_RELATIONS}"
        )
    if source_claim.id == target_claim.id:
        raise ValueError("A claim cannot have a relationship with itself")

    return get_or_create(
        session,
        ClaimRelation,
        {
            "source_claim_id": source_claim.id,
            "target_claim_id": target_claim.id,
            "relation_type": relation_type,
        },
        {"provenance_id": provenance_id},
    )
