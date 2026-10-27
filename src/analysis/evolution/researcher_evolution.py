from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from src.models import Authorship, Paper, Researcher


def active_researchers_by_year(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[int, set[int]]:
    statement = (
        select(Paper.publication_year, Authorship.researcher_id)
        .join(Authorship, Authorship.paper_id == Paper.id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .distinct()
    )
    if paper_ids is not None:
        if not paper_ids:
            return {year: set() for year in range(start_year, end_year + 1)}
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    active = {year: set() for year in range(start_year, end_year + 1)}
    for year, researcher_id in rows:
        active[year].add(researcher_id)
    return active


def researcher_cohorts(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[int, dict[str, int]]:
    active = active_researchers_by_year(session, start_year, end_year, paper_ids)
    seen: set[int] = set()
    cohorts: dict[int, dict[str, int]] = {}
    for year in range(start_year, end_year + 1):
        current = active[year]
        previous = active.get(year - 1, set())
        new = current - seen
        returning = current & seen
        entering = current - previous
        leaving = previous - current
        cohorts[year] = {
            "active": len(current),
            "new": len(new),
            "returning": len(returning),
            "entering": len(entering),
            "leaving": len(leaving),
        }
        seen.update(current)
    return cohorts


def central_researchers_over_time(session: Session, start_year: int, end_year: int, limit: int = 10, paper_ids: set[int] | None = None) -> list[dict]:
    statement = (
        select(Researcher.id, Researcher.name, Paper.publication_year)
        .join(Authorship, Authorship.researcher_id == Researcher.id)
        .join(Paper, Paper.id == Authorship.paper_id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .distinct()
    )
    if paper_ids is not None:
        if not paper_ids:
            return []
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    counts: dict[int, dict] = {}
    for researcher_id, name, year in rows:
        item = counts.setdefault(researcher_id, {"researcher": name, "active_years": set(), "paper_year_count": 0})
        item["active_years"].add(year)
        item["paper_year_count"] += 1
    ranked = sorted(counts.values(), key=lambda item: (len(item["active_years"]), item["paper_year_count"], item["researcher"]), reverse=True)
    return [
        {
            "researcher": item["researcher"],
            "active_years": sorted(item["active_years"]),
            "paper_year_count": item["paper_year_count"],
        }
        for item in ranked[:limit]
    ]
