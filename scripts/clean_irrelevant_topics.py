from pathlib import Path
import sys

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.session import session_scope  # noqa: E402
from src.ingestion.schemas import SourceTopic  # noqa: E402
from src.ingestion.topic_filter import relevant_topic  # noqa: E402
from src.models import PaperTopic, Topic  # noqa: E402


def main() -> None:
    removed_links = 0
    removed_topics = 0
    with session_scope() as session:
        topics = session.scalars(select(Topic)).all()
        for topic in topics:
            candidate = SourceTopic(
                external_id=topic.external_id,
                name=topic.name,
                source=topic.source or "database",
                domain_name=topic.domain_name,
                field_name=topic.field_name,
                subfield_name=topic.subfield_name,
            )
            if relevant_topic(candidate):
                continue

            links = session.scalars(select(PaperTopic).where(PaperTopic.topic_id == topic.id)).all()
            for link in links:
                session.delete(link)
                removed_links += 1

            remaining = session.scalar(select(func.count(PaperTopic.id)).where(PaperTopic.topic_id == topic.id))
            if remaining == 0:
                session.delete(topic)
                removed_topics += 1

    print({"removed_paper_topic_links": removed_links, "removed_topics": removed_topics})


if __name__ == "__main__":
    main()
