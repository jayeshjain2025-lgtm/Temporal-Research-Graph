from datetime import date

from pydantic import BaseModel, Field


class SourceAuthor(BaseModel):
    external_id: str | None = None
    name: str
    position: int | None = None
    institutions: list[dict] = Field(default_factory=list)


class SourceTopic(BaseModel):
    external_id: str | None = None
    name: str
    score: float | None = None
    source: str = "openalex"
    domain_id: str | None = None
    domain_name: str | None = None
    field_id: str | None = None
    field_name: str | None = None
    subfield_id: str | None = None
    subfield_name: str | None = None


class SourcePaper(BaseModel):
    external_id: str
    title: str
    abstract: str | None = None
    publication_date: date | None = None
    publication_year: int | None = None
    venue: str | None = None
    doi: str | None = None
    source_url: str | None = None
    authors: list[SourceAuthor] = Field(default_factory=list)
    topics: list[SourceTopic] = Field(default_factory=list)
    referenced_external_ids: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
