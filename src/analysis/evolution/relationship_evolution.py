from src.analysis.evolution.snapshots import edge_identities
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models import Dataset, DatasetUsage, Method, Paper, PaperTopic, Topic, UsesMethod


def relationship_changes(snapshots: dict[int, object]) -> dict[int, dict[str, list[dict]]]:
    changes: dict[int, dict[str, list[dict]]] = {}
    previous_edges: set[tuple[str, str, str]] = set()
    previous_year = None
    for year in sorted(snapshots):
        current_edges = edge_identities(snapshots[year])
        new_edges = current_edges - previous_edges
        not_observed = previous_edges - current_edges
        changes[year] = {
            "new_relationships": [_edge_dict(edge, year, "first observed") for edge in sorted(new_edges)],
            "not_observed_after_previous_snapshot": [
                {**_edge_dict(edge, previous_year, "not observed in current snapshot"), "current_year": year}
                for edge in sorted(not_observed)
            ],
        }
        previous_edges = current_edges
        previous_year = year
    return changes


def first_seen_relationships(snapshots: dict[int, object], limit: int = 50) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    first_seen = []
    for year in sorted(snapshots):
        current = edge_identities(snapshots[year])
        for edge in sorted(current - seen):
            first_seen.append(_edge_dict(edge, year, "first observed"))
        seen.update(current)
    return first_seen[:limit]


def not_observed_relationships(snapshots: dict[int, object], limit: int = 50) -> list[dict]:
    changes = relationship_changes(snapshots)
    flattened = []
    for year in sorted(changes):
        flattened.extend(changes[year]["not_observed_after_previous_snapshot"])
    return flattened[:limit]


def relationship_observation_windows(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> list[dict]:
    observations = []
    observations.extend(_paper_entity_windows(session, start_year, end_year, UsesMethod, Method, UsesMethod.method_id, "USES_METHOD", "method", paper_ids))
    observations.extend(_paper_entity_windows(session, start_year, end_year, DatasetUsage, Dataset, DatasetUsage.dataset_id, "USES_DATASET", "dataset", paper_ids))
    observations.extend(_paper_entity_windows(session, start_year, end_year, PaperTopic, Topic, PaperTopic.topic_id, "STUDIES", "topic", paper_ids))
    return sorted(observations, key=lambda item: (item["last_observed_year"], item["relationship"], item["target_label"]))


def not_observed_after_year(session: Session, start_year: int, end_year: int, limit: int = 50, paper_ids: set[int] | None = None) -> list[dict]:
    windows = relationship_observation_windows(session, start_year, end_year, paper_ids)
    missing = [item for item in windows if item["last_observed_year"] < end_year]
    for item in missing:
        item["note"] = f"Not observed after {item['last_observed_year']} in this bounded corpus; this does not prove the relationship ceased."
    return missing[:limit]


def _paper_entity_windows(session: Session, start_year: int, end_year: int, relation_model, entity_model, entity_column, relationship: str, target_type: str, paper_ids: set[int] | None) -> list[dict]:
    statement = (
        select(
            entity_model.name,
            func.min(Paper.publication_year),
            func.max(Paper.publication_year),
            func.count(func.distinct(Paper.id)),
        )
        .select_from(entity_model)
        .join(relation_model, entity_column == entity_model.id)
        .join(Paper, Paper.id == relation_model.paper_id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(entity_model.name)
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    return [
        {
            "relationship": relationship,
            "target_type": target_type,
            "target_label": name,
            "first_observed_year": first_year,
            "last_observed_year": last_year,
            "paper_count": count,
        }
        for name, first_year, last_year, count in rows
    ]


def _edge_dict(edge: tuple[str, str, str], year: int | None, note: str) -> dict:
    source, relationship, target = edge
    return {
        "source": source,
        "relationship": relationship,
        "target": target,
        "year": year,
        "note": note,
    }
