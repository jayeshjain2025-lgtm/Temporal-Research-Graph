"""Research claim intelligence report — Phase 3, Milestone 3.5.

Generates a structured, evidence-backed research intelligence report covering:
- Extracted claims and their categories
- Source paper identifiers and publication dates
- Traceable provenance evidence and heuristic confidence
- Inter-claim relationships (SUPPORTS, CHALLENGES, REFINES, QUALIFIES)
- Temporal evolution, newly observed claims, and observation gaps
- Evaluation metrics from manually reviewed samples (or explicit unavailable status)

Does NOT invent findings when evidence is absent; returns explicit empty sections.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis.claims.temporal import (
    claim_observation_gaps,
    claims_timeline,
    newly_observed_claims,
    newly_observed_relations,
)
from src.analysis.evolution.corpus_filter import corpus_paper_ids
from src.models import Claim, ClaimRelation, Paper, PaperClaim, Provenance


def build_claim_report(
    session: Session,
    start_year: int,
    end_year: int,
    corpus_name: str | None = None,
    evaluation_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a comprehensive claim intelligence and temporal reasoning report.

    Parameters
    ----------
    session:
        SQLAlchemy database session.
    start_year:
        Start publication year (inclusive).
    end_year:
        End publication year (inclusive).
    corpus_name:
        Optional named corpus to restrict analysis to.
    evaluation_metrics:
        Optional evaluation metrics computed from a human-reviewed sample.

    Returns
    -------
    dict containing structured research intelligence report.
    """
    paper_ids = corpus_paper_ids(session, corpus_name)

    # 1. Base query for claims observed in the period
    stmt_claims = (
        select(
            Claim.id,
            Claim.text,
            Claim.normalized_text,
            Claim.claim_type,
            Paper.id.label("paper_id"),
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
        .join(PaperClaim, PaperClaim.claim_id == Claim.id)
        .join(Paper, PaperClaim.paper_id == Paper.id)
        .outerjoin(Provenance, PaperClaim.provenance_id == Provenance.id)
        .where(
            Paper.publication_year >= start_year,
            Paper.publication_year <= end_year,
        )
        .order_by(Paper.publication_year.asc().nulls_last(), Claim.id.asc())
    )

    if paper_ids is not None:
        if not paper_ids:
            stmt_claims = stmt_claims.where(False)
        else:
            stmt_claims = stmt_claims.where(Paper.id.in_(paper_ids))

    rows = session.execute(stmt_claims).all()

    # Aggregate by claim
    claims_map: dict[int, dict[str, Any]] = {}
    categories_count: dict[str, int] = {}
    total_paper_claim_links = len(rows)

    for r in rows:
        cid = r.id
        if cid not in claims_map:
            ctype = r.claim_type or "unspecified"
            categories_count[ctype] = categories_count.get(ctype, 0) + 1
            claims_map[cid] = {
                "id": cid,
                "text": r.text,
                "normalized_text": r.normalized_text,
                "category": r.claim_type,
                "source_papers": [],
                "evidence_references": [],
            }

        # Add paper if not already listed
        existing_paper_ids = {p["paper_id"] for p in claims_map[cid]["source_papers"]}
        if r.paper_id not in existing_paper_ids:
            claims_map[cid]["source_papers"].append({
                "paper_id": r.paper_id,
                "external_id": r.external_id,
                "title": r.title,
                "publication_year": r.publication_year,
                "publication_date": str(r.publication_date) if r.publication_date else None,
                "relation_type": r.relation_type,
            })

        if r.prov_id:
            existing_prov_ids = {e["provenance_id"] for e in claims_map[cid]["evidence_references"]}
            if r.prov_id not in existing_prov_ids:
                claims_map[cid]["evidence_references"].append({
                    "provenance_id": r.prov_id,
                    "evidence_text": r.evidence_text,
                    "extraction_method": r.extraction_method,
                    "confidence": r.confidence,
                    "observed_at": r.observed_at.isoformat() if r.observed_at else None,
                })

    extracted_claims = list(claims_map.values())

    # 2. Inter-claim relationships in the period
    stmt_rels = (
        select(
            ClaimRelation.id,
            ClaimRelation.relation_type,
            ClaimRelation.source_claim_id,
            ClaimRelation.target_claim_id,
            Provenance.evidence_text,
            Provenance.confidence,
        )
        .outerjoin(Provenance, ClaimRelation.provenance_id == Provenance.id)
    )

    observed_claim_ids = set(claims_map.keys())
    if observed_claim_ids:
        # Either source or target observed in this period
        stmt_rels = stmt_rels.where(
            (ClaimRelation.source_claim_id.in_(observed_claim_ids))
            | (ClaimRelation.target_claim_id.in_(observed_claim_ids))
        )
    else:
        stmt_rels = stmt_rels.where(False)

    rel_rows = session.execute(stmt_rels).all()

    # Look up texts for claims involved in relations
    rel_claim_ids = set()
    for rr in rel_rows:
        rel_claim_ids.add(rr.source_claim_id)
        rel_claim_ids.add(rr.target_claim_id)

    claim_texts = {}
    if rel_claim_ids:
        c_rows = session.execute(
            select(Claim.id, Claim.text).where(Claim.id.in_(rel_claim_ids))
        ).all()
        claim_texts = {cid: text for cid, text in c_rows}

    relationships = []
    relations_count: dict[str, int] = {}
    for rr in rel_rows:
        rtype = rr.relation_type
        relations_count[rtype] = relations_count.get(rtype, 0) + 1
        relationships.append({
            "id": rr.id,
            "relation_type": rtype,
            "source_claim_id": rr.source_claim_id,
            "source_claim_text": claim_texts.get(rr.source_claim_id),
            "target_claim_id": rr.target_claim_id,
            "target_claim_text": claim_texts.get(rr.target_claim_id),
            "evidence_text": rr.evidence_text,
            "confidence": rr.confidence,
            "direction": f"Claim {rr.source_claim_id} {rtype} Claim {rr.target_claim_id}",
        })

    # 3. Temporal evolution analysis
    timeline = claims_timeline(session, start_year, end_year, paper_ids=paper_ids)
    new_claims = newly_observed_claims(session, start_year, end_year, paper_ids=paper_ids)
    new_rels = newly_observed_relations(session, start_year, end_year, paper_ids=paper_ids)
    gaps = claim_observation_gaps(session, start_year, end_year, paper_ids=paper_ids)

    # 4. Evaluation section
    eval_section: dict[str, Any]
    if evaluation_metrics:
        eval_section = {
            "status": "evaluated_on_sample",
            **evaluation_metrics,
        }
    else:
        eval_section = {
            "status": "no_evaluation_sample_provided",
            "precision": None,
            "recall": None,
            "sample_size": 0,
            "note": "Evaluation metrics are calculated only when a manually annotated sample is provided.",
        }

    corpus_title = f"CLAIM INTELLIGENCE: {corpus_name.upper()}" if corpus_name else "CLAIM INTELLIGENCE"

    return {
        "title": corpus_title,
        "period": {"start_year": start_year, "end_year": end_year},
        "corpus": corpus_name or "all",
        "scope_note": (
            "All claims, relationships, and temporal metrics are derived strictly from "
            "the bounded PostgreSQL corpus. Absence of a claim or relationship in a given "
            "year indicates lack of observation in this dataset, not real-world invalidity."
        ),
        "summary_counts": {
            "total_distinct_claims": len(extracted_claims),
            "total_paper_claim_links": total_paper_claim_links,
            "total_claim_relationships": len(relationships),
            "claims_by_category": categories_count,
            "relationships_by_type": relations_count,
        },
        "temporal_evolution": {
            "timeline": timeline,
            "newly_observed_claims_count": len(new_claims),
            "newly_observed_claims": new_claims,
            "newly_observed_relations_count": len(new_rels),
            "newly_observed_relations": new_rels,
            "observation_gaps_count": len(gaps),
            "observation_gaps": gaps,
        },
        "extracted_claims": extracted_claims,
        "claim_relationships": relationships,
        "evaluation_metrics": eval_section,
        "epistemic_notes": {
            "uncertainty_note": (
                "Confidence values are heuristic rule-based estimates, not calibrated "
                "scientific probabilities. Evidence text is captured at extraction time."
            ),
            "temporality_note": (
                "Publication time and observation time are kept strictly separate. "
                "Validity intervals are not fabricated."
            ),
        },
    }


def format_claim_summary(report: dict[str, Any]) -> str:
    """Format a human-readable text summary of the claim intelligence report."""
    start_year = report["period"]["start_year"]
    end_year = report["period"]["end_year"]
    corpus = report.get("corpus", "all")
    counts = report["summary_counts"]

    title = report.get("title", "CLAIM INTELLIGENCE")
    lines = [
        title,
        "=" * len(title),
        "",
        f"Period: {start_year} -> {end_year} | Corpus: {corpus}",
        "",
        f"Distinct Claims: {counts['total_distinct_claims']}",
        f"Paper-Claim Links: {counts['total_paper_claim_links']}",
        f"Claim-Claim Relationships: {counts['total_claim_relationships']}",
        "",
        "Claims by Category:",
    ]

    for cat, cnt in counts.get("claims_by_category", {}).items():
        lines.append(f"  - {cat}: {cnt}")

    if not counts.get("claims_by_category"):
        lines.append("  (No claims observed in this period)")

    lines.append("")
    lines.append("Relationships by Type:")
    for rel_type, cnt in counts.get("relationships_by_type", {}).items():
        lines.append(f"  - {rel_type}: {cnt}")

    if not counts.get("relationships_by_type"):
        lines.append("  (No inter-claim relationships observed in this period)")

    temp = report.get("temporal_evolution", {})
    lines.append("")
    lines.append(f"Newly Observed Claims: {temp.get('newly_observed_claims_count', 0)}")
    lines.append(f"Observation Gaps Detected: {temp.get('observation_gaps_count', 0)}")

    eval_sec = report.get("evaluation_metrics", {})
    lines.append("")
    lines.append(f"Evaluation Status: {eval_sec.get('status')}")
    if eval_sec.get("precision") is not None:
        lines.append(f"  - Precision: {eval_sec['precision']:.2%}")
        lines.append(f"  - Recall: {eval_sec.get('recall', 0.0):.2%}")
        lines.append(f"  - Sample size: {eval_sec.get('sample_size', 0)}")

    lines.append("")
    lines.append("Note: Corpus absence does not imply real-world claim invalidation.")
    return "\n".join(lines)
