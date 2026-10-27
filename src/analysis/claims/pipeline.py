"""Claim extraction, persistence, and corpus-level relation pipeline — Phase 3.

Orchestrates the full extract → normalise → upsert → link → detect-relations
workflow.  Designed to be called inside the caller's transaction; does not commit.

Public API
----------
ClaimPipelineResult    dataclass
extract_and_persist_claims(session, paper, extractor)  -> ClaimPipelineResult
run_corpus_relation_pass(session, paper_ids=None)      -> dict[str, int]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.claims.extractor import (
    ClaimCandidate,
    ClaimExtractorProtocol,
    DeterministicClaimExtractor,
    extract_claim_candidates,
)
from src.analysis.claims.relations import detect_claim_relations
from src.models import Claim, Paper, PaperClaim, Provenance
from src.repositories.claims import (
    link_paper_claim,
    upsert_claim,
    upsert_claim_provenance,
    upsert_claim_relation,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ClaimPipelineResult:
    """Summary of one paper's claim extraction pass.

    Attributes
    ----------
    paper_external_id:
        The paper's ``external_id`` (e.g. an OpenAlex work ID).
    candidates_found:
        Number of candidate sentences the extractor produced.
    claims_created:
        Number of new canonical ``Claim`` rows inserted.
    claims_reused:
        Number of existing canonical ``Claim`` rows matched by normalised text.
    links_created:
        Number of new ``PaperClaim`` rows inserted.
    relations_created:
        Number of new ``ClaimRelation`` rows created for intra-paper pairs.
    skipped_no_abstract:
        ``True`` when the paper had no abstract (no extraction attempted).
    errors:
        Any non-fatal issues encountered (e.g. provenance validation errors).
    """

    paper_external_id: str
    candidates_found: int = 0
    claims_created: int = 0
    claims_reused: int = 0
    links_created: int = 0
    relations_created: int = 0
    skipped_no_abstract: bool = False
    errors: list[str] = field(default_factory=list)


def extract_and_persist_claims(
    session: Session,
    paper: Paper,
    extractor: ClaimExtractorProtocol | None = None,
) -> ClaimPipelineResult:
    """Extract candidate claims from *paper*, persist them, and detect
    intra-paper claim relations.

    The function is idempotent: running it twice on the same paper produces
    the same database state.  All writes are flushed to the session but not
    committed; the caller controls the transaction boundary.

    Missing abstracts
    -----------------
    When ``paper.abstract`` is ``None`` or blank, extraction is skipped and
    ``result.skipped_no_abstract`` is ``True``.  This is not an error.

    Intra-paper relations
    ---------------------
    After all claims for this paper are persisted, ``detect_claim_relations``
    is run on the extracted candidates.  Each detected relation is persisted
    via ``upsert_claim_relation`` with a provenance record referencing the
    source paper.  Self-relations are skipped.  This covers relations between
    claims from the *same* abstract (e.g. a "however" sentence qualifying an
    earlier finding sentence).  Cross-paper relations require the separate
    :func:`run_corpus_relation_pass`.

    Parameters
    ----------
    session:
        An open SQLAlchemy session.
    paper:
        A ``Paper`` ORM instance that has been flushed (``paper.id`` is set).
    extractor:
        A :class:`ClaimExtractorProtocol` instance.  Defaults to
        :class:`DeterministicClaimExtractor` when ``None``.

    Returns
    -------
    ClaimPipelineResult
    """
    if extractor is None:
        extractor = DeterministicClaimExtractor()

    result = ClaimPipelineResult(paper_external_id=paper.external_id)

    abstract = paper.abstract
    if not abstract or not abstract.strip():
        result.skipped_no_abstract = True
        return result

    candidates: list[ClaimCandidate] = extractor.extract(abstract)
    result.candidates_found = len(candidates)

    # Map normalized_text -> persisted Claim for intra-paper relation step.
    persisted: dict[str, Claim] = {}

    for candidate in candidates:
        try:
            # 1. Create/reuse the canonical claim row.
            claim, created = upsert_claim(
                session,
                text=candidate.text,
                normalized_text=candidate.normalized_text,
                claim_type=candidate.claim_type,
            )
            if created:
                result.claims_created += 1
            else:
                result.claims_reused += 1

            # 2. Create a provenance record for this specific extraction event.
            prov = upsert_claim_provenance(
                session,
                source_identifier=paper.external_id,
                source_url=paper.source_url,
                source_type="abstract",
                evidence_text=candidate.text,
                extraction_method=candidate.extraction_method,
                confidence=candidate.confidence,
            )

            # 3. Link the paper to the claim with relation MAKES_CLAIM.
            link_paper_claim(session, paper, claim, "MAKES_CLAIM", prov.id)
            result.links_created += 1

            persisted[candidate.normalized_text] = claim

        except Exception as exc:  # noqa: BLE001
            # Non-fatal: record the error and continue with remaining candidates.
            result.errors.append(
                f"claim={candidate.normalized_text[:60]!r}: {exc}"
            )

    # 4. Detect and persist intra-paper claim relations.
    if len(candidates) >= 2:
        relation_candidates = detect_claim_relations(candidates)
        for rc in relation_candidates:
            src_claim = persisted.get(rc.source_normalized_text)
            tgt_claim = persisted.get(rc.target_normalized_text)
            if src_claim is None or tgt_claim is None:
                continue
            if src_claim.id == tgt_claim.id:
                continue  # Guard: never persist self-relations.
            try:
                rel_prov = upsert_claim_provenance(
                    session,
                    source_identifier=paper.external_id,
                    source_url=paper.source_url,
                    source_type="abstract",
                    evidence_text=rc.evidence_text,
                    extraction_method="deterministic",
                    confidence=rc.confidence,
                )
                _, created = upsert_claim_relation(
                    session, src_claim, tgt_claim, rc.relation_type, rel_prov.id
                )
                if created:
                    result.relations_created += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(
                    f"relation {rc.relation_type} "
                    f"{rc.source_normalized_text[:40]!r}->{rc.target_normalized_text[:40]!r}: {exc}"
                )

    return result


def run_corpus_relation_pass(
    session: Session,
    paper_ids: set[int] | None = None,
) -> dict[str, int]:
    """Detect and persist cross-paper claim relations for a corpus.

    Strategy
    --------
    For each paper that has persisted claims, reload its ``ClaimCandidate``
    proxies from the database (using stored claim text and type), then run
    ``detect_claim_relations`` across all claims from *every* paper in the
    corpus combined, ordered by publication year then claim id.

    This detects relations where a later paper's sentence explicitly references
    an earlier finding using a supported signal (e.g. "consistent with",
    "contradicts", "however").

    Design constraints
    ------------------
    * Does NOT pair claims from papers that share no common publication-year
      ordering — all pairs are considered, but the later sentence must contain
      the signal.
    * Only supported lexical signals trigger a relationship; shared topics or
      words alone do NOT.
    * All persisted relations are idempotent (unique constraint on
      source_claim_id, target_claim_id, relation_type).
    * Self-relations are rejected before persistence.

    Parameters
    ----------
    session:
        An open SQLAlchemy session.
    paper_ids:
        Optional set of paper IDs to restrict the pass to (corpus scoping).
        When ``None``, all papers in the database are considered.

    Returns
    -------
    dict with counts:
        ``relations_created``: new ClaimRelation rows inserted.
        ``relations_skipped``: duplicates or self-relations skipped.
        ``errors``: non-fatal error count.
    """
    counts = {"relations_created": 0, "relations_skipped": 0, "errors": 0}

    # Load all (paper, claim) rows in publication-year order.
    stmt = (
        select(
            Paper.id.label("paper_id"),
            Paper.external_id.label("paper_external_id"),
            Paper.source_url.label("paper_source_url"),
            Paper.publication_year,
            Claim.id.label("claim_id"),
            Claim.text,
            Claim.normalized_text,
            Claim.claim_type,
            Provenance.evidence_text,
            Provenance.confidence,
            Provenance.extraction_method,
        )
        .join(PaperClaim, PaperClaim.paper_id == Paper.id)
        .join(Claim, Claim.id == PaperClaim.claim_id)
        .outerjoin(Provenance, PaperClaim.provenance_id == Provenance.id)
        .where(PaperClaim.relation_type == "MAKES_CLAIM")
        .order_by(
            Paper.publication_year.asc().nulls_last(),
            Paper.id.asc(),
            Claim.id.asc(),
        )
    )

    if paper_ids is not None:
        if not paper_ids:
            return counts
        stmt = stmt.where(Paper.id.in_(paper_ids))

    rows = session.execute(stmt).all()

    if len(rows) < 2:
        return counts

    # Build ClaimCandidate proxies from DB rows, maintaining encounter order.
    # sentence_index is approximated by DB insertion order (claim.id within paper).
    seen_norm: set[str] = set()
    ordered_candidates: list[ClaimCandidate] = []
    # paper_external_id per normalized_text (for provenance)
    claim_paper_map: dict[str, tuple[str, str | None]] = {}  # norm -> (ext_id, source_url)

    for i, row in enumerate(rows):
        norm = row.normalized_text
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        ordered_candidates.append(
            ClaimCandidate(
                text=row.text,
                normalized_text=norm,
                claim_type=row.claim_type or "finding",
                sentence_index=i,  # global encounter order across papers
                extraction_method=row.extraction_method or "deterministic",
                confidence=row.confidence or 0.65,
            )
        )
        claim_paper_map[norm] = (row.paper_external_id, row.paper_source_url)

    # Detect relations across all candidates in corpus order.
    relation_candidates = detect_claim_relations(ordered_candidates)

    # Build a lookup: normalized_text -> Claim ORM object in chunks of 500
    all_norms = [c.normalized_text for c in ordered_candidates]
    claim_lookup: dict[str, Claim] = {}
    chunk_size = 500
    for idx in range(0, len(all_norms), chunk_size):
        batch = all_norms[idx : idx + chunk_size]
        for claim_obj in session.scalars(
            select(Claim).where(Claim.normalized_text.in_(batch))
        ).all():
            claim_lookup[claim_obj.normalized_text] = claim_obj

    for rc in relation_candidates:
        src_claim = claim_lookup.get(rc.source_normalized_text)
        tgt_claim = claim_lookup.get(rc.target_normalized_text)
        if src_claim is None or tgt_claim is None:
            counts["errors"] += 1
            continue
        if src_claim.id == tgt_claim.id:
            counts["relations_skipped"] += 1
            continue

        # Use the source claim's paper for provenance.
        src_paper_ext, src_source_url = claim_paper_map.get(
            rc.source_normalized_text, ("unknown", None)
        )

        try:
            rel_prov = upsert_claim_provenance(
                session,
                source_identifier=src_paper_ext,
                source_url=src_source_url,
                source_type="abstract",
                evidence_text=rc.evidence_text,
                extraction_method="deterministic",
                confidence=rc.confidence,
            )
            _, created = upsert_claim_relation(
                session, src_claim, tgt_claim, rc.relation_type, rel_prov.id
            )
            if created:
                counts["relations_created"] += 1
            else:
                counts["relations_skipped"] += 1
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug(
                "Skipped relation %s %s->%s: %s",
                rc.relation_type,
                rc.source_normalized_text[:40],
                rc.target_normalized_text[:40],
                exc,
            )
            counts["errors"] += 1

    return counts
