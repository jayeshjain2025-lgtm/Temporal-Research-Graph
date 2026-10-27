from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.analysis.graph_metrics import centrality, communities
from src.analysis.temporal import (
    active_researchers_per_year,
    dataset_usage_over_time,
    disappearing_relationships,
    method_adoption_rate,
    papers_per_year,
    relationships_appearing_after,
    topic_growth,
)
from src.graph.build import build_graph
from src.models import Authorship, Paper, PaperTopic, Researcher, Topic


def research_evolution_report(session: Session) -> dict:
    graph = build_graph(session)
    years = list(papers_per_year(session))
    current_year = max(years) if years else None
    cutoff_year = sorted(years)[len(years) // 2] if years else 0
    return {
        "question": "How has research on Temporal Knowledge Graphs evolved over the available time period?",
        "papers_per_year": papers_per_year(session),
        "active_researchers_per_year": active_researchers_per_year(session),
        "major_topics": major_topics(session),
        "method_adoption_rate": method_adoption_rate(session),
        "dataset_usage_over_time": dataset_usage_over_time(session),
        "important_researchers": important_researchers(session),
        "important_papers": important_papers(session),
        "communities": communities(graph),
        "centrality": centrality(graph),
        "relationships_appearing_over_time": relationships_appearing_after(session, cutoff_year),
        "disappearing_relationships": disappearing_relationships(session, current_year) if current_year else [],
        "topic_growth": topic_growth(session),
        "limitations": [
            "Disappearing relationships mean not observed in the current bounded corpus.",
            "Method and dataset extraction is deterministic and heuristic in Phase 1.",
            "OpenAlex topics are filtered by available hierarchy metadata, but they are not a manually curated project ontology.",
        ],
    }


def major_topics(session: Session, limit: int = 15) -> list[dict]:
    rows = session.execute(
        select(Topic.name, func.count(PaperTopic.paper_id).label("papers"))
        .join(PaperTopic, PaperTopic.topic_id == Topic.id)
        .group_by(Topic.name)
        .order_by(desc("papers"))
        .limit(limit)
    )
    return [{"topic": name, "papers": count} for name, count in rows]


def important_researchers(session: Session, limit: int = 15) -> list[dict]:
    rows = session.execute(
        select(Researcher.name, func.count(Authorship.paper_id).label("papers"))
        .join(Authorship, Authorship.researcher_id == Researcher.id)
        .group_by(Researcher.name)
        .order_by(desc("papers"))
        .limit(limit)
    )
    return [{"researcher": name, "papers": count} for name, count in rows]


def important_papers(session: Session, limit: int = 15) -> list[dict]:
    rows = session.execute(select(Paper.title, Paper.publication_year, Paper.venue).order_by(Paper.publication_year.desc().nullslast()).limit(limit))
    return [{"title": title, "year": year, "venue": venue} for title, year, venue in rows]
