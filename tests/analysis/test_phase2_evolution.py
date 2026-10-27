from datetime import date

from src.analysis.evolution.dataset_evolution import dataset_trends, dataset_usage
from src.analysis.evolution.method_evolution import method_adoption, method_trends
from src.analysis.evolution.relationship_evolution import first_seen_relationships, not_observed_after_year
from src.analysis.evolution.reports.evolution_report import build_evolution_report
from src.analysis.evolution.researcher_evolution import researcher_cohorts
from src.analysis.evolution.snapshots import build_snapshot, yearly_snapshots
from src.analysis.evolution.topic_evolution import topic_activity, topic_growth_rates
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schemas import SourceAuthor, SourcePaper, SourceTopic


def test_yearly_snapshot_is_cumulative(session):
    _seed_phase2_data(session)

    snapshot_2022 = build_snapshot(session, 2022)
    snapshot_2023 = build_snapshot(session, 2023)

    assert snapshot_2022.number_of_nodes() < snapshot_2023.number_of_nodes()
    assert any(data["relationship"] == "USES_METHOD" for _, _, data in snapshot_2023.edges(data=True))
    assert not any(data.get("label") == "Transformer" for _, data in snapshot_2022.nodes(data=True))


def test_topic_growth_rates(session):
    _seed_phase2_data(session)

    activity = topic_activity(session, 2021, 2023)
    rates = topic_growth_rates(session, 2021, 2023)

    assert activity["Temporal Knowledge Graph"][2021] == 1
    assert activity["Temporal Knowledge Graph"][2023] == 1
    assert rates["Temporal Knowledge Graph"][2022] == -1.0


def test_method_and_dataset_evolution(session):
    _seed_phase2_data(session)

    methods = method_adoption(session, 2021, 2023)
    datasets = dataset_usage(session, 2021, 2023)

    assert methods["Temporal Reasoning"][2021] == 1.0
    assert methods["Transformer"][2023] == 1.0
    assert method_trends(session, 2021, 2023)[0]["method"] in {"Temporal Reasoning", "Transformer"}
    assert datasets["Wikidata"][2023] == 1
    assert dataset_trends(session, 2021, 2023)[0]["dataset"] == "Wikidata"


def test_researcher_cohorts(session):
    _seed_phase2_data(session)

    cohorts = researcher_cohorts(session, 2021, 2023)

    assert cohorts[2021]["new"] == 1
    assert cohorts[2022]["leaving"] == 1
    assert cohorts[2023]["active"] == 1


def test_relationship_first_seen(session):
    _seed_phase2_data(session)

    snapshots = yearly_snapshots(session, 2021, 2023)
    first_seen = first_seen_relationships(snapshots)

    assert any(item["relationship"] == "USES_METHOD" and item["year"] == 2023 for item in first_seen)
    not_observed = not_observed_after_year(session, 2021, 2023)
    assert any(item["target_label"] == "Temporal Reasoning" for item in not_observed)


def test_unified_evolution_report(session):
    _seed_phase2_data(session)

    report = build_evolution_report(session, 2021, 2023)

    assert report["title"] == "TEMPORAL RESEARCH EVOLUTION"
    assert report["paper_growth"] == {2021: 1, 2022: 1, 2023: 1}
    assert "which_methods_became_more_common" in report["questions"]
    assert "communities" in report["graph_structure"]


def _seed_phase2_data(session):
    papers = [
        SourcePaper(
            external_id="W2021",
            title="Temporal Reasoning for Temporal Knowledge Graphs",
            abstract="Temporal reasoning with ICEWS.",
            publication_date=date(2021, 1, 1),
            publication_year=2021,
            authors=[SourceAuthor(external_id="A1", name="Ada Lovelace", position=1)],
            topics=[SourceTopic(name="Temporal Knowledge Graph", field_name="Computer Science", score=0.9)],
        ),
        SourcePaper(
            external_id="W2022",
            title="Knowledge Graph Completion",
            abstract="Link prediction for knowledge graphs.",
            publication_date=date(2022, 1, 1),
            publication_year=2022,
            authors=[SourceAuthor(external_id="A2", name="Grace Hopper", position=1)],
            topics=[SourceTopic(name="Knowledge Graph", field_name="Computer Science", score=0.9)],
        ),
        SourcePaper(
            external_id="W2023",
            title="Transformer Models for Temporal Knowledge Graph Question Answering",
            abstract="Transformer model using Wikidata.",
            publication_date=date(2023, 1, 1),
            publication_year=2023,
            authors=[SourceAuthor(external_id="A1", name="Ada Lovelace", position=1)],
            topics=[SourceTopic(name="Temporal Knowledge Graph", field_name="Computer Science", score=0.9)],
        ),
    ]
    IngestionPipeline(session).ingest(papers)
    session.commit()
