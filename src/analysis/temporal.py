from collections import defaultdict

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.models import Authorship, Dataset, DatasetUsage, Method, Paper, PaperTopic, Topic, UsesMethod


def papers_per_year(session: Session) -> dict[int, int]:
    rows = session.execute(select(Paper.publication_year, func.count(Paper.id)).where(Paper.publication_year.is_not(None)).group_by(Paper.publication_year).order_by(Paper.publication_year))
    return {year: count for year, count in rows}


def active_researchers_per_year(session: Session) -> dict[int, int]:
    rows = session.execute(
        select(Paper.publication_year, func.count(distinct(Authorship.researcher_id)))
        .join(Authorship, Authorship.paper_id == Paper.id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Paper.publication_year)
        .order_by(Paper.publication_year)
    )
    return {year: count for year, count in rows}


def topic_growth(session: Session) -> dict[str, dict[int, int]]:
    rows = session.execute(
        select(Topic.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(PaperTopic, PaperTopic.topic_id == Topic.id)
        .join(Paper, Paper.id == PaperTopic.paper_id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Topic.name, Paper.publication_year)
        .order_by(Topic.name, Paper.publication_year)
    )
    return _nested(rows)


def method_adoption_rate(session: Session) -> dict[str, dict[int, float]]:
    field_counts = papers_per_year(session)
    rows = session.execute(
        select(Method.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(UsesMethod, UsesMethod.method_id == Method.id)
        .join(Paper, Paper.id == UsesMethod.paper_id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Method.name, Paper.publication_year)
        .order_by(Method.name, Paper.publication_year)
    )
    adoption: dict[str, dict[int, float]] = defaultdict(dict)
    for method_name, year, count in rows:
        denominator = field_counts.get(year, 0)
        adoption[method_name][year] = count / denominator if denominator else 0.0
    return dict(adoption)


def dataset_usage_over_time(session: Session) -> dict[str, dict[int, int]]:
    rows = session.execute(
        select(Dataset.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(DatasetUsage, DatasetUsage.dataset_id == Dataset.id)
        .join(Paper, Paper.id == DatasetUsage.paper_id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Dataset.name, Paper.publication_year)
        .order_by(Dataset.name, Paper.publication_year)
    )
    return _nested(rows)


def relationships_appearing_after(session: Session, cutoff_year: int) -> list[dict]:
    rows = session.execute(
        select(Method.name, func.min(Paper.publication_year))
        .join(UsesMethod, UsesMethod.method_id == Method.id)
        .join(Paper, Paper.id == UsesMethod.paper_id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Method.name)
        .having(func.min(Paper.publication_year) > cutoff_year)
    )
    return [{"relationship": "USES_METHOD", "target": name, "first_seen_year": year} for name, year in rows]


def disappearing_relationships(session: Session, current_year: int, lookback_years: int = 3) -> list[dict]:
    rows = session.execute(
        select(Method.name, func.max(Paper.publication_year))
        .join(UsesMethod, UsesMethod.method_id == Method.id)
        .join(Paper, Paper.id == UsesMethod.paper_id)
        .where(Paper.publication_year.is_not(None))
        .group_by(Method.name)
        .having(func.max(Paper.publication_year) < current_year - lookback_years)
    )
    return [{"relationship": "USES_METHOD", "target": name, "last_seen_year": year, "note": "Not observed recently; this does not mean the relationship is false."} for name, year in rows]


def _nested(rows) -> dict[str, dict[int, int]]:
    values: dict[str, dict[int, int]] = defaultdict(dict)
    for name, year, count in rows:
        values[name][year] = count
    return dict(values)
