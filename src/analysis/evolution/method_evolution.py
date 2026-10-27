from collections import defaultdict

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.models import Method, Paper, UsesMethod


def method_counts(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[str, dict[int, int]]:
    statement = (
        select(Method.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(UsesMethod, UsesMethod.method_id == Method.id)
        .join(Paper, Paper.id == UsesMethod.paper_id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(Method.name, Paper.publication_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            return {}
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    counts: dict[str, dict[int, int]] = defaultdict(lambda: {year: 0 for year in range(start_year, end_year + 1)})
    for method, year, count in rows:
        counts[method][year] = count
    return dict(counts)


def method_adoption(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[str, dict[int, float]]:
    denominators = _paper_counts(session, start_year, end_year, paper_ids)
    counts = method_counts(session, start_year, end_year, paper_ids)
    adoption: dict[str, dict[int, float]] = {}
    for method, yearly in counts.items():
        adoption[method] = {}
        for year in range(start_year, end_year + 1):
            denominator = denominators.get(year, 0)
            adoption[method][year] = yearly.get(year, 0) / denominator if denominator else 0.0
    return adoption


def method_trends(session: Session, start_year: int, end_year: int, limit: int = 10, paper_ids: set[int] | None = None) -> list[dict]:
    adoption = method_adoption(session, start_year, end_year, paper_ids)
    counts = method_counts(session, start_year, end_year, paper_ids)
    trends = []
    for method, yearly in adoption.items():
        first_seen = next((year for year in range(start_year, end_year + 1) if counts[method].get(year, 0) > 0), None)
        if first_seen is None:
            continue
        latest = yearly.get(end_year, 0.0)
        baseline = yearly.get(first_seen, 0.0)
        direction = "increasing" if latest > baseline else "decreasing" if latest < baseline else "stable"
        trends.append(
            {
                "method": method,
                "first_seen_year": first_seen,
                "latest_adoption_rate": latest,
                "trend": direction,
            }
        )
    return sorted(trends, key=lambda item: (item["trend"] != "increasing", -item["latest_adoption_rate"], item["method"]))[:limit]


def _paper_counts(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[int, int]:
    statement = (
        select(Paper.publication_year, func.count(Paper.id))
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(Paper.publication_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            return {}
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    return {year: count for year, count in rows}
