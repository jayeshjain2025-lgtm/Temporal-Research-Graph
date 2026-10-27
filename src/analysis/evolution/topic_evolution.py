from collections import defaultdict

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.models import Paper, PaperTopic, Topic


def topic_activity(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[str, dict[int, int]]:
    statement = (
        select(Topic.name, Paper.publication_year, func.count(distinct(Paper.id)))
        .join(PaperTopic, PaperTopic.topic_id == Topic.id)
        .join(Paper, Paper.id == PaperTopic.paper_id)
        .where(Paper.publication_year >= start_year, Paper.publication_year <= end_year)
        .group_by(Topic.name, Paper.publication_year)
        .order_by(Topic.name, Paper.publication_year)
    )
    if paper_ids is not None:
        if not paper_ids:
            return {}
        statement = statement.where(Paper.id.in_(paper_ids))
    rows = session.execute(statement)
    activity: dict[str, dict[int, int]] = defaultdict(lambda: {year: 0 for year in range(start_year, end_year + 1)})
    for topic, year, count in rows:
        activity[topic][year] = count
    return dict(activity)


def topic_growth_rates(session: Session, start_year: int, end_year: int, paper_ids: set[int] | None = None) -> dict[str, dict[int, float | None]]:
    activity = topic_activity(session, start_year, end_year, paper_ids)
    rates: dict[str, dict[int, float | None]] = {}
    for topic, yearly in activity.items():
        rates[topic] = {}
        previous = None
        for year in range(start_year, end_year + 1):
            current = yearly.get(year, 0)
            if previous is None:
                rates[topic][year] = None
            elif previous == 0:
                rates[topic][year] = None if current == 0 else 1.0
            else:
                rates[topic][year] = (current - previous) / previous
            previous = current
    return rates


def emerging_topics(session: Session, start_year: int, end_year: int, limit: int = 10, paper_ids: set[int] | None = None) -> list[dict]:
    activity = topic_activity(session, start_year, end_year, paper_ids)
    ranked = []
    for topic, yearly in activity.items():
        first_seen = next((year for year in range(start_year, end_year + 1) if yearly.get(year, 0) > 0), None)
        latest = yearly.get(end_year, 0)
        baseline = yearly.get(start_year, 0)
        if first_seen is None:
            continue
        ranked.append(
            {
                "topic": topic,
                "first_seen_year": first_seen,
                "start_count": baseline,
                "latest_count": latest,
                "absolute_growth": latest - baseline,
            }
        )
    return sorted(ranked, key=lambda item: (item["first_seen_year"], -item["absolute_growth"], item["topic"]))[:limit]
