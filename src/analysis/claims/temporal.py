"""Temporal claim evolution analysis — Phase 3, Milestone 3.4.

Provides temporal reasoning queries over research claims, tracking how
claims emerge, get corroborated, get challenged, or exhibit observation gaps
over publication years.

Design principles
-----------------
1. Separation of times:
   * Publication time: ``Paper.publication_year`` and ``Paper.publication_date``.
   * System observation time: ``Provenance.observed_at``.
   * Validity intervals: Never fabricated or inferred from publication years.
2. Absence in corpus:
   Absence of a claim or relationship in a given year indicates only that it was
   not observed in the bounded corpus for that year; it is NOT proof that the claim
   is false or that the relationship ceased to exist.
3. Corpus scoping:
   Reuses ``corpus_paper_ids`` and ``paper_ids`` set filtering identical to Phase 2.

Public API
----------
claim_history(session, claim_id) -> dict
papers_reporting_claim(session, claim_id, ...) -> list[dict]
papers_challenging_claim(session, claim_id, ...) -> list[dict]
claims_timeline(session, start_year, end_year, ...) -> dict[int, dict]
newly_observed_claims(session, start_year, end_year, ...) -> list[dict]
newly_observed_relations(session, start_year, end_year, ...) -> list[dict]
claim_observation_gaps(session, start_year, end_year, ...) -> list[dict]
claim_temporal_summary(session, start_year, end_year, ...) -> dict
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis.evolution.corpus_filter import corpus_paper_ids
from src.models import Claim, ClaimRelation, Paper, PaperClaim, Provenance


def claim_history(session: Session, claim_id: int) -> dict[str, Any] | None:
    """Retrieve the full chronological history and provenance of a claim.

    Returns the claim metadata, all papers linking to it (with publication
    time, relation type, and provenance evidence), and incoming/outgoing
    claim relations.

    Parameters
    ----------
    session:
        SQLAlchemy database session.
    claim_id:
        Primary key of the claim.

    Returns
    -------
    dict with claim history details, or None if claim_id does not exist.
    """
    claim = session.scalar(select(Claim).where(Claim.id == claim_id))
    if claim is None:
        return None

    # Query all paper links to this claim joined with paper and provenance
    paper_rows = session.execute(
        select(
            Paper.id,
            Paper.external_id,
            Paper.title,
            Paper.publication_year,
            Paper.publication_date,
            PaperClaim.relation_type,
            Provenance.id.label("prov_id"),
            Provenance.evidence_text,
            Provenance.extraction_method,
            Provenance.confidence,
            Provenance.observed_at,
        )
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, PaperClaim.provenance_id == Provenance.id)
        .where(PaperClaim.claim_id == claim_id)
        .order_by(Paper.publication_year.asc().nulls_last(), Paper.publication_date.asc().nulls_last(), Paper.id.asc())
    ).all()

    observations = []
    observed_years = []
    for row in paper_rows:
        if row.publication_year is not None:
            observed_years.append(row.publication_year)
        observations.append({
            "paper_id": row.id,
            "paper_external_id": row.external_id,
            "paper_title": row.title,
            "publication_year": row.publication_year,
            "publication_date": str(row.publication_date) if row.publication_date else None,
            "relation_type": row.relation_type,
            "provenance": {
                "id": row.prov_id,
                "evidence_text": row.evidence_text,
                "extraction_method": row.extraction_method,
                "confidence": row.confidence,
                "observed_at": row.observed_at.isoformat() if row.observed_at else None,
            } if row.prov_id else None,
        })

    # Outgoing relationships (this claim -> target)
    outgoing_rows = session.execute(
        select(
            ClaimRelation.id,
            ClaimRelation.relation_type,
            ClaimRelation.target_claim_id,
            Claim.text.label("target_text"),
            Claim.normalized_text.label("target_norm"),
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(Claim, ClaimRelation.target_claim_id == Claim.id)
        .outerjoin(Provenance, ClaimRelation.provenance_id == Provenance.id)
        .where(ClaimRelation.source_claim_id == claim_id)
    ).all()

    outgoing = [
        {
            "relation_id": r.id,
            "relation_type": r.relation_type,
            "target_claim_id": r.target_claim_id,
            "target_claim_text": r.target_text,
            "target_normalized_text": r.target_norm,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
        }
        for r in outgoing_rows
    ]

    # Incoming relationships (source -> this claim)
    incoming_rows = session.execute(
        select(
            ClaimRelation.id,
            ClaimRelation.relation_type,
            ClaimRelation.source_claim_id,
            Claim.text.label("source_text"),
            Claim.normalized_text.label("source_norm"),
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(Claim, ClaimRelation.source_claim_id == Claim.id)
        .outerjoin(Provenance, ClaimRelation.provenance_id == Provenance.id)
        .where(ClaimRelation.target_claim_id == claim_id)
    ).all()

    incoming = [
        {
            "relation_id": r.id,
            "relation_type": r.relation_type,
            "source_claim_id": r.source_claim_id,
            "source_claim_text": r.source_text,
            "source_normalized_text": r.source_norm,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
        }
        for r in incoming_rows
    ]

    first_year = min(observed_years) if observed_years else None
    latest_year = max(observed_years) if observed_years else None

    return {
        "claim_id": claim.id,
        "text": claim.text,
        "normalized_text": claim.normalized_text,
        "claim_type": claim.claim_type,
        "first_seen_year": first_year,
        "latest_seen_year": latest_year,
        "total_observations": len(observations),
        "observations": observations,
        "outgoing_relations": outgoing,
        "incoming_relations": incoming,
        "epistemic_note": (
            "Observations reflect corpus presence across publication years; "
            "absence in any year does not imply the claim was invalidated."
        ),
    }


def papers_reporting_claim(
    session: Session,
    claim_id: int,
    relation_types: list[str] | None = None,
    paper_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Return all papers that report, make, or support a given claim.

    Parameters
    ----------
    session:
        SQLAlchemy session.
    claim_id:
        Claim primary key.
    relation_types:
        Allowed PaperClaim relation types (defaults to ``['MAKES_CLAIM', 'SUPPORTS']``).
    paper_ids:
        Optional corpus-scoped paper ID filter.
    """
    if relation_types is None:
        relation_types = ["MAKES_CLAIM", "SUPPORTS"]

    stmt = (
        select(
            Paper.id,
            Paper.external_id,
            Paper.title,
            Paper.publication_year,
            Paper.publication_date,
            PaperClaim.relation_type,
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, PaperClaim.provenance_id == Provenance.id)
        .where(
            PaperClaim.claim_id == claim_id,
            PaperClaim.relation_type.in_(relation_types),
        )
        .order_by(Paper.publication_year.asc().nulls_last(), Paper.id.asc())
    )

    if paper_ids is not None:
        if not paper_ids:
            return []
        stmt = stmt.where(Paper.id.in_(paper_ids))

    rows = session.execute(stmt).all()
    return [
        {
            "paper_id": r.id,
            "paper_external_id": r.external_id,
            "paper_title": r.title,
            "publication_year": r.publication_year,
            "publication_date": str(r.publication_date) if r.publication_date else None,
            "relation_type": r.relation_type,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
        }
        for r in rows
    ]


