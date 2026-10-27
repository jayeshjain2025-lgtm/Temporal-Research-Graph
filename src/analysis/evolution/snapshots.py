from collections.abc import Iterable

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    Affiliation,
    Authorship,
    Claim,
    Citation,
    Dataset,
    DatasetUsage,
    Institution,
    Method,
    Paper,
    PaperClaim,
    PaperTopic,
    Researcher,
    Technology,
    TechnologyUsage,
    Topic,
    TopicHierarchy,
    UsesMethod,
)


def available_years(session: Session) -> list[int]:
    years = session.scalars(
        select(Paper.publication_year)
        .where(Paper.publication_year.is_not(None))
        .distinct()
        .order_by(Paper.publication_year)
    ).all()
    return [year for year in years if year is not None]


def yearly_snapshots(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[int, nx.MultiDiGraph]:
    return {year: build_snapshot(session, year, paper_ids=paper_ids) for year in range(start_year, end_year + 1)}


def build_snapshot(session: Session, year: int, paper_ids: set[int] | None = None) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(snapshot_year=year)
    statement = select(Paper).where(Paper.publication_year.is_not(None), Paper.publication_year <= year)
    if paper_ids is not None:
        if not paper_ids:
            return graph
        statement = statement.where(Paper.id.in_(paper_ids))
    papers = session.scalars(statement).all()
    paper_ids = {paper.id for paper in papers}

    for paper in papers:
        graph.add_node(_node("paper", paper.id), type="paper", label=paper.title, year=paper.publication_year, external_id=paper.external_id)

    _add_authorships(session, graph, paper_ids)
    # Affiliations are researcher-level facts, so include them only for
    # researchers represented by the snapshot's selected papers/corpus.
    snapshot_researchers = {
        int(node.rsplit(":", 1)[1])
        for node, data in graph.nodes(data=True)
        if data.get("type") == "researcher"
    }
    _add_affiliations(session, graph, year, snapshot_researchers)
    _add_citations(session, graph, paper_ids, year)
    _add_paper_topics(session, graph, paper_ids)
    _add_methods(session, graph, paper_ids)
    _add_datasets(session, graph, paper_ids)
    _add_technologies(session, graph, paper_ids)
    _add_topic_hierarchy(session, graph)
    _add_claim_edges(session, graph, paper_ids)
    return graph


def snapshot_summary(graph: nx.MultiDiGraph) -> dict:
    edge_counts: dict[str, int] = {}
    node_counts: dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        node_counts[data.get("type", "unknown")] = node_counts.get(data.get("type", "unknown"), 0) + 1
    for _, _, data in graph.edges(data=True):
        rel = data.get("relationship", "UNKNOWN")
        edge_counts[rel] = edge_counts.get(rel, 0) + 1
    return {
        "snapshot_year": graph.graph.get("snapshot_year"),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "node_counts": node_counts,
        "edge_counts": edge_counts,
    }


def edge_identity(source: str, target: str, data: dict) -> tuple[str, str, str]:
    return (source, data.get("relationship", "UNKNOWN"), target)


def edge_identities(graph: nx.MultiDiGraph) -> set[tuple[str, str, str]]:
    return {edge_identity(source, target, data) for source, target, data in graph.edges(data=True)}


def _add_node_from_model(graph: nx.MultiDiGraph, kind: str, item, **extra) -> None:
    graph.add_node(_node(kind, item.id), type=kind, label=getattr(item, "name", None) or getattr(item, "title", None), **extra)


def _add_authorships(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    if not paper_ids:
        return
    rows = session.execute(
        select(Authorship, Researcher)
        .join(Researcher, Researcher.id == Authorship.researcher_id)
        .where(Authorship.paper_id.in_(paper_ids))
    )
    for authorship, researcher in rows:
        _add_node_from_model(graph, "researcher", researcher, external_id=researcher.external_id)
        graph.add_edge(_node("researcher", researcher.id), _node("paper", authorship.paper_id), relationship="AUTHORED", provenance_id=authorship.provenance_id)


def _add_affiliations(session: Session, graph: nx.MultiDiGraph, year: int, researcher_ids: set[int]) -> None:
    if not researcher_ids:
        return
    rows = session.execute(
        select(Affiliation, Researcher, Institution)
        .join(Researcher, Researcher.id == Affiliation.researcher_id)
        .join(Institution, Institution.id == Affiliation.institution_id)
        .where(Affiliation.researcher_id.in_(researcher_ids))
    )
    for affiliation, researcher, institution in rows:
        if not _valid_in_year(affiliation.valid_from, affiliation.valid_to, year):
            continue
        _add_node_from_model(graph, "researcher", researcher, external_id=researcher.external_id)
        _add_node_from_model(graph, "institution", institution, external_id=institution.external_id)
        graph.add_edge(
            _node("researcher", researcher.id),
            _node("institution", institution.id),
            relationship="AFFILIATED_WITH",
            valid_from=affiliation.valid_from,
            valid_to=affiliation.valid_to,
            observed_at=affiliation.observed_at,
            provenance_id=affiliation.provenance_id,
        )


def _add_citations(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int], year: int) -> None:
    if not paper_ids:
        return
    rows = session.scalars(
        select(Citation).where(Citation.citing_paper_id.in_(paper_ids), Citation.cited_paper_id.in_(paper_ids))
    )
    for citation in rows:
        if citation.event_year and citation.event_year > year:
            continue
        graph.add_edge(_node("paper", citation.citing_paper_id), _node("paper", citation.cited_paper_id), relationship="CITES", event_date=citation.event_date, event_year=citation.event_year, provenance_id=citation.provenance_id)


def _add_paper_topics(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    _add_paper_entity_edges(session, graph, paper_ids, PaperTopic, Topic, "topic", "STUDIES", PaperTopic.topic_id)


def _add_methods(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    _add_paper_entity_edges(session, graph, paper_ids, UsesMethod, Method, "method", "USES_METHOD", UsesMethod.method_id)


def _add_datasets(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    _add_paper_entity_edges(session, graph, paper_ids, DatasetUsage, Dataset, "dataset", "USES_DATASET", DatasetUsage.dataset_id)


def _add_technologies(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    _add_paper_entity_edges(session, graph, paper_ids, TechnologyUsage, Technology, "technology", "USES_TECHNOLOGY", TechnologyUsage.technology_id)


def _add_paper_entity_edges(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int], relation_model, entity_model, kind: str, relationship: str, entity_column) -> None:
    if not paper_ids:
        return
    rows = session.execute(
        select(relation_model, entity_model)
        .join(entity_model, entity_model.id == entity_column)
        .where(relation_model.paper_id.in_(paper_ids))
    )
    for relation, entity in rows:
        extras = {}
        if kind == "method":
            extras["method_type"] = entity.method_type
        if kind == "technology":
            extras["technology_type"] = entity.technology_type
        _add_node_from_model(graph, kind, entity, **extras)
        graph.add_edge(_node("paper", relation.paper_id), _node(kind, entity.id), relationship=relationship, provenance_id=relation.provenance_id)


def _add_topic_hierarchy(session: Session, graph: nx.MultiDiGraph) -> None:
    rows = session.scalars(select(TopicHierarchy))
    for row in rows:
        child = _node("topic", row.child_topic_id)
        parent = _node("topic", row.parent_topic_id)
        if child in graph and parent in graph:
            graph.add_edge(child, parent, relationship="SUBTOPIC_OF", provenance_id=row.provenance_id)


def _add_claim_edges(session: Session, graph: nx.MultiDiGraph, paper_ids: set[int]) -> None:
    if not paper_ids:
        return
    rows = session.execute(
        select(PaperClaim, Claim)
        .join(Claim, Claim.id == PaperClaim.claim_id)
        .where(PaperClaim.paper_id.in_(paper_ids))
    )
    for row, claim in rows:
        graph.add_node(_node("claim", claim.id), type="claim", label=claim.text)
        graph.add_edge(_node("paper", row.paper_id), _node("claim", row.claim_id), relationship=row.relation_type, provenance_id=row.provenance_id)


def _valid_in_year(valid_from, valid_to, year: int) -> bool:
    from_year = valid_from.year if valid_from else None
    to_year = valid_to.year if valid_to else None
    if from_year and from_year > year:
        return False
    if to_year and to_year < year:
        return False
    return True


def _node(kind: str, identifier: int) -> str:
    return f"{kind}:{identifier}"
