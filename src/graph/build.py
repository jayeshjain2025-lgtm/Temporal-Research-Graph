import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    Affiliation,
    Authorship,
    Citation,
    Dataset,
    DatasetUsage,
    Institution,
    Method,
    Paper,
    PaperClaim,
    PaperTopic,
    Claim,
    Researcher,
    Technology,
    TechnologyUsage,
    Topic,
    TopicHierarchy,
    UsesMethod,
)


def build_graph(session: Session) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()

    for paper in session.scalars(select(Paper)):
        graph.add_node(_node("paper", paper.id), type="paper", label=paper.title, year=paper.publication_year, external_id=paper.external_id)
    for researcher in session.scalars(select(Researcher)):
        graph.add_node(_node("researcher", researcher.id), type="researcher", label=researcher.name, external_id=researcher.external_id)
    for institution in session.scalars(select(Institution)):
        graph.add_node(_node("institution", institution.id), type="institution", label=institution.name, external_id=institution.external_id)
    for topic in session.scalars(select(Topic)):
        graph.add_node(_node("topic", topic.id), type="topic", label=topic.name)
    for method in session.scalars(select(Method)):
        graph.add_node(_node("method", method.id), type="method", label=method.name, method_type=method.method_type)
    for dataset in session.scalars(select(Dataset)):
        graph.add_node(_node("dataset", dataset.id), type="dataset", label=dataset.name)
    for technology in session.scalars(select(Technology)):
        graph.add_node(_node("technology", technology.id), type="technology", label=technology.name, technology_type=technology.technology_type)
    for claim in session.scalars(select(Claim)):
        graph.add_node(_node("claim", claim.id), type="claim", label=claim.text)

    for row in session.scalars(select(Authorship)):
        graph.add_edge(_node("researcher", row.researcher_id), _node("paper", row.paper_id), relationship="AUTHORED", provenance_id=row.provenance_id)
    for row in session.scalars(select(Affiliation)):
        graph.add_edge(_node("researcher", row.researcher_id), _node("institution", row.institution_id), relationship="AFFILIATED_WITH", valid_from=row.valid_from, valid_to=row.valid_to, observed_at=row.observed_at, provenance_id=row.provenance_id)
    for row in session.scalars(select(Citation)):
        graph.add_edge(_node("paper", row.citing_paper_id), _node("paper", row.cited_paper_id), relationship="CITES", event_date=row.event_date, event_year=row.event_year, provenance_id=row.provenance_id)
    for row in session.scalars(select(PaperTopic)):
        graph.add_edge(_node("paper", row.paper_id), _node("topic", row.topic_id), relationship="STUDIES", provenance_id=row.provenance_id)
    for row in session.scalars(select(UsesMethod)):
        graph.add_edge(_node("paper", row.paper_id), _node("method", row.method_id), relationship="USES_METHOD", provenance_id=row.provenance_id)
    for row in session.scalars(select(DatasetUsage)):
        graph.add_edge(_node("paper", row.paper_id), _node("dataset", row.dataset_id), relationship="USES_DATASET", provenance_id=row.provenance_id)
    for row in session.scalars(select(TechnologyUsage)):
        graph.add_edge(_node("paper", row.paper_id), _node("technology", row.technology_id), relationship="USES_TECHNOLOGY", provenance_id=row.provenance_id)
    for row in session.scalars(select(TopicHierarchy)):
        graph.add_edge(_node("topic", row.child_topic_id), _node("topic", row.parent_topic_id), relationship="SUBTOPIC_OF", provenance_id=row.provenance_id)
    for row in session.scalars(select(PaperClaim)):
        graph.add_edge(_node("paper", row.paper_id), _node("claim", row.claim_id), relationship=row.relation_type, provenance_id=row.provenance_id)

    return graph


def _node(kind: str, identifier: int) -> str:
    return f"{kind}:{identifier}"