def papers_challenging_claim(
    session: Session,
    claim_id: int,
    paper_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Return papers challenging, contradicting, or qualifying a given claim.

    Includes:
    1. Papers directly linked via ``PaperClaim`` with ``relation_type='CONTRADICTS'``.
    2. Papers reporting a claim that has a ``CHALLENGES`` or ``QUALIFIES``
       relationship targeting this claim.

    Parameters
    ----------
    session:
        SQLAlchemy session.
    claim_id:
        Target claim primary key.
    paper_ids:
        Optional corpus-scoped paper ID filter.
    """
    results: list[dict[str, Any]] = []

    # 1. Direct CONTRADICTS links
    direct_stmt = (
        select(
            Paper.id,
            Paper.external_id,
            Paper.title,
            Paper.publication_year,
            Paper.publication_date,
            PaperClaim.relation_type,
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, PaperClaim.provenance_id == Provenance.id)
        .where(
            PaperClaim.claim_id == claim_id,
            PaperClaim.relation_type == "CONTRADICTS",
        )
        .order_by(Paper.publication_year.asc().nulls_last())
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        direct_stmt = direct_stmt.where(Paper.id.in_(paper_ids))

    for r in session.execute(direct_stmt).all():
        results.append({
            "mechanism": "direct_paper_contradiction",
            "paper_id": r.id,
            "paper_external_id": r.external_id,
            "paper_title": r.title,
            "publication_year": r.publication_year,
            "publication_date": str(r.publication_date) if r.publication_date else None,
            "relation_type": r.relation_type,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
            "challenging_claim_id": claim_id,
            "challenging_claim_text": None,
        })

    # 2. Inter-claim CHALLENGES or QUALIFIES targeting this claim
    rel_stmt = (
        select(
            Paper.id,
            Paper.external_id,
            Paper.title,
            Paper.publication_year,
            Paper.publication_date,
            ClaimRelation.relation_type,
            Claim.id.label("src_claim_id"),
            Claim.text.label("src_claim_text"),
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(Claim, ClaimRelation.source_claim_id == Claim.id)
        .join(PaperClaim, PaperClaim.claim_id == Claim.id)
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, ClaimRelation.provenance_id == Provenance.id)
        .where(
            ClaimRelation.target_claim_id == claim_id,
            ClaimRelation.relation_type.in_(["CHALLENGES", "QUALIFIES"]),
        )
        .order_by(Paper.publication_year.asc().nulls_last())
    )
    if paper_ids is not None:
        rel_stmt = rel_stmt.where(Paper.id.in_(paper_ids))

    for r in session.execute(rel_stmt).all():
        results.append({
            "mechanism": "inter_claim_relation",
            "paper_id": r.id,
            "paper_external_id": r.external_id,
            "paper_title": r.title,
            "publication_year": r.publication_year,
            "publication_date": str(r.publication_date) if r.publication_date else None,
            "relation_type": r.relation_type,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
            "challenging_claim_id": r.src_claim_id,
            "challenging_claim_text": r.src_claim_text,
        })

    return results


def claims_timeline(
    session: Session,
    start_year: int,
    end_year: int,
    paper_ids: set[int] | None = None,
) -> dict[int, dict[str, Any]]:
    """Compare claim observations across each year in [start_year, end_year].

    For each year, returns:
    - ``active_claims_count``: distinct claims observed in papers published in that year
    - ``by_type``: count breakdown by claim_type for that year
    - ``paper_claim_links``: total paper-claim associations in that year
    """
    timeline: dict[int, dict[str, Any]] = {
        year: {
            "active_claims_count": 0,
            "by_type": {},
            "paper_claim_links": 0,
        }
        for year in range(start_year, end_year + 1)
    }

    stmt = (
        select(
            Paper.publication_year,
            Claim.id,
            Claim.claim_type,
        )
        .join(PaperClaim, PaperClaim.paper_id == Paper.id)
        .join(Claim, PaperClaim.claim_id == Claim.id)
        .where(
            Paper.publication_year >= start_year,
            Paper.publication_year <= end_year,
        )
    )
    if paper_ids is not None:
        if not paper_ids:
            return timeline
        stmt = stmt.where(Paper.id.in_(paper_ids))

    rows = session.execute(stmt).all()

    year_claims: dict[int, set[int]] = {year: set() for year in range(start_year, end_year + 1)}
    for pub_year, claim_id, claim_type in rows:
        if pub_year in timeline:
            timeline[pub_year]["paper_claim_links"] += 1
            year_claims[pub_year].add(claim_id)
            c_type = claim_type or "unspecified"
            timeline[pub_year]["by_type"][c_type] = timeline[pub_year]["by_type"].get(c_type, 0) + 1

    for year in timeline:
        timeline[year]["active_claims_count"] = len(year_claims[year])

    return timeline


def newly_observed_claims(
    session: Session,
    start_year: int,
    end_year: int,
    paper_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Return claims whose earliest observation in the corpus falls in [start_year, end_year].

    Parameters
    ----------
    session:
        SQLAlchemy session.
    start_year:
        Inclusive lower publication year.
    end_year:
        Inclusive upper publication year.
    paper_ids:
        Optional corpus-scoped paper ID filter.
    """
    stmt = (
        select(
            Claim.id,
            Claim.text,
            Claim.normalized_text,
            Claim.claim_type,
            func.min(Paper.publication_year).label("first_year"),
        )
        .join(PaperClaim, PaperClaim.claim_id == Claim.id)
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .where(Paper.publication_year.is_not(None))
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        stmt = stmt.where(Paper.id.in_(paper_ids))

    stmt = (
        stmt.group_by(Claim.id, Claim.text, Claim.normalized_text, Claim.claim_type)
        .having(
            func.min(Paper.publication_year) >= start_year,
            func.min(Paper.publication_year) <= end_year,
        )
        .order_by(func.min(Paper.publication_year).asc(), Claim.id.asc())
    )

    rows = session.execute(stmt).all()
    return [
        {
            "claim_id": r.id,
            "text": r.text,
            "normalized_text": r.normalized_text,
            "claim_type": r.claim_type,
            "first_observed_year": r.first_year,
        }
        for r in rows
    ]


def newly_observed_relations(
    session: Session,
    start_year: int,
    end_year: int,
    paper_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Return claim relationships whose source paper or provenance is in [start_year, end_year].

    The relationship year is determined by the earliest publication year of the
    papers that introduce the source claim.
    """
    stmt = (
        select(
            ClaimRelation.id,
            ClaimRelation.relation_type,
            ClaimRelation.source_claim_id,
            ClaimRelation.target_claim_id,
            func.min(Paper.publication_year).label("rel_year"),
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .join(PaperClaim, PaperClaim.claim_id == ClaimRelation.source_claim_id)
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, ClaimRelation.provenance_id == Provenance.id)
        .where(Paper.publication_year.is_not(None))
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        stmt = stmt.where(Paper.id.in_(paper_ids))

    stmt = (
        stmt.group_by(
            ClaimRelation.id,
            ClaimRelation.relation_type,
            ClaimRelation.source_claim_id,
            ClaimRelation.target_claim_id,
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .having(
            func.min(Paper.publication_year) >= start_year,
            func.min(Paper.publication_year) <= end_year,
        )
        .order_by(func.min(Paper.publication_year).asc(), ClaimRelation.id.asc())
    )

    rows = session.execute(stmt).all()
    return [
        {
            "relation_id": r.id,
            "relation_type": r.relation_type,
            "source_claim_id": r.source_claim_id,
            "target_claim_id": r.target_claim_id,
            "observed_year": r.rel_year,
            "evidence_text": r.evidence_text,
            "confidence": r.confidence,
        }
        for r in rows
    ]


def claim_observation_gaps(
    session: Session,
    start_year: int,
    end_year: int,
    paper_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Detect claims observed with temporal gaps or not observed after a given year.

    Distinguishes:
    - ``not_observed_after_year``: last observed before end_year
    - ``intervening_gap``: observed in year X and year Z, but not in year Y (X < Y < Z)

    Crucial interpretation note:
    Absence indicates lack of corpus observation, not proof that the claim was
    invalidated or abandoned in real-world science.
    """
    stmt = (
        select(
            Claim.id,
            Claim.text,
            Paper.publication_year,
        )
        .join(PaperClaim, PaperClaim.claim_id == Claim.id)
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .where(
            Paper.publication_year >= start_year,
            Paper.publication_year <= end_year,
        )
        .distinct()
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        stmt = stmt.where(Paper.id.in_(paper_ids))

    rows = session.execute(stmt).all()
    claim_years: dict[int, tuple[str, set[int]]] = {}
    for cid, ctext, pub_year in rows:
        if pub_year is None:
            continue
        if cid not in claim_years:
            claim_years[cid] = (ctext, set())
        claim_years[cid][1].add(pub_year)

    results: list[dict[str, Any]] = []
    all_years = list(range(start_year, end_year + 1))

    for cid, (ctext, years) in claim_years.items():
        if not years:
            continue
        min_y = min(years)
        max_y = max(years)

        # Check for intervening gaps between first and last observation
        missing_between = [y for y in all_years if min_y < y < max_y and y not in years]
        not_seen_after = max_y if max_y < end_year else None

        if missing_between or not_seen_after is not None:
            results.append({
                "claim_id": cid,
                "text": ctext,
                "first_year": min_y,
                "latest_year": max_y,
                "observed_years": sorted(years),
                "intervening_gap_years": missing_between,
                "not_observed_after_year": not_seen_after,
                "interpretation": (
                    "Absence from corpus in missing years reflects lack of publication "
                    "records in this dataset, not scientific invalidation."
                ),
            })

    results.sort(key=lambda r: (r["latest_year"], r["claim_id"]))
    return results


def claim_temporal_summary(
    session: Session,
    start_year: int,
    end_year: int,
    paper_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Build a comprehensive temporal claim summary for a time window.

    Aggregates timeline, newly observed claims, newly observed relations,
    and gap analysis.
    """
    timeline = claims_timeline(session, start_year, end_year, paper_ids=paper_ids)
    new_claims = newly_observed_claims(session, start_year, end_year, paper_ids=paper_ids)
    new_rels = newly_observed_relations(session, start_year, end_year, paper_ids=paper_ids)
    gaps = claim_observation_gaps(session, start_year, end_year, paper_ids=paper_ids)

    count_stmt = (
        select(func.count(func.distinct(PaperClaim.claim_id)))
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            total_claims = 0
        else:
            total_claims = session.scalar(count_stmt.where(Paper.id.in_(paper_ids))) or 0
    else:
        total_claims = session.scalar(count_stmt) or 0

    return {
        "period": {"start_year": start_year, "end_year": end_year},
        "total_claims_in_period": total_claims,
        "timeline": timeline,
        "newly_observed_claims_count": len(new_claims),
        "newly_observed_claims": new_claims[:20],
        "newly_observed_relations_count": len(new_rels),
        "newly_observed_relations": new_rels[:20],
        "observation_gaps_count": len(gaps),
        "observation_gaps": gaps[:20],
        "scope_note": (
            "Temporal observations are derived strictly from bounded corpus paper dates. "
            "Corpus absence is not proof of claim expiration or falsity."
        ),
    }
