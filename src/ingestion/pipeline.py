import logging
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.claims.pipeline import extract_and_persist_claims
from src.ingestion.extractors import extract_datasets, extract_methods, extract_technologies
from src.ingestion.schemas import SourcePaper
from src.ingestion.topic_filter import canonical_topic_name, relevant_topic
from src.models import Paper
from src.repositories.upsert import (
    link_affiliation,
    link_authorship,
    link_citation,
    link_dataset,
    link_method,
    link_paper_corpus,
    link_paper_topic,
    link_technology,
    provenance,
    upsert_corpus,
    upsert_dataset,
    upsert_institution,
    upsert_method,
    upsert_paper,
    upsert_researcher,
    upsert_technology,
    upsert_topic,
)

LOGGER = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, session: Session, corpus_name: str = "default", corpus_query: str | None = None) -> None:
        self.session = session
        self.corpus = upsert_corpus(session, name=corpus_name, source="openalex", query=corpus_query)

    def ingest(self, papers: Iterable[SourcePaper]) -> dict[str, int]:
        records = list(papers)
        counts = {"papers": 0, "authorships": 0, "topics": 0, "methods": 0, "datasets": 0, "technologies": 0, "citations": 0, "claims": 0}
        for source_paper in records:
            paper = self._ingest_paper(source_paper, counts)
            LOGGER.info("Ingested %s", paper.external_id)

        by_external_id = {paper.external_id: paper for paper in self.session.scalars(select(Paper)).all()}
        for source_paper in records:
            citing = by_external_id.get(source_paper.external_id)
            if not citing:
                continue
            prov = provenance(self.session, source_identifier=source_paper.external_id, source_url=source_paper.source_url)
            for cited_external_id in source_paper.referenced_external_ids:
                cited = by_external_id.get(cited_external_id)
                if cited:
                    link_citation(self.session, citing, cited, prov.id)
                    counts["citations"] += 1
        return counts

    def _ingest_paper(self, source_paper: SourcePaper, counts: dict[str, int]) -> Paper:
        paper = upsert_paper(
            self.session,
            external_id=source_paper.external_id,
            title=source_paper.title,
            abstract=source_paper.abstract,
            publication_date=source_paper.publication_date,
            publication_year=source_paper.publication_year,
            venue=source_paper.venue,
            doi=source_paper.doi,
            source_url=source_paper.source_url,
        )
        counts["papers"] += 1
        prov = provenance(self.session, source_identifier=source_paper.external_id, source_url=source_paper.source_url)
        link_paper_corpus(self.session, paper, self.corpus, prov.id)

        for author in source_paper.authors:
            researcher = upsert_researcher(self.session, external_id=author.external_id, name=author.name)
            link_authorship(self.session, researcher, paper, author.position, prov.id)
            counts["authorships"] += 1
            for institution_data in author.institutions:
                name = institution_data.get("display_name") or institution_data.get("name")
                if not name:
                    continue
                institution = upsert_institution(self.session, external_id=institution_data.get("id"), name=name)
                link_affiliation(self.session, researcher, institution, source_paper.publication_date, prov.id)

        for source_topic in source_paper.topics:
            if not relevant_topic(source_topic):
                LOGGER.debug("Rejected OpenAlex topic %s for %s", source_topic.name, source_paper.external_id)
                continue
            topic_prov = provenance(
                self.session,
                source_identifier=source_topic.external_id or source_paper.external_id,
                source_url=source_paper.source_url,
                evidence_text=f"OpenAlex topic score={source_topic.score}, field={source_topic.field_name}, subfield={source_topic.subfield_name}, domain={source_topic.domain_name}",
                confidence=source_topic.score,
            )
            topic = upsert_topic(
                self.session,
                name=canonical_topic_name(source_topic),
                external_id=source_topic.external_id,
                source=source_topic.source,
                domain_name=source_topic.domain_name,
                field_name=source_topic.field_name,
                subfield_name=source_topic.subfield_name,
            )
            link_paper_topic(self.session, paper, topic, topic_prov.id)
            counts["topics"] += 1

        for extracted in extract_methods(source_paper.title, source_paper.abstract):
            item_prov = provenance(self.session, source_identifier=source_paper.external_id, source_url=source_paper.source_url, source_type="abstract", evidence_text=extracted.evidence, confidence=0.65)
            method = upsert_method(self.session, name=extracted.name, method_type=extracted.concept_type)
            link_method(self.session, paper, method, item_prov.id)
            counts["methods"] += 1

        for extracted in extract_datasets(source_paper.title, source_paper.abstract):
            item_prov = provenance(self.session, source_identifier=source_paper.external_id, source_url=source_paper.source_url, source_type="abstract", evidence_text=extracted.evidence, confidence=0.65)
            dataset = upsert_dataset(self.session, extracted.name)
            link_dataset(self.session, paper, dataset, item_prov.id)
            counts["datasets"] += 1

        for extracted in extract_technologies(source_paper.title, source_paper.abstract):
            item_prov = provenance(self.session, source_identifier=source_paper.external_id, source_url=source_paper.source_url, source_type="abstract", evidence_text=extracted.evidence, confidence=0.65)
            technology = upsert_technology(self.session, name=extracted.name, technology_type=extracted.concept_type)
            link_technology(self.session, paper, technology, item_prov.id)
            counts["technologies"] += 1

        claim_res = extract_and_persist_claims(self.session, paper)
        if "claims" in counts:
            counts["claims"] += claim_res.claims_created

        return paper
