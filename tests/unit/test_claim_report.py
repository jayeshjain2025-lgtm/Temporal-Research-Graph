"""Tests for Phase 3 Milestone 3.5 — research claim intelligence report.

Coverage
--------
REP1  build_claim_report returns complete expected top-level schema
REP2  build_claim_report aggregates claim counts, categories, and relationships accurately
REP3  build_claim_report returns explicit empty sections when no data exists (no invented facts)
REP4  build_claim_report restricts results when corpus_name is provided
REP5  build_claim_report includes evaluation_metrics when provided
REP6  build_claim_report defaults evaluation_metrics to no_evaluation_sample_provided
REP7  format_claim_summary produces human-readable text with summary counts
REP8  report is 100% JSON-serializable without errors
"""
from datetime import date
import json
import pytest

from src.analysis.claims.extractor import normalize_claim
from src.analysis.claims.reports.claim_report import build_claim_report, format_claim_summary
from src.models import Claim, Corpus, Paper, PaperClaim, PaperCorpus, Provenance
from src.repositories.claims import (
    link_paper_claim,
    upsert_claim,
    upsert_claim_provenance,
    upsert_claim_relation,
)


def _seed_report_data(session):
    p2022 = Paper(
        external_id="W_REP_2022",
        title="Scalable Temporal Embeddings",
        publication_year=2022,
        publication_date=date(2022, 5, 10),
        source="openalex",
    )
    p2023 = Paper(
        external_id="W_REP_2023",
        title="Evaluating Temporal Graphs",
        publication_year=2023,
        publication_date=date(2023, 6, 15),
        source="openalex",
    )
    session.add_all([p2022, p2023])
    session.flush()

    c1, _ = upsert_claim(
        session,
        text="Temporal embeddings improve link prediction accuracy.",
        normalized_text=normalize_claim("Temporal embeddings improve link prediction accuracy."),
        claim_type="finding",
    )
    c2, _ = upsert_claim(
        session,
        text="We propose an inductive temporal graph neural network.",
        normalized_text=normalize_claim("We propose an inductive temporal graph neural network."),
        claim_type="method",
    )
    c3, _ = upsert_claim(
        session,
        text="These results are consistent with findings on static graph baselines.",
        normalized_text=normalize_claim("These results are consistent with findings on static graph baselines."),
        claim_type="finding",
    )

    prov1 = upsert_claim_provenance(
        session,
        source_identifier=p2022.external_id,
        evidence_text="embeddings improve link prediction accuracy",
        extraction_method="deterministic",
        confidence=0.75,
    )
    link_paper_claim(session, p2022, c1, "MAKES_CLAIM", prov1.id)
    link_paper_claim(session, p2022, c2, "MAKES_CLAIM", prov1.id)

    prov2 = upsert_claim_provenance(
        session,
        source_identifier=p2023.external_id,
        evidence_text="results are consistent with findings",
        extraction_method="deterministic",
        confidence=0.60,
    )
    link_paper_claim(session, p2023, c3, "MAKES_CLAIM", prov2.id)
    link_paper_claim(session, p2023, c1, "SUPPORTS", prov2.id)

    # Relationship: c3 SUPPORTS c1
    rel_prov = upsert_claim_provenance(
        session,
        source_identifier=p2023.external_id,
        evidence_text="results are consistent with findings",
        confidence=0.60,
    )
    upsert_claim_relation(session, c3, c1, "SUPPORTS", rel_prov.id)

    return {"papers": [p2022, p2023], "claims": [c1, c2, c3]}


# ---------------------------------------------------------------------------
# REP1 — Schema completeness
# ---------------------------------------------------------------------------


def test_build_claim_report_schema(session):
    _seed_report_data(session)

    report = build_claim_report(session, 2022, 2023)

    expected_keys = {
        "title",
        "period",
        "corpus",
        "scope_note",
        "summary_counts",
        "temporal_evolution",
        "extracted_claims",
        "claim_relationships",
        "evaluation_metrics",
        "epistemic_notes",
    }
    assert expected_keys.issubset(report.keys())
    assert report["period"] == {"start_year": 2022, "end_year": 2023}
    assert report["corpus"] == "all"


# ---------------------------------------------------------------------------
# REP2 — Aggregations and counts
# ---------------------------------------------------------------------------


