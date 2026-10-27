from datetime import date
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    Affiliation,
    Authorship,
    Citation,
    Corpus,
    Dataset,
    DatasetUsage,
    Institution,
    Method,
    Paper,
    PaperCorpus,
    PaperTopic,
    Provenance,
    Researcher,
    Technology,
    TechnologyUsage,
    Topic,
    UsesMethod,
)
from src.normalization.text import normalize_text

T = TypeVar("T")


def get_or_create(session: Session, model: type[T], lookup: dict[str, Any], defaults: dict[str, Any] | None = None) -> tuple[T, bool]:
    instance = session.scalar(select(model).filter_by(**lookup))
    if instance:
        return instance, False
    values = {**(defaults or {}), **lookup}
    instance = model(**values)
    session.add(instance)
    session.flush()
    return instance, True


def provenance(session: Session, *, source_identifier: str, source_url: str | None, source_type: str = "metadata", evidence_text: str | None = None, extraction_method: str = "deterministic", confidence: float | None = 1.0) -> Provenance:
    item = Provenance(
        source_type=source_type,
        source_identifier=source_identifier,
        source_url=source_url,
        evidence_text=evidence_text,
        extraction_method=extraction_method,
        confidence=confidence,
    )
    session.add(item)
    session.flush()
    return item


def upsert_paper(session: Session, *, external_id: str, title: str, abstract: str | None, publication_date: date | None, publication_year: int | None, venue: str | None, doi: str | None, source_url: str | None) -> Paper:
    paper, created = get_or_create(
        session,
        Paper,
        {"external_id": external_id},
        {
            "title": title,
            "abstract": abstract,
            "publication_date": publication_date,
            "publication_year": publication_year,
            "venue": venue,
            "doi": doi,
            "source": "openalex",
            "source_url": source_url,
        },
    )
    if not created:
        paper.title = title or paper.title
        paper.abstract = abstract or paper.abstract
        paper.publication_date = publication_date or paper.publication_date
        paper.publication_year = publication_year or paper.publication_year
        paper.venue = venue or paper.venue
        paper.doi = doi or paper.doi
        paper.source_url = source_url or paper.source_url
    return paper


def upsert_corpus(session: Session, *, name: str, source: str | None = None, query: str | None = None, description: str | None = None) -> Corpus:
    corpus, created = get_or_create(
        session,
        Corpus,
        {"name": name},
        {"source": source, "query": query, "description": description},
    )
    if not created:
        corpus.source = source or corpus.source
        corpus.query = query or corpus.query
        corpus.description = description or corpus.description
    return corpus


def link_paper_corpus(session: Session, paper: Paper, corpus: Corpus, provenance_id: int | None) -> None:
    get_or_create(session, PaperCorpus, {"paper_id": paper.id, "corpus_id": corpus.id}, {"provenance_id": provenance_id})


def upsert_researcher(session: Session, *, external_id: str | None, name: str) -> Researcher:
    lookup = {"external_id": external_id} if external_id else {"normalized_name": normalize_text(name)}
    researcher, _ = get_or_create(session, Researcher, lookup, {"name": name, "normalized_name": normalize_text(name)})
    return researcher


def upsert_institution(session: Session, *, external_id: str | None, name: str) -> Institution:
    institution = None
    if external_id:
        institution = session.scalar(select(Institution).where(Institution.external_id == external_id))
    if institution is None:
        institution = session.scalar(select(Institution).where(Institution.name == name))
    if institution is None:
        institution = Institution(external_id=external_id, name=name)
        session.add(institution)
        session.flush()
    else:
        institution.external_id = external_id or institution.external_id
        institution.name = name or institution.name
    return institution


def upsert_topic(
    session: Session,
    *,
    name: str,
    external_id: str | None = None,
    source: str | None = None,
    domain_name: str | None = None,
    field_name: str | None = None,
    subfield_name: str | None = None,
) -> Topic:
    normalized_name = normalize_text(name)
    topic = None
    if external_id:
        topic = session.scalar(select(Topic).where(Topic.external_id == external_id))
    if topic is None:
        topic = session.scalar(select(Topic).where(Topic.normalized_name == normalized_name))
    if topic is None:
        topic = Topic(name=name, normalized_name=normalized_name)
        session.add(topic)
        session.flush()

    topic.external_id = external_id or topic.external_id
    topic.name = name or topic.name
    topic.normalized_name = normalized_name or topic.normalized_name
    topic.source = source or topic.source
    topic.domain_name = domain_name or topic.domain_name
    topic.field_name = field_name or topic.field_name
    topic.subfield_name = subfield_name or topic.subfield_name
    return topic


def upsert_method(session: Session, *, name: str, method_type: str) -> Method:
    method, _ = get_or_create(session, Method, {"normalized_name": normalize_text(name), "method_type": method_type}, {"name": name})
    return method


def upsert_dataset(session: Session, name: str) -> Dataset:
    dataset, _ = get_or_create(session, Dataset, {"normalized_name": normalize_text(name)}, {"name": name})
    return dataset


def upsert_technology(session: Session, *, name: str, technology_type: str) -> Technology:
    technology, _ = get_or_create(session, Technology, {"normalized_name": normalize_text(name), "technology_type": technology_type}, {"name": name})
    return technology


def link_authorship(session: Session, researcher: Researcher, paper: Paper, author_position: int | None, provenance_id: int | None) -> None:
    get_or_create(session, Authorship, {"researcher_id": researcher.id, "paper_id": paper.id}, {"author_position": author_position, "provenance_id": provenance_id})


def link_affiliation(session: Session, researcher: Researcher, institution: Institution, valid_from: date | None, provenance_id: int | None) -> None:
    get_or_create(session, Affiliation, {"researcher_id": researcher.id, "institution_id": institution.id, "valid_from": valid_from}, {"valid_to": None, "provenance_id": provenance_id})


def link_paper_topic(session: Session, paper: Paper, topic: Topic, provenance_id: int | None) -> None:
    get_or_create(session, PaperTopic, {"paper_id": paper.id, "topic_id": topic.id}, {"provenance_id": provenance_id})


def link_method(session: Session, paper: Paper, method: Method, provenance_id: int | None) -> None:
    get_or_create(session, UsesMethod, {"paper_id": paper.id, "method_id": method.id}, {"provenance_id": provenance_id})


def link_dataset(session: Session, paper: Paper, dataset: Dataset, provenance_id: int | None) -> None:
    get_or_create(session, DatasetUsage, {"paper_id": paper.id, "dataset_id": dataset.id}, {"provenance_id": provenance_id})


def link_technology(session: Session, paper: Paper, technology: Technology, provenance_id: int | None) -> None:
    get_or_create(session, TechnologyUsage, {"paper_id": paper.id, "technology_id": technology.id}, {"provenance_id": provenance_id})


def link_citation(session: Session, citing: Paper, cited: Paper, provenance_id: int | None) -> None:
    get_or_create(session, Citation, {"citing_paper_id": citing.id, "cited_paper_id": cited.id}, {"event_date": citing.publication_date, "event_year": citing.publication_year, "provenance_id": provenance_id})
