from src.ingestion.schemas import SourceTopic
from src.normalization.text import normalize_text


ALLOWED_DOMAIN_NAMES = {
    "physical science",
    "social science",
}

ALLOWED_FIELD_NAMES = {
    "computer science",
    "decision science",
    "mathematics",
    "engineering",
}

ALLOWED_SUBFIELD_NAMES = {
    "artificial intelligence",
    "computer network and communication",
    "computer science application",
    "human-computer interaction",
    "information system",
    "logic",
    "software",
    "theoretical computer science",
}

ALLOWED_LEGACY_CONCEPT_IDS = {
    "https://openalex.org/C41008148",  # Computer science
    "https://openalex.org/C154945302",  # Artificial intelligence
    "https://openalex.org/C119857082",  # Machine learning
    "https://openalex.org/C2778407487",  # Knowledge graph
    "https://openalex.org/C111919701",  # Knowledge representation and reasoning
    "https://openalex.org/C132525143",  # Graph
    "https://openalex.org/C80444323",  # Theoretical computer science
    "https://openalex.org/C204321447",  # Natural language processing
    "https://openalex.org/C2522767166",  # Question answering
    "https://openalex.org/C2776214188",  # Inference
}

ALLOWED_LEGACY_CONCEPT_NAMES = {
    "artificial intelligence",
    "computer science",
    "database",
    "graph",
    "graph neural network",
    "information retrieval",
    "knowledge graph",
    "knowledge graph completion",
    "knowledge representation",
    "knowledge representation and reasoning",
    "link prediction",
    "machine learning",
    "natural language processing",
    "neural network",
    "question answering",
    "semantic web",
    "scholarly knowledge graph",
    "temporal database",
    "temporal knowledge graph",
    "temporal logic",
    "temporal reasoning",
    "theoretical computer science",
}


def relevant_topic(topic: SourceTopic) -> bool:
    if topic.score is not None and topic.score < 0.2:
        return False

    if _matches_hierarchy(topic):
        return True

    # Legacy OpenAlex concepts do not include domain/field/subfield metadata in
    # work payloads, so accept only known in-domain concept IDs/names.
    if topic.external_id in ALLOWED_LEGACY_CONCEPT_IDS:
        return True
    return normalize_text(topic.name) in ALLOWED_LEGACY_CONCEPT_NAMES


def canonical_topic_name(topic: SourceTopic) -> str:
    name = topic.name.strip()
    aliases = {
        "knowledge representation and reasoning": "Knowledge Representation",
    }
    return aliases.get(normalize_text(name), name)


def _matches_hierarchy(topic: SourceTopic) -> bool:
    domain = normalize_text(topic.domain_name)
    field = normalize_text(topic.field_name)
    subfield = normalize_text(topic.subfield_name)
    return (
        domain in ALLOWED_DOMAIN_NAMES
        or field in ALLOWED_FIELD_NAMES
        or subfield in ALLOWED_SUBFIELD_NAMES
    )
