from datetime import date

from sqlalchemy import func, select

from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schemas import SourceAuthor, SourcePaper, SourceTopic
from src.models import Authorship, Institution, Paper, Researcher


def test_ingestion_is_idempotent(session):
    paper = SourcePaper(
        external_id="https://openalex.org/W1",
        title="Temporal Knowledge Graph Reasoning with ICEWS",
        abstract="A temporal reasoning method for link prediction on ICEWS.",
        publication_date=date(2020, 1, 1),
        publication_year=2020,
        authors=[SourceAuthor(external_id="https://openalex.org/A1", name="Ada Lovelace", position=1)],
        topics=[SourceTopic(external_id="https://openalex.org/T1", name="Temporal Knowledge Graph", field_name="Computer Science", score=0.9)],
    )

    pipeline = IngestionPipeline(session)
    pipeline.ingest([paper])
    pipeline.ingest([paper])
    session.commit()

    assert session.scalar(select(func.count(Paper.id))) == 1
    assert session.scalar(select(func.count(Researcher.id))) == 1
    assert session.scalar(select(func.count(Authorship.id))) == 1


def test_ingestion_handles_author_without_external_id(session):
    paper = SourcePaper(
        external_id="https://openalex.org/W2",
        title="Temporal Knowledge Graph Reasoning",
        abstract="A temporal reasoning method.",
        publication_date=date(2021, 1, 1),
        publication_year=2021,
        authors=[
            SourceAuthor(
                external_id=None,
                name="Unknown Researcher",
                position=1,
                institutions=[{"display_name": "Unknown University"}],
            )
        ],
        topics=[SourceTopic(external_id="https://openalex.org/T1", name="Temporal Knowledge Graph", field_name="Computer Science", score=0.9)],
    )

    IngestionPipeline(session).ingest([paper])
    session.commit()

    assert session.scalar(select(func.count(Researcher.id))) == 1
    assert session.scalar(select(func.count(Authorship.id))) == 1


def test_institution_name_collision_merges_external_id(session):
    first = SourcePaper(
        external_id="https://openalex.org/W3",
        title="Temporal Knowledge Graph Reasoning A",
        publication_date=date(2021, 1, 1),
        publication_year=2021,
        authors=[
            SourceAuthor(
                external_id="https://openalex.org/A3",
                name="First Author",
                position=1,
                institutions=[{"display_name": "Wuyi University"}],
            )
        ],
    )
    second = SourcePaper(
        external_id="https://openalex.org/W4",
        title="Temporal Knowledge Graph Reasoning B",
        publication_date=date(2022, 1, 1),
        publication_year=2022,
        authors=[
            SourceAuthor(
                external_id="https://openalex.org/A4",
                name="Second Author",
                position=1,
                institutions=[{"id": "https://openalex.org/I98834328", "display_name": "Wuyi University"}],
            )
        ],
    )

    IngestionPipeline(session).ingest([first, second])
    session.commit()

    institution = session.scalar(select(Institution).where(Institution.name == "Wuyi University"))
    assert session.scalar(select(func.count(Institution.id))) == 1
    assert institution.external_id == "https://openalex.org/I98834328"
