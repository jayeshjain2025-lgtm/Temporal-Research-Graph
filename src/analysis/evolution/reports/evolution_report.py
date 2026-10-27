from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis.evolution.corpus_filter import corpus_paper_ids
from src.analysis.evolution.dataset_evolution import dataset_trends, dataset_usage
from src.analysis.evolution.graph.centrality import betweenness_centrality, central_entities_by_type, degree_centrality
from src.analysis.evolution.graph.communities import structural_communities
from src.analysis.evolution.graph.components import connected_components
from src.analysis.evolution.method_evolution import method_adoption, method_trends
from src.analysis.evolution.relationship_evolution import first_seen_relationships, not_observed_after_year, not_observed_relationships, relationship_changes, relationship_observation_windows
from src.analysis.evolution.researcher_evolution import central_researchers_over_time, researcher_cohorts
from src.analysis.evolution.snapshots import snapshot_summary, yearly_snapshots
from src.analysis.evolution.topic_evolution import emerging_topics, topic_activity, topic_growth_rates
from src.models import Paper


def build_evolution_report(session: Session, start_year: int, end_year: int, corpus_name: str | None = None) -> dict:
    paper_ids = corpus_paper_ids(session, corpus_name)
    snapshots = yearly_snapshots(session, start_year, end_year, paper_ids=paper_ids)
    final_graph = snapshots[end_year]
    papers = _paper_counts(session, start_year, end_year, paper_ids=paper_ids)
    researcher_evolution = researcher_cohorts(session, start_year, end_year, paper_ids=paper_ids)
    relationships = relationship_changes(snapshots)

    return {
        "title": "TEMPORAL RESEARCH EVOLUTION",
        "period": {"start_year": start_year, "end_year": end_year},
        "corpus": corpus_name or "all",
        "scope_note": "All results are derived from the bounded PostgreSQL corpus; absence means not observed in the corpus.",
        "paper_growth": papers,
        "researcher_growth": researcher_evolution,
        "temporal_snapshots": {year: snapshot_summary(graph) for year, graph in snapshots.items()},
        "topic_growth": {
            "activity": topic_activity(session, start_year, end_year, paper_ids=paper_ids),
            "growth_rates": topic_growth_rates(session, start_year, end_year, paper_ids=paper_ids),
            "emerging_topics": emerging_topics(session, start_year, end_year, paper_ids=paper_ids),
        },
        "method_adoption": {
            "rates": method_adoption(session, start_year, end_year, paper_ids=paper_ids),
            "growing_methods": method_trends(session, start_year, end_year, paper_ids=paper_ids),
        },
        "dataset_adoption": {
            "usage": dataset_usage(session, start_year, end_year, paper_ids=paper_ids),
            "important_datasets": dataset_trends(session, start_year, end_year, paper_ids=paper_ids),
        },
        "network_evolution": {
            "new_relationships_by_year": {year: data["new_relationships"] for year, data in relationships.items()},
            "not_observed_after_previous_snapshot": not_observed_relationships(snapshots),
            "observation_windows": relationship_observation_windows(session, start_year, end_year, paper_ids=paper_ids),
            "not_observed_after_year": not_observed_after_year(session, start_year, end_year, paper_ids=paper_ids),
            "first_seen_relationships": first_seen_relationships(snapshots),
        },
        "graph_structure": {
            "degree_centrality": degree_centrality(final_graph),
            "betweenness_centrality": betweenness_centrality(final_graph),
            "central_entities_by_type": central_entities_by_type(final_graph),
            "connected_components": connected_components(final_graph),
            "communities": structural_communities(final_graph),
        },
        "researcher_evolution": {
            "cohorts": researcher_evolution,
            "central_researchers": central_researchers_over_time(session, start_year, end_year, paper_ids=paper_ids),
        },
        "questions": {
            "how_has_tkg_evolved": {
                "paper_growth": papers,
                "researcher_growth": researcher_evolution,
                "topic_growth": topic_activity(session, start_year, end_year, paper_ids=paper_ids),
                "method_adoption": method_adoption(session, start_year, end_year, paper_ids=paper_ids),
                "dataset_adoption": dataset_usage(session, start_year, end_year, paper_ids=paper_ids),
            },
            "which_methods_became_more_common": method_trends(session, start_year, end_year, paper_ids=paper_ids),
            "which_datasets_became_more_important": dataset_trends(session, start_year, end_year, paper_ids=paper_ids),
            "which_researchers_became_central": central_researchers_over_time(session, start_year, end_year, paper_ids=paper_ids),
            "which_topics_emerged_recently": emerging_topics(session, start_year, end_year, paper_ids=paper_ids),
        },
    }


def _paper_counts(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[int, int]:
    rows = session.execute(
        select(Paper.publication_year, func.count(Paper.id))
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(Paper.publication_year)
        .order_by(Paper.publication_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            return {year: 0 for year in range(start_year, end_year + 1)}
        rows = session.execute(
            select(Paper.publication_year, func.count(Paper.id))
            .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year, Paper.id.in_(paper_ids))
            .group_by(Paper.publication_year)
            .order_by(Paper.publication_year)
        )
    counts = {year: 0 for year in range(start_year, end_year + 1)}
    counts.update({year: count for year, count in rows})
    return counts


def format_evolution_summary(report: dict) -> str:
    start_year = report["period"]["start_year"]
    end_year = report["period"]["end_year"]
    papers = report["paper_growth"]
    researchers = report["researcher_growth"]
    start_papers = papers.get(start_year, 0)
    end_papers = papers.get(end_year, 0)
    start_researchers = researchers.get(start_year, {}).get("active", 0)
    end_researchers = researchers.get(end_year, {}).get("active", 0)
    corpus = report.get("corpus", "all")
    title = f"TEMPORAL RESEARCH EVOLUTION: {corpus.upper()}" if corpus != "all" else "TEMPORAL RESEARCH EVOLUTION"
    lines = [
        title,
        "=" * len(title),
        "",
        f"{start_year} -> {end_year}",
        "",
        f"Papers: {start_papers} -> {end_papers}",
        f"Researchers: {start_researchers} -> {end_researchers}",
        "",
        "Emerging Topics:",
    ]
    lines.extend([f"- {item['topic']} (first seen {item['first_seen_year']}, latest count {item['latest_count']})" for item in report["topic_growth"]["emerging_topics"][:8]])
    lines.append("")
    lines.append("Growing Methods:")
    lines.extend([f"- {item['method']} ({item['trend']}, latest adoption {item['latest_adoption_rate']:.2%})" for item in report["method_adoption"]["growing_methods"][:8]])
    lines.append("")
    lines.append("Dataset Adoption:")
    lines.extend([f"- {item['dataset']} ({item['trend']}, latest usage {item['latest_usage']})" for item in report["dataset_adoption"]["important_datasets"][:8]])
    lines.append("")
    lines.append("Research Communities:")
    lines.extend([f"- {item['structural_label']} (size {item['size']})" for item in report["graph_structure"]["communities"][:5]])
    lines.append("")
    lines.append("Central Entities:")
    lines.extend([f"- {item['label']} [{item['type']}] score={item['score']:.3f}" for item in report["graph_structure"]["degree_centrality"][:8]])
    lines.append("")
    lines.append("Note: Not-observed relationships are corpus observations, not proof that real-world relationships ceased.")
    return "\n".join(lines)
