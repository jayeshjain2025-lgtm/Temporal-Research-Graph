"""Candidate claim relationship detection — Phase 3, Milestone 3.3.

Detects conservative, rule-based candidate relationships between pairs of
claims extracted from the same corpus.  Each detected relationship has an
explicit type, a direction, and a traceable evidence basis.

Supported relationship types
-----------------------------
SUPPORTS   — Claim A provides corroborating evidence for Claim B.
CHALLENGES — Claim A presents evidence that calls Claim B into question.
REFINES    — Claim A narrows the scope or adds precision to Claim B.
QUALIFIES  — Claim A adds a condition or exception to Claim B.

Design constraints
------------------
* Rules are conservative: only well-defined lexical signals trigger a
  relationship.  Different wording, shared topics, or opposite sentiment
  alone do NOT imply contradiction.
* Direction is explicit in every returned ``ClaimRelationCandidate``.
* The result is a *candidate*, not a verified fact.
* The function has no side effects; persistence is handled by the caller
  using :func:`src.repositories.claims.upsert_claim_relation`.

Public API
----------
ClaimRelationCandidate      frozen dataclass
detect_claim_relations(candidates) -> list[ClaimRelationCandidate]
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from src.analysis.claims.extractor import ClaimCandidate

# ---------------------------------------------------------------------------
# Lexical signal patterns
# ---------------------------------------------------------------------------

# SUPPORTS: explicit corroboration or confirmation language.
_SUPPORTS_SIGNALS = re.compile(
    r"\b("
    r"confirm(s|ed)?|"
    r"consistent(ly)? with|"
    r"in line with|"
    r"corroborat(es|ed|ing)|"
    r"support(s|ed|ing)|"
    r"replicat(es|ed|ing)|"
    r"similar(ly)? to|"
    r"agree(s|d)? with|"
    r"align(s|ed)? with"
    r")\b",
    re.IGNORECASE,
)

# CHALLENGES: explicit counter-evidence or failure language.
_CHALLENGES_SIGNALS = re.compile(
    r"\b("
    r"contradict(s|ed|ing)?|"
    r"challeng(es|ed|ing)|"
    r"refut(es|ed|ing)|"
    r"conflict(s|ed|ing)? with|"
    r"inconsistent with|"
    r"call(s|ed|ing)? into question|"
    r"fail(s|ed|ing)? to|"
    r"does not (hold|apply|generalise|generalize)|"
    r"in contrast (to|with)"
    r")\b",
    re.IGNORECASE,
)

# REFINES: scope narrowing or precision-adding language.
_REFINES_SIGNALS = re.compile(
    r"\b("
    r"more specifically|"
    r"in particular|"
    r"specifically|"
    r"narrow(s|ed|ing)|"
    r"refin(es|ed|ing)|"
    r"extend(s|ed|ing) (the )?(analysis|result|finding|method)|"
    r"restrict(s|ed|ing) (to|the)"
    r")\b",
    re.IGNORECASE,
)

# QUALIFIES: conditional or exception-adding language.
_QUALIFIES_SIGNALS = re.compile(
    r"\b("
    r"however|"
    r"nevertheless|"
    r"except (when|where|for)|"
    r"only when|"
    r"under (certain|specific|limited) conditions|"
    r"with the caveat|"
    r"subject to|"
    r"provided that|"
    r"unless"
    r")\b",
    re.IGNORECASE,
)

# Ordered by specificity (CHALLENGES before QUALIFIES, which shares "however").
_RELATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SUPPORTS", _SUPPORTS_SIGNALS),
    ("CHALLENGES", _CHALLENGES_SIGNALS),
    ("REFINES", _REFINES_SIGNALS),
    ("QUALIFIES", _QUALIFIES_SIGNALS),
]

# Only pair claims of types that can plausibly relate.
# A "dataset" claim rarely supports or challenges a "method" claim at the
# sentence level; keeping pairs within compatible types reduces false positives.
_COMPATIBLE_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"finding", "finding"}),
        frozenset({"finding", "method"}),
        frozenset({"finding", "comparison"}),
        frozenset({"finding", "limitation"}),
        frozenset({"method", "method"}),
        frozenset({"method", "comparison"}),
        frozenset({"comparison", "limitation"}),
        frozenset({"limitation", "limitation"}),
    }
)


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimRelationCandidate:
    """A candidate directional relationship between two claims.

    Attributes
    ----------
    source_normalized_text:
        Normalized text of the source (subject) claim.
    target_normalized_text:
        Normalized text of the target (object) claim.
    relation_type:
        One of ``SUPPORTS``, ``CHALLENGES``, ``REFINES``, ``QUALIFIES``.
    evidence_text:
        The sentence(s) that triggered the signal (for provenance tracing).
    confidence:
        Heuristic score in [0, 1].  NOT a calibrated probability.
    basis:
        Human-readable description of which lexical signal was matched.
    """

    source_normalized_text: str
    target_normalized_text: str
    relation_type: str
    evidence_text: str
    confidence: float
    basis: str


# Heuristic confidence per relation type.
_RELATION_CONFIDENCE: dict[str, float] = {
    "SUPPORTS": 0.60,
    "CHALLENGES": 0.55,
    "REFINES": 0.55,
    "QUALIFIES": 0.55,
}


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


def detect_claim_relations(
    candidates: list[ClaimCandidate],
) -> list[ClaimRelationCandidate]:
    """Return candidate relationships between the supplied claim candidates.

    Strategy
    --------
    1. Consider all ordered pairs (A, B) where A appears before B in the
       source text (sentence_index order).
    2. Skip pairs whose claim types are not in ``_COMPATIBLE_PAIRS``.
    3. For each pair, scan *both* sentences for the signal patterns.
       When B's text contains a signal, the relationship is (B → A) because
       the later claim is commenting on the earlier one.
    4. Emit at most one relationship per ordered pair (first-matching signal
       in priority order wins).
    5. Do not emit a relationship when the signal is ambiguous or absent.

    Parameters
    ----------
    candidates:
        Claim candidates from a single paper or a corpus slice, ordered by
        ``sentence_index``.  The list may be empty.

    Returns
    -------
    list[ClaimRelationCandidate]
        Candidates in encounter order; may be empty.

    Notes
    -----
    * Different wording or shared topics alone do NOT produce a relationship.
    * Contradictions are not inferred from negation alone; explicit
      counter-evidence signals are required.
    * The returned objects are candidates only; callers decide whether to
      persist them.
    """
    if len(candidates) < 2:
        return []

    # Sort by sentence_index to maintain encounter order.
    ordered = sorted(candidates, key=lambda c: c.sentence_index)
    results: list[ClaimRelationCandidate] = []

    for earlier, later in combinations(ordered, 2):
        # Only pair compatible claim types.
        if frozenset({earlier.claim_type, later.claim_type}) not in _COMPATIBLE_PAIRS:
            continue

        # Scan the *later* sentence for signals referencing the earlier claim.
        for relation_type, pattern in _RELATION_PATTERNS:
            match = pattern.search(later.text)
            if match:
                results.append(
                    ClaimRelationCandidate(
                        source_normalized_text=later.normalized_text,
                        target_normalized_text=earlier.normalized_text,
                        relation_type=relation_type,
                        evidence_text=later.text,
                        confidence=_RELATION_CONFIDENCE[relation_type],
                        basis=f"signal={match.group()!r} in sentence index {later.sentence_index}",
                    )
                )
                break  # First-match wins; avoid duplicate relations for the same pair.

    return results
