from dataclasses import dataclass

from src.normalization.text import normalize_text


@dataclass(frozen=True)
class ExtractedConcept:
    name: str
    concept_type: str
    evidence: str


METHOD_TERMS = {
    "graph neural network": "model/architecture",
    "knowledge graph embedding": "technique",
    "link prediction": "method",
    "temporal reasoning": "method",
    "rule learning": "algorithm",
    "representation learning": "technique",
    "neural network": "model/architecture",
    "transformer": "model/architecture",
}

DATASET_TERMS = [
    "icews",
    "gdelt",
    "wikidata",
    "yago",
    "dbpedia",
    "wordnet",
    "freebase",
    "ogb",
]

TECHNOLOGY_TERMS = {
    "rdf": "standard",
    "sparql": "query_language",
    "owl": "ontology_language",
    "networkx": "library",
}


def extract_methods(title: str, abstract: str | None) -> list[ExtractedConcept]:
    return _extract_terms(title, abstract, METHOD_TERMS)


def extract_datasets(title: str, abstract: str | None) -> list[ExtractedConcept]:
    return [ExtractedConcept(name=term.upper() if len(term) <= 5 else term.title(), concept_type="dataset", evidence=evidence) for term, evidence in _matches(title, abstract, DATASET_TERMS)]


def extract_technologies(title: str, abstract: str | None) -> list[ExtractedConcept]:
    return _extract_terms(title, abstract, TECHNOLOGY_TERMS)


def _extract_terms(title: str, abstract: str | None, terms: dict[str, str]) -> list[ExtractedConcept]:
    return [ExtractedConcept(name=term.title(), concept_type=terms[term], evidence=evidence) for term, evidence in _matches(title, abstract, terms.keys())]


def _matches(title: str, abstract: str | None, terms) -> list[tuple[str, str]]:
    haystack = f"{title} {abstract or ''}"
    normalized = normalize_text(haystack)
    found: list[tuple[str, str]] = []
    for term in terms:
        if normalize_text(term) in normalized:
            found.append((term, _snippet(haystack, term)))
    return found


def _snippet(text: str, term: str) -> str:
    lower = text.lower()
    idx = lower.find(term.lower())
    if idx < 0:
        return text[:240]
    start = max(0, idx - 80)
    end = min(len(text), idx + len(term) + 80)
    return text[start:end]
