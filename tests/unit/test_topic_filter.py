from src.ingestion.schemas import SourceTopic
from src.ingestion.topic_filter import canonical_topic_name, relevant_topic


def test_rejects_legacy_unrelated_concepts():
    assert not relevant_topic(
        SourceTopic(
            external_id="https://openalex.org/C2780980858",
            name="Dual (grammatical number)",
            score=0.55,
            source="openalex_concept",
        )
    )
    assert not relevant_topic(
        SourceTopic(
            external_id="https://openalex.org/C89611455",
            name="Mechanism (biology)",
            score=0.72,
            source="openalex_concept",
        )
    )


def test_accepts_domain_relevant_openalex_topics():
    assert relevant_topic(
        SourceTopic(
            external_id="https://openalex.org/T123",
            name="Knowledge Graph Completion",
            score=0.83,
            source="openalex_topic",
            domain_name="Physical Sciences",
            field_name="Computer Science",
            subfield_name="Artificial Intelligence",
        )
    )


def test_accepts_known_in_domain_legacy_concepts():
    assert relevant_topic(
        SourceTopic(
            external_id="https://openalex.org/C154945302",
            name="Artificial intelligence",
            score=0.33,
            source="openalex_concept",
        )
    )


def test_canonicalizes_topic_aliases():
    topic = SourceTopic(name="Knowledge representation and reasoning")
    assert canonical_topic_name(topic) == "Knowledge Representation"
