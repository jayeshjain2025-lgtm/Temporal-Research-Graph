from datetime import date

from src.analysis.temporal import disappearing_relationships, relationships_appearing_after
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schemas import SourcePaper


def test_relationship_appearance_and_disappearance(session):
    papers = [
        SourcePaper(external_id="W1", title="Rule Learning for Knowledge Graphs", abstract="Rule learning.", publication_date=date(2010, 1, 1), publication_year=2010),
        SourcePaper(external_id="W2", title="Transformer for Temporal Knowledge Graphs", abstract="Transformer model.", publication_date=date(2024, 1, 1), publication_year=2024),
    ]
    IngestionPipeline(session).ingest(papers)
    session.commit()

    appearing = relationships_appearing_after(session, 2020)
    disappearing = disappearing_relationships(session, 2024, lookback_years=3)
    assert any(item["target"] == "Transformer" for item in appearing)
    assert any(item["target"] == "Rule Learning" for item in disappearing)
