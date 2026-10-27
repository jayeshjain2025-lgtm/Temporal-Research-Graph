from datetime import date

from src.analysis.temporal import active_researchers_per_year, method_adoption_rate, papers_per_year
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schemas import SourceAuthor, SourcePaper, SourceTopic


def test_yearly_aggregation_and_adoption_rate(session):
    papers = [
        SourcePaper(
            external_id="W1",
            title="Knowledge Graph Embedding for Temporal Knowledge Graphs",
            abstract="Knowledge graph embedding is evaluated.",
            publication_date=date(2020, 1, 1),
            publication_year=2020,
            authors=[SourceAuthor(external_id="A1", name="Ada Lovelace")],
            topics=[SourceTopic(external_id="https://openalex.org/T2", name="Knowledge Graph", field_name="Computer Science", score=0.9)],
        ),
        SourcePaper(
            external_id="W2",
            title="Survey of Temporal Knowledge Graphs",
            abstract="A survey.",
            publication_date=date(2020, 2, 1),
            publication_year=2020,
            authors=[SourceAuthor(external_id="A2", name="Grace Hopper")],
            topics=[SourceTopic(external_id="https://openalex.org/T2", name="Knowledge Graph", field_name="Computer Science", score=0.9)],
        ),
    ]
    IngestionPipeline(session).ingest(papers)
    session.commit()

    assert papers_per_year(session) == {2020: 2}
    assert active_researchers_per_year(session) == {2020: 2}
    assert method_adoption_rate(session)["Knowledge Graph Embedding"][2020] == 0.5
