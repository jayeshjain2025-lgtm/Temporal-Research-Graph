"""Deterministic candidate-claim extraction from research abstracts.

This module proposes candidate claims from sentence-level pattern matching.
It does not verify whether a proposition is scientifically true.
Confidence values are heuristic estimates, not calibrated scientific probabilities.

Public API
----------
split_sentences(text)                      -> list[str]
normalize_claim(text)                      -> str
extract_claim_candidates(text)             -> list[ClaimCandidate]
ClaimCandidate                             (frozen dataclass)
ClaimExtractorProtocol                     (runtime-checkable Protocol for future substitution)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Claim-type pattern catalogue
# Favour precision: each pattern targets a distinct epistemic role.
# ---------------------------------------------------------------------------

CLAIM_PATTERNS: dict[str, re.Pattern[str]] = {
    "finding": re.compile(
        r"\b("
        r"we find|we found|our findings|results show|"
        r"results demonstrate|experiments show|"
        r"demonstrate that|shows that|show that|"
        r"indicates that|suggests that|"
        r"outperforms|outperformed|achieves|achieved|"
        r"improves|improved|reduces|reduced|"
        r"increases|increased|decreases|decreased|"
        r"confirms that|confirm that|verify that|verified that|"
        r"we observe|we observed|we report|we reported"
        r")\b",
        re.IGNORECASE,
    ),
    "method": re.compile(
        r"\b("
        r"we propose|we present|we introduce|we develop|we design|"
        r"this paper proposes|this paper presents|this work proposes|"
        r"this work presents|this work introduces|"
        r"we describe|we formulate|we define|"
        r"a novel|a new approach|a new framework|a new method|"
        r"new model|new algorithm|new architecture"
        r")\b",
        re.IGNORECASE,
    ),
    "comparison": re.compile(
        r"\b("
        r"compared (to|with)|in comparison (to|with)|"
        r"versus|outperforms|surpasses|exceeds|"
        r"performs better|performs worse|"
        r"superior to|inferior to|"
        r"state.of.the.art|state of the art|baseline"
        r")\b",
        re.IGNORECASE,
    ),
    "limitation": re.compile(
        r"\b("
        r"however|nevertheless|despite|limitation|"
        r"fails to|does not|cannot|can not|"
        r"we acknowledge|challenging|difficult|"
        r"remains an open|open problem|future work"
        r")\b",
        re.IGNORECASE,
    ),
    "dataset": re.compile(
        r"\b("
        r"we evaluate(d)? on|evaluated on|"
        r"benchmark(s)?|dataset(s)?|"
        r"using the \w+ dataset|on the \w+ benchmark|"
        r"train(ed)? on|test(ed)? on"
        r")\b",
        re.IGNORECASE,
    ),
}

# Minimum character length for a sentence to be considered as a claim.
_MIN_SENTENCE_LENGTH = 30

# A very short sentence is almost certainly a heading or fragment, not a claim.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Tokens that, if the sentence is *only* about them, indicate non-claim boilerplate.
_BOILERPLATE = re.compile(
    r"^("
    r"in this (paper|work|study)|"
    r"this (paper|work|study) (is (organised|organized)|focuses|aims)|"
    r"the rest of (this|the) paper|"
    r"section \d|"
    r"we (also )?(briefly )?(describe|discuss|review|survey)|"
    r"the paper is (structured|organized)"
    r")",
    re.IGNORECASE,
)

# Heuristic confidence assigned per claim type (not a scientific probability).
_TYPE_CONFIDENCE: dict[str, float] = {
    "finding": 0.7,
    "method": 0.75,
    "comparison": 0.65,
    "limitation": 0.60,
    "dataset": 0.60,
}


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimCandidate:
    """A single candidate claim extracted from a research abstract.

    Attributes
    ----------
    text:
        The original sentence text, lightly cleaned (leading/trailing
        whitespace collapsed; Unicode normalized to NFC).
    normalized_text:
        A canonical form suitable for deduplication.  Lower-cased,
        punctuation-stripped, whitespace-collapsed.
    claim_type:
        One of the keys from ``CLAIM_PATTERNS``:
        ``"finding"``, ``"method"``, ``"comparison"``,
        ``"limitation"``, or ``"dataset"``.
    sentence_index:
        Zero-based position of this sentence in the source text.
        Preserved for provenance tracing.
    char_start:
        Character offset of the sentence in the original text, or
        ``None`` when the offset cannot be determined reliably.
    char_end:
        Exclusive character offset of the end of the sentence, or
        ``None`` when unavailable.
    extraction_method:
        Always ``"deterministic"`` for this extractor; reserved for
        future NLP or LLM extractors.
    confidence:
        A heuristic estimate in [0, 1] based on claim type.
        This is NOT a calibrated scientific probability.
    """

    text: str
    normalized_text: str
    claim_type: str
    sentence_index: int = 0
    char_start: int | None = None
    char_end: int | None = None
    extraction_method: str = "deterministic"
    confidence: float = 0.65


# ---------------------------------------------------------------------------
# Protocol — allows future LLM-assisted extractor substitution
# ---------------------------------------------------------------------------


@runtime_checkable
class ClaimExtractorProtocol(Protocol):
    """Interface that any claim extractor must satisfy.

    Implement this protocol to substitute a future NLP or LLM-assisted
    extractor without changing persistence or temporal-analysis code.
    """

    def extract(self, text: str) -> list[ClaimCandidate]:
        """Return candidate claims from *text* (typically an abstract)."""
        ...


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split *text* into sentences using a lightweight heuristic splitter.

    Rules
    -----
    * Split on ``. ``, ``! ``, ``? `` followed by an uppercase letter.
    * Treat abbreviations ending in a digit (e.g. ``e.g. 3``) as *not*
      sentence boundaries (they pass through unchanged because they are
      not followed by an uppercase letter).
    * Strip each candidate and discard blanks.

    Returns
    -------
    list[str]
        Non-empty, stripped sentence strings.
    """
    if not text or not text.strip():
        return []

    text = unicodedata.normalize("NFC", text)
    # Collapse internal whitespace runs (newlines, tabs) to single spaces
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r" {2,}", " ", text).strip()

    parts = _SENTENCE_BOUNDARY.split(text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_claim(text: str) -> str:
    """Return a canonical, deduplication-ready form of *text*.

    Steps
    -----
    1. Unicode NFC normalization.
    2. Lower-case.
    3. Strip all punctuation characters.
    4. Collapse whitespace to single spaces.
    5. Strip leading/trailing whitespace.

    The normalized form is **never** stored as the display text; it is
    only used for identity comparison and the ``normalized_text`` DB column.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).lower()
    text = _PUNCT.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Claim extractor (deterministic implementation of ClaimExtractorProtocol)
# ---------------------------------------------------------------------------


class DeterministicClaimExtractor:
    """Deterministic, rule-based implementation of :class:`ClaimExtractorProtocol`.

    This class wraps :func:`extract_claim_candidates` in the Protocol
    interface so it can be swapped for an NLP or LLM extractor without
    changing any persistence or analysis code.

    Confidence values are heuristic estimates, not scientific probabilities.
    """

    def extract(self, text: str) -> list[ClaimCandidate]:
        """Delegate to the module-level :func:`extract_claim_candidates`."""
        return extract_claim_candidates(text)


def extract_claim_candidates(text: str) -> list[ClaimCandidate]:
    """Extract candidate claims from *text* (typically a paper abstract).

    Strategy
    --------
    1. Split *text* into sentences.
    2. For each sentence, check each pattern in ``CLAIM_PATTERNS`` in
       priority order (finding → method → comparison → limitation → dataset).
    3. Skip sentences that are too short or are pure boilerplate.
    4. Emit at most one ``ClaimCandidate`` per sentence (first-match wins).
    5. Deduplicate by ``normalized_text`` so identical sentences from the
       same abstract do not produce duplicate candidates.
    6. Track sentence index and character offsets for provenance.

    Parameters
    ----------
    text:
        Raw abstract or evidence text.  ``None``, empty, or whitespace-only
        inputs return an empty list without raising.

    Returns
    -------
    list[ClaimCandidate]
        Ordered as they appear in *text*; duplicates removed.
    """
    if not text or not text.strip():
        return []

    # Normalise whitespace before offset tracking
    normalised = unicodedata.normalize("NFC", text)
    normalised = re.sub(r"[ \t]*\n[ \t]*", " ", normalised)
    normalised = re.sub(r" {2,}", " ", normalised).strip()

    sentences = split_sentences(text)
    seen_normalized: set[str] = set()
    candidates: list[ClaimCandidate] = []

    # Priority order for claim-type assignment when multiple patterns match.
    priority: list[str] = ["finding", "method", "comparison", "limitation", "dataset"]

    search_start = 0
    for sentence_index, sentence in enumerate(sentences):
        if len(sentence) < _MIN_SENTENCE_LENGTH:
            # Still advance the search cursor so offsets stay accurate.
            pos = normalised.find(sentence, search_start)
            if pos != -1:
                search_start = pos + len(sentence)
            continue
        if _BOILERPLATE.match(sentence):
            pos = normalised.find(sentence, search_start)
            if pos != -1:
                search_start = pos + len(sentence)
            continue

        matched_type: str | None = None
        for claim_type in priority:
            if CLAIM_PATTERNS[claim_type].search(sentence):
                matched_type = claim_type
                break

        if matched_type is None:
            pos = normalised.find(sentence, search_start)
            if pos != -1:
                search_start = pos + len(sentence)
            continue

        norm = normalize_claim(sentence)
        if norm in seen_normalized:
            pos = normalised.find(sentence, search_start)
            if pos != -1:
                search_start = pos + len(sentence)
            continue

        # Locate character offsets in the normalised text.
        char_start: int | None = None
        char_end: int | None = None
        pos = normalised.find(sentence, search_start)
        if pos != -1:
            char_start = pos
            char_end = pos + len(sentence)
            search_start = char_end

        seen_normalized.add(norm)
        candidates.append(
            ClaimCandidate(
                text=unicodedata.normalize("NFC", sentence.strip()),
                normalized_text=norm,
                claim_type=matched_type,
                sentence_index=sentence_index,
                char_start=char_start,
                char_end=char_end,
                extraction_method="deterministic",
                confidence=_TYPE_CONFIDENCE.get(matched_type, 0.65),
            )
        )

    return candidates
