from datetime import date

from src.graph.build import build_graph
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schemas import SourceAuthor, SourcePaper, SourceTopic


def test_graph_contains_typed_nodes_and_edges(session):
    paper = SourcePaper(
        external_id="W1",
        title="Graph Neural Networks for Knowledge Graphs",
        abstract="Graph neural network methods are used.",
        publication_date=date(2021, 1, 1),
        publication_year=2021,
        authors=[SourceAuthor(external_id="A1", name="Ada Lovelace")],
        topics=[SourceTopic(external_id="https://openalex.org/T2", name="Knowledge Graph", field_name="Computer Science", score=0.9)],
    )
    IngestionPipeline(session).ingest([paper])
    session.commit()

    graph = build_graph(session)
    assert any(data["type"] == "paper" for _, data in graph.nodes(data=True))
    assert any(data["relationship"] == "AUTHORED" for _, _, data in graph.edges(data=True))
    assert any(data["relationship"] == "USES_METHOD" for _, _, data in graph.edges(data=True))
