"""Claim extraction, relationships, and temporal reasoning."""
from src.analysis.claims.extractor import (
    ClaimCandidate,
    ClaimExtractorProtocol,
    DeterministicClaimExtractor,
    extract_claim_candidates,
    normalize_claim,
)
from src.analysis.claims.pipeline import (
    ClaimPipelineResult,
    extract_and_persist_claims,
    run_corpus_relation_pass,
)
from src.analysis.claims.relations import (
    ClaimRelationCandidate,
    detect_claim_relations,
)
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

__all__ = [
    "ClaimCandidate",
    "ClaimExtractorProtocol",
    "ClaimPipelineResult",
    "ClaimRelationCandidate",
    "DeterministicClaimExtractor",
    "claim_history",
    "claim_observation_gaps",
    "claim_temporal_summary",
    "claims_timeline",
    "detect_claim_relations",
    "extract_and_persist_claims",
    "extract_claim_candidates",
    "run_corpus_relation_pass",
    "newly_observed_claims",
    "newly_observed_relations",
    "normalize_claim",
    "papers_challenging_claim",
    "papers_reporting_claim",
]