def test_build_claim_report_counts(session):
    _seed_report_data(session)

    report = build_claim_report(session, 2022, 2023)
    counts = report["summary_counts"]

    assert counts["total_distinct_claims"] == 3
    assert counts["total_paper_claim_links"] == 4  # (p2022, c1), (p2022, c2), (p2023, c3), (p2023, c1)
    assert counts["total_claim_relationships"] == 1
    assert counts["claims_by_category"]["finding"] == 2
    assert counts["claims_by_category"]["method"] == 1
    assert counts["relationships_by_type"]["SUPPORTS"] == 1

    # Check extracted claims detail
    claims = report["extracted_claims"]
    assert len(claims) == 3
    for c in claims:
        assert "id" in c
        assert "text" in c
        assert "normalized_text" in c
        assert "category" in c
        assert len(c["source_papers"]) >= 1

    # Check relationships detail
    rels = report["claim_relationships"]
    assert len(rels) == 1
    assert rels[0]["relation_type"] == "SUPPORTS"
    assert "direction" in rels[0]


# ---------------------------------------------------------------------------
# REP3 — Empty range reports explicit empty sections without errors
# ---------------------------------------------------------------------------


def test_build_claim_report_empty_range(session):
    _seed_report_data(session)

    report = build_claim_report(session, 2010, 2015)
    counts = report["summary_counts"]

    assert counts["total_distinct_claims"] == 0
    assert counts["total_paper_claim_links"] == 0
    assert counts["total_claim_relationships"] == 0
    assert counts["claims_by_category"] == {}
    assert counts["relationships_by_type"] == {}
    assert report["extracted_claims"] == []
    assert report["claim_relationships"] == []


# ---------------------------------------------------------------------------
# REP4 — Corpus scoping
# ---------------------------------------------------------------------------


def test_build_claim_report_corpus_scoping(session):
    data = _seed_report_data(session)
    p2022 = data["papers"][0]

    corpus = Corpus(name="ml_graphs")
    session.add(corpus)
    session.flush()

    session.add(PaperCorpus(paper_id=p2022.id, corpus_id=corpus.id))
    session.flush()

    report_corpus = build_claim_report(session, 2022, 2023, corpus_name="ml_graphs")
    assert report_corpus["corpus"] == "ml_graphs"
    # Only p2022 papers (c1 and c2) should be in ml_graphs
    assert report_corpus["summary_counts"]["total_distinct_claims"] == 2
    claim_ids = {c["id"] for c in report_corpus["extracted_claims"]}
    assert data["claims"][0].id in claim_ids
    assert data["claims"][1].id in claim_ids
    assert data["claims"][2].id not in claim_ids


# ---------------------------------------------------------------------------
# REP5 — Evaluation metrics included when provided
# ---------------------------------------------------------------------------


def test_build_claim_report_with_evaluation_metrics(session):
    metrics = {
        "precision": 0.88,
        "recall": 0.79,
        "f1": 0.83,
        "sample_size": 50,
        "annotator_agreement": "Cohen_kappa=0.82",
    }
    report = build_claim_report(session, 2022, 2023, evaluation_metrics=metrics)

    eval_sec = report["evaluation_metrics"]
    assert eval_sec["status"] == "evaluated_on_sample"
    assert eval_sec["precision"] == 0.88
    assert eval_sec["recall"] == 0.79
    assert eval_sec["sample_size"] == 50


# ---------------------------------------------------------------------------
# REP6 — Evaluation metrics default when not provided
# ---------------------------------------------------------------------------


def test_build_claim_report_without_evaluation_metrics(session):
    report = build_claim_report(session, 2022, 2023)

    eval_sec = report["evaluation_metrics"]
    assert eval_sec["status"] == "no_evaluation_sample_provided"
    assert eval_sec["precision"] is None
    assert eval_sec["sample_size"] == 0


# ---------------------------------------------------------------------------
# REP7 — Format summary text
# ---------------------------------------------------------------------------


def test_format_claim_summary(session):
    _seed_report_data(session)

    report = build_claim_report(session, 2022, 2023)
    summary_text = format_claim_summary(report)

    assert "CLAIM INTELLIGENCE" in summary_text
    assert "Period: 2022 -> 2023" in summary_text
    assert "Distinct Claims: 3" in summary_text
    assert "SUPPORTS: 1" in summary_text
    assert "finding: 2" in summary_text


# ---------------------------------------------------------------------------
# REP8 — JSON serialization
# ---------------------------------------------------------------------------


def test_claim_report_json_serializable(session):
    _seed_report_data(session)

    report = build_claim_report(session, 2022, 2023)
    dumped = json.dumps(report, default=str)
    assert dumped is not None
    loaded = json.loads(dumped)
    assert loaded["summary_counts"]["total_distinct_claims"] == 3
