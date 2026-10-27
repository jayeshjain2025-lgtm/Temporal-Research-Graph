from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Researcher(TimestampMixin, Base):
    __tablename__ = "researchers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date, index=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, index=True)
    venue: Mapped[str | None] = mapped_column(String(500))
    doi: Mapped[str | None] = mapped_column(String(255), unique=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)


class Corpus(TimestampMixin, Base):
    __tablename__ = "corpora"
    __table_args__ = (UniqueConstraint("name", name="uq_corpora_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    query: Mapped[str | None] = mapped_column(Text)


class Topic(TimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_topics_normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(100))
    domain_name: Mapped[str | None] = mapped_column(String(255))
    field_name: Mapped[str | None] = mapped_column(String(255))
    subfield_name: Mapped[str | None] = mapped_column(String(255))
    parent_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    parent_topic: Mapped["Topic | None"] = relationship(remote_side=[id])


class Method(TimestampMixin, Base):
    __tablename__ = "methods"
    __table_args__ = (UniqueConstraint("normalized_name", "method_type", name="uq_methods_name_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    method_type: Mapped[str] = mapped_column(String(100), nullable=False, default="method")


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_datasets_normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)


class Technology(TimestampMixin, Base):
    __tablename__ = "technologies"
    __table_args__ = (UniqueConstraint("normalized_name", "technology_type", name="uq_technologies_name_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    technology_type: Mapped[str] = mapped_column(String(100), nullable=False)


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Added in migration 004.  Nullable so pre-existing rows are unaffected.
    claim_type: Mapped[str | None] = mapped_column(String(30))


Index("ix_papers_year_date", Paper.publication_year, Paper.publication_date)
