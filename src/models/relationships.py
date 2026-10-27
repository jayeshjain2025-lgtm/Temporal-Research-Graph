from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Provenance(Base):
    __tablename__ = "provenance"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("source_type in ('metadata','abstract','full_text','inferred')", name="ck_provenance_source_type"),
        CheckConstraint("extraction_method in ('deterministic','manual','NLP','inferred')", name="ck_provenance_extraction_method"),
        CheckConstraint("confidence is null or (confidence >= 0 and confidence <= 1)", name="ck_provenance_confidence"),
    )


class Authorship(Base):
    __tablename__ = "authorships"
    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id", ondelete="CASCADE"), nullable=False)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    author_position: Mapped[int | None]
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("researcher_id", "paper_id", name="uq_authorship"),)


class Affiliation(Base):
    __tablename__ = "affiliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id", ondelete="CASCADE"), nullable=False)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("researcher_id", "institution_id", "valid_from", name="uq_affiliation_period"),)


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[int] = mapped_column(primary_key=True)
    citing_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    cited_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    event_year: Mapped[int | None] = mapped_column(index=True)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("citing_paper_id", "cited_paper_id", name="uq_citation"),)


class PaperCorpus(Base):
    __tablename__ = "paper_corpora"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    corpus_id: Mapped[int] = mapped_column(ForeignKey("corpora.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("paper_id", "corpus_id", name="uq_paper_corpus"),)


class PaperTopic(Base):
    __tablename__ = "paper_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("paper_id", "topic_id", name="uq_paper_topic"),)


class UsesMethod(Base):
    __tablename__ = "uses_methods"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    method_id: Mapped[int] = mapped_column(ForeignKey("methods.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("paper_id", "method_id", name="uq_paper_method"),)


class DatasetUsage(Base):
    __tablename__ = "dataset_usages"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("paper_id", "dataset_id", name="uq_paper_dataset"),)


class TechnologyUsage(Base):
    __tablename__ = "technology_usages"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    technology_id: Mapped[int] = mapped_column(ForeignKey("technologies.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("paper_id", "technology_id", name="uq_paper_technology"),)


class TopicHierarchy(Base):
    __tablename__ = "topic_hierarchy"
    id: Mapped[int] = mapped_column(primary_key=True)
    child_topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    parent_topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("child_topic_id", "parent_topic_id", name="uq_topic_hierarchy"),)


class PaperClaim(Base):
    __tablename__ = "paper_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (
        UniqueConstraint("paper_id", "claim_id", "relation_type", name="uq_paper_claim_relation"),
        CheckConstraint("relation_type in ('MAKES_CLAIM','SUPPORTS','CONTRADICTS')", name="ck_paper_claim_relation"),
    )


class ClaimRelation(Base):
    __tablename__ = "claim_relations"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    target_claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provenance_id: Mapped[int | None] = mapped_column(ForeignKey("provenance.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("source_claim_id", "target_claim_id", "relation_type", name="uq_claim_relation"),)


Index("ix_authorship_source_target", Authorship.researcher_id, Authorship.paper_id)
Index("ix_affiliation_source_target", Affiliation.researcher_id, Affiliation.institution_id)
Index("ix_citation_source_target", Citation.citing_paper_id, Citation.cited_paper_id)
Index("ix_paper_corpora_source_target", PaperCorpus.paper_id, PaperCorpus.corpus_id)
Index("ix_paper_topics_source_target", PaperTopic.paper_id, PaperTopic.topic_id)
Index("ix_uses_methods_source_target", UsesMethod.paper_id, UsesMethod.method_id)
Index("ix_dataset_usages_source_target", DatasetUsage.paper_id, DatasetUsage.dataset_id)
