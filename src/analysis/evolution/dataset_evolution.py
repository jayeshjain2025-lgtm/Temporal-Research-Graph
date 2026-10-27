from collections import defaultdict

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.models import Dataset, DatasetUsage, Paper


def dataset_usage(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[str, dict[int, int]]:
    statement = (
        select(Dataset.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(DatasetUsage, DatasetUsage.dataset_id == Dataset.id)
        .join(Paper, Paper.id == DatasetUsage.paper_id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(Dataset.name, Paper.publication_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            return {}
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    usage: dict[str, dict[int, int]] = defaultdict(lambda: {year: 0 for year in range(start_year, end_year + 1)})
    for dataset, year, count in rows:
        usage[dataset][year] = count
    return dict(usage)


def dataset_trends(session: Session, start_year: int, end_year: int, limit: int = 10, paper_ids: set[int] | None = None) -> list[dict]:
    usage = dataset_usage(session, start_year, end_year, paper_ids)
    trends = []
    for dataset, yearly in usage.items():
        first_seen = next((year for year in range(start_year, end_year + 1) if yearly.get(year, 0) > 0), None)
        if first_seen is None:
            continue
        latest = yearly.get(end_year, 0)
        first = yearly.get(first_seen, 0)
        trend = "increasing" if latest > first else "decreasing" if latest < first else "stable"
        trends.append(
            {
                "dataset": dataset,
                "first_seen_year": first_seen,
                "latest_usage": latest,
                "trend": trend,
            }
        )
    return sorted(trends, key=lambda item: (item["trend"] != "increasing", -item["latest_usage"], item["dataset"]))[:limit]
