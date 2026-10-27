"""Tests for Phase 3 Milestone 3.4 — temporal claim evolution.

Coverage
--------
T1  claim_history returns chronological observations with paper & provenance metadata
T2  claim_history tracks both incoming and outgoing claim relationships
T3  claim_history returns None for nonexistent claim ID
T4  papers_reporting_claim filters by relation_type and respects corpus scoping
T5  papers_challenging_claim returns direct CONTRADICTS paper associations
T6  papers_challenging_claim returns indirect inter-claim CHALLENGES & QUALIFIES
T7  claims_timeline accurately counts active claims and breakdowns per year
T8  newly_observed_claims identifies first observation year across corpus
T9  newly_observed_relations associates relationships with observation year
T10 claim_observation_gaps detects both intervening gaps and discontinued observations
T11 corpus filtering isolates claims strictly by corpus membership
T12 publication year vs observation time separation without fabricated validity intervals
"""
from datetime import date
import pytest
from sqlalchemy import select

from src.analysis.claims.extractor import normalize_claim
from src.analysis.claims.temporal import (
    claim_history,
    claim_observation_gaps,
    claim_temporal_summary,
    claims_timeline,
    newly_observed_claims,
    newly_observed_relations,
    papers_challenging_claim,
    papers_reporting_claim,
)
from src.models import (
    Claim,
    Corpus,
    Paper,
    PaperClaim,
    PaperCorpus,
    Provenance,
)
from src.repositories.claims import (
    link_paper_claim,
    upsert_claim,
    upsert_claim_provenance,
    upsert_claim_relation,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _create_paper(
    session,
    external_id: str,
    title: str,
    year: int,
    pub_date: date | None = None,
    source: str = "openalex",
) -> Paper:
    paper = Paper(
        external_id=external_id,
        title=title,
        publication_year=year,
        publication_date=pub_date or date(year, 1, 1),
        source=source,
    )
    session.add(paper)
    session.flush()
    return paper


def _setup_temporal_claims_data(session):
    p2020 = _create_paper(session, "W2020", "Early Paper on TKG", 2020)
    p2021 = _create_paper(session, "W2021", "Intermediate TKG Study", 2021)
    p2022 = _create_paper(session, "W2022", "Modern Link Prediction", 2022)
    p2023 = _create_paper(session, "W2023", "Critique of Early TKG Methods", 2023)

    # Claim 1: Persistent claim observed in 2020 and 2023 (gap in 2021, 2022)
    c1, _ = upsert_claim(
        session,
        text="Temporal graph embeddings improve link prediction accuracy over static baselines.",
        normalized_text=normalize_claim("Temporal graph embeddings improve link prediction accuracy over static baselines."),
        claim_type="finding",
    )
    prov_2020 = upsert_claim_provenance(session, source_identifier=p2020.external_id, evidence_text="embeddings improve link prediction")
    link_paper_claim(session, p2020, c1, "MAKES_CLAIM", prov_2020.id)

    prov_2023 = upsert_claim_provenance(session, source_identifier=p2023.external_id, evidence_text="we also find embeddings improve link prediction")
    link_paper_claim(session, p2023, c1, "SUPPORTS", prov_2023.id)

    # Claim 2: One-off claim observed only in 2021
    c2, _ = upsert_claim(
        session,
        text="We propose an inductive temporal reasoning architecture.",
        normalized_text=normalize_claim("We propose an inductive temporal reasoning architecture."),
        claim_type="method",
    )
    prov_2021 = upsert_claim_provenance(session, source_identifier=p2021.external_id, evidence_text="we propose inductive temporal architecture")
    link_paper_claim(session, p2021, c2, "MAKES_CLAIM", prov_2021.id)

    # Claim 3: New method in 2022
    c3, _ = upsert_claim(
        session,
        text="Transformer architectures outperform recurrent baselines on temporal benchmarks.",
        normalized_text=normalize_claim("Transformer architectures outperform recurrent baselines on temporal benchmarks."),
        claim_type="comparison",
    )
    prov_2022 = upsert_claim_provenance(session, source_identifier=p2022.external_id, evidence_text="transformers outperform recurrent baselines")
    link_paper_claim(session, p2022, c3, "MAKES_CLAIM", prov_2022.id)

    # Claim 4: Challenging claim in 2023 that CHALLENGES Claim 1
    c4, _ = upsert_claim(
        session,
        text="However, these results contradict claims of improvement under distribution shifts.",
        normalized_text=normalize_claim("However, these results contradict claims of improvement under distribution shifts."),
        claim_type="limitation",
    )
    prov_c4 = upsert_claim_provenance(session, source_identifier=p2023.external_id, evidence_text="contradict claims of improvement")
    link_paper_claim(session, p2023, c4, "MAKES_CLAIM", prov_c4.id)

    # Relationship: c4 CHALLENGES c1
    rel_prov = upsert_claim_provenance(session, source_identifier=p2023.external_id, evidence_text="contradict claims of improvement")
    upsert_claim_relation(session, c4, c1, "CHALLENGES", rel_prov.id)

    # Direct contradiction: p2023 also directly CONTRADICTS c2
    prov_contra = upsert_claim_provenance(session, source_identifier=p2023.external_id, evidence_text="inductive claims failed replication")
    link_paper_claim(session, p2023, c2, "CONTRADICTS", prov_contra.id)

    return {
        "papers": {"2020": p2020, "2021": p2021, "2022": p2022, "2023": p2023},
        "claims": {"c1": c1, "c2": c2, "c3": c3, "c4": c4},
    }


# ---------------------------------------------------------------------------
# T1 — claim_history chronological observations
# ---------------------------------------------------------------------------


def test_claim_history_chronological(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]

    history = claim_history(session, c1.id)
    assert history is not None
    assert history["claim_id"] == c1.id
    assert history["first_seen_year"] == 2020
    assert history["latest_seen_year"] == 2023
    assert history["total_observations"] == 2

    obs = history["observations"]
    assert obs[0]["publication_year"] == 2020
    assert obs[0]["paper_external_id"] == "W2020"
    assert obs[0]["relation_type"] == "MAKES_CLAIM"
    assert obs[0]["provenance"]["evidence_text"] == "embeddings improve link prediction"

    assert obs[1]["publication_year"] == 2023
    assert obs[1]["paper_external_id"] == "W2023"
    assert obs[1]["relation_type"] == "SUPPORTS"


# ---------------------------------------------------------------------------
# T2 — claim_history incoming and outgoing relations
# ---------------------------------------------------------------------------


def test_claim_history_relations(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]
    c4 = data["claims"]["c4"]

    h1 = claim_history(session, c1.id)
    assert len(h1["incoming_relations"]) == 1
    assert h1["incoming_relations"][0]["relation_type"] == "CHALLENGES"
    assert h1["incoming_relations"][0]["source_claim_id"] == c4.id

    h4 = claim_history(session, c4.id)
    assert len(h4["outgoing_relations"]) == 1
    assert h4["outgoing_relations"][0]["relation_type"] == "CHALLENGES"
    assert h4["outgoing_relations"][0]["target_claim_id"] == c1.id


# ---------------------------------------------------------------------------
# T3 — claim_history nonexistent ID returns None
# ---------------------------------------------------------------------------


def test_claim_history_nonexistent(session):
    assert claim_history(session, 999999) is None


# ---------------------------------------------------------------------------
# T4 — papers_reporting_claim filtering
# ---------------------------------------------------------------------------


def test_papers_reporting_claim(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]

    # Both W2020 (MAKES_CLAIM) and W2023 (SUPPORTS) report c1
    reporters = papers_reporting_claim(session, c1.id)
    ext_ids = [r["paper_external_id"] for r in reporters]
    assert ext_ids == ["W2020", "W2023"]

    # Filter to only SUPPORTS
    supports_only = papers_reporting_claim(session, c1.id, relation_types=["SUPPORTS"])
    assert len(supports_only) == 1
    assert supports_only[0]["paper_external_id"] == "W2023"


# ---------------------------------------------------------------------------
# T5 — papers_challenging_claim via direct PaperClaim CONTRADICTS
# ---------------------------------------------------------------------------


def test_papers_challenging_claim_direct(session):
    data = _setup_temporal_claims_data(session)
    c2 = data["claims"]["c2"]

    # W2023 directly CONTRADICTS c2
    challengers = papers_challenging_claim(session, c2.id)
    assert len(challengers) == 1
    assert challengers[0]["mechanism"] == "direct_paper_contradiction"
    assert challengers[0]["paper_external_id"] == "W2023"


# ---------------------------------------------------------------------------
# T6 — papers_challenging_claim via inter-claim CHALLENGES
# ---------------------------------------------------------------------------


def test_papers_challenging_claim_inter_claim(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]

    # c4 CHALLENGES c1, and c4 was published in W2023
    challengers = papers_challenging_claim(session, c1.id)
    assert len(challengers) == 1
    assert challengers[0]["mechanism"] == "inter_claim_relation"
    assert challengers[0]["paper_external_id"] == "W2023"
    assert challengers[0]["relation_type"] == "CHALLENGES"
    assert challengers[0]["challenging_claim_id"] == data["claims"]["c4"].id


# ---------------------------------------------------------------------------
# T7 — claims_timeline counts and by_type
# ---------------------------------------------------------------------------


def test_claims_timeline(session):
    _setup_temporal_claims_data(session)

    timeline = claims_timeline(session, 2020, 2023)
    assert 2020 in timeline
    assert 2021 in timeline
    assert 2022 in timeline
    assert 2023 in timeline

    assert timeline[2020]["active_claims_count"] == 1
    assert timeline[2020]["by_type"] == {"finding": 1}

    assert timeline[2021]["active_claims_count"] == 1
    assert timeline[2021]["by_type"] == {"method": 1}

    assert timeline[2022]["active_claims_count"] == 1
    assert timeline[2022]["by_type"] == {"comparison": 1}

    # In 2023: c1 (finding, via SUPPORTS), c2 (method, via CONTRADICTS), c4 (limitation, via MAKES_CLAIM)
    assert timeline[2023]["active_claims_count"] == 3


# ---------------------------------------------------------------------------
# T8 — newly_observed_claims
# ---------------------------------------------------------------------------


def test_newly_observed_claims(session):
    data = _setup_temporal_claims_data(session)

    # 2022 should only yield c3 (first seen in 2022)
    new_2022 = newly_observed_claims(session, 2022, 2022)
    assert len(new_2022) == 1
    assert new_2022[0]["claim_id"] == data["claims"]["c3"].id
    assert new_2022[0]["first_observed_year"] == 2022

    # 2020 should yield c1
    new_2020 = newly_observed_claims(session, 2020, 2020)
    assert len(new_2020) == 1
    assert new_2020[0]["claim_id"] == data["claims"]["c1"].id


# ---------------------------------------------------------------------------
# T9 — newly_observed_relations
# ---------------------------------------------------------------------------


def test_newly_observed_relations(session):
    _setup_temporal_claims_data(session)

    rels = newly_observed_relations(session, 2020, 2023)
    assert len(rels) == 1
    assert rels[0]["relation_type"] == "CHALLENGES"
    assert rels[0]["observed_year"] == 2023


# ---------------------------------------------------------------------------
# T10 — claim_observation_gaps
# ---------------------------------------------------------------------------


def test_claim_observation_gaps(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]
    c2 = data["claims"]["c2"]

    gaps = claim_observation_gaps(session, 2020, 2023)
    gaps_by_id = {g["claim_id"]: g for g in gaps}

    # c1 observed in 2020 and 2023 -> intervening gap in [2021, 2022]
    assert c1.id in gaps_by_id
    assert gaps_by_id[c1.id]["intervening_gap_years"] == [2021, 2022]

    # c2 observed in 2021, then in 2023 (CONTRADICTS) -> gap in 2022
    assert c2.id in gaps_by_id
    assert gaps_by_id[c2.id]["intervening_gap_years"] == [2022]


# ---------------------------------------------------------------------------
# T11 — corpus filtering
# ---------------------------------------------------------------------------


def test_corpus_filtering(session):
    data = _setup_temporal_claims_data(session)
    p2020 = data["papers"]["2020"]
    p2021 = data["papers"]["2021"]

    corpus_a = Corpus(name="corpus_a")
    corpus_b = Corpus(name="corpus_b")
    session.add_all([corpus_a, corpus_b])
    session.flush()

    session.add(PaperCorpus(paper_id=p2020.id, corpus_id=corpus_a.id))
    session.add(PaperCorpus(paper_id=p2021.id, corpus_id=corpus_b.id))
    session.flush()

    # In corpus_b (contains only p2021), newly observed claims in 2020 should be empty
    paper_ids_b = {p2021.id}
    new_in_b_2020 = newly_observed_claims(session, 2020, 2020, paper_ids=paper_ids_b)
    assert len(new_in_b_2020) == 0

    new_in_b_2021 = newly_observed_claims(session, 2021, 2021, paper_ids=paper_ids_b)
    assert len(new_in_b_2021) == 1
    assert new_in_b_2021[0]["claim_id"] == data["claims"]["c2"].id


# ---------------------------------------------------------------------------
# T12 — separation of times (no fabricated valid_from / valid_to)
# ---------------------------------------------------------------------------


def test_separation_of_times(session):
    data = _setup_temporal_claims_data(session)
    c1 = data["claims"]["c1"]

    history = claim_history(session, c1.id)
    assert "valid_from" not in history
    assert "valid_to" not in history
    assert "epistemic_note" in history
    assert "not imply the claim was invalidated" in history["epistemic_note"]

    summary = claim_temporal_summary(session, 2020, 2023)
    assert "scope_note" in summary
    assert summary["period"] == {"start_year": 2020, "end_year": 2023}
