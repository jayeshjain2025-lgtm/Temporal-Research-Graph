import json
import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

from src.config.settings import Settings
from src.ingestion.schemas import SourceAuthor, SourcePaper, SourceTopic

LOGGER = logging.getLogger(__name__)


class OpenAlexSource:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = "https://api.openalex.org/works"

    def fetch(self, query: str, *, max_results: int | None = None) -> list[SourcePaper]:
        limit = max_results or self.settings.openalex_max_results
        params = {
            "search": query,
            "per-page": self.settings.openalex_per_page,
            "filter": "type:article",
            "select": ",".join(
                [
                    "id",
                    "doi",
                    "display_name",
                    "abstract_inverted_index",
                    "publication_date",
                    "publication_year",
                    "primary_location",
                    "authorships",
                    "primary_topic",
                    "topics",
                    "concepts",
                    "referenced_works",
                ]
            ),
        }
        if self.settings.openalex_mailto:
            params["mailto"] = self.settings.openalex_mailto
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key

        papers: list[SourcePaper] = []
        cursor = "*"
        while len(papers) < limit:
            params["cursor"] = cursor
            response = requests.get(self.base_url, params=params, timeout=30)
            if response.status_code == 401:
                raise RuntimeError(
                    "OpenAlex returned 401 Unauthorized. Add a valid OPENALEX_API_KEY to .env; "
                    "cursor pagination requires an API key."
                )
            response.raise_for_status()
            payload = response.json()
            self._write_raw(query, payload, len(papers))
            papers.extend(self._parse_many(payload.get("results", [])))
            cursor = payload.get("meta", {}).get("next_cursor")
            LOGGER.info("Fetched %s/%s OpenAlex records", len(papers), limit)
            if not cursor:
                break
        return papers[:limit]

    def _write_raw(self, query: str, payload: dict, offset: int) -> None:
        raw_dir = Path(self.settings.raw_data_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_query = "".join(ch if ch.isalnum() else "_" for ch in query.lower()).strip("_")[:80]
        path = raw_dir / f"openalex_{safe_query}_{offset}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _parse_many(self, records: Iterable[dict]) -> list[SourcePaper]:
        return [self._parse(record) for record in records if record.get("id") and record.get("display_name")]

    def _parse(self, record: dict) -> SourcePaper:
        publication_date = _parse_date(record.get("publication_date"))
        venue = ((record.get("primary_location") or {}).get("source") or {}).get("display_name")
        return SourcePaper(
            external_id=record["id"],
            title=record["display_name"],
            abstract=_abstract(record.get("abstract_inverted_index")),
            publication_date=publication_date,
            publication_year=record.get("publication_year"),
            venue=venue,
            doi=record.get("doi"),
            source_url=record.get("id"),
            authors=_authors(record.get("authorships") or []),
            topics=_topics(record),
            referenced_external_ids=record.get("referenced_works") or [],
            raw=record,
        )


def _abstract(inverted_index: dict | None) -> str | None:
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indices in inverted_index.items():
        positions.extend((idx, word) for idx in indices)
    return " ".join(word for _, word in sorted(positions))


def _authors(authorships: list[dict]) -> list[SourceAuthor]:
    authors: list[SourceAuthor] = []
    for index, authorship in enumerate(authorships, start=1):
        author = authorship.get("author") or {}
        if not author.get("display_name"):
            continue
        authors.append(
            SourceAuthor(
                external_id=author.get("id"),
                name=author["display_name"],
                position=index,
                institutions=authorship.get("institutions") or [],
            )
        )
    return authors


def _topics(record: dict) -> list[SourceTopic]:
    seen: set[str] = set()
    parsed: list[SourceTopic] = []

    primary_topic = record.get("primary_topic")
    if primary_topic:
        topic = _topic_from_openalex_topic(primary_topic)
        if topic and _topic_key(topic) not in seen:
            seen.add(_topic_key(topic))
            parsed.append(topic)

    for raw_topic in record.get("topics") or []:
        topic = _topic_from_openalex_topic(raw_topic)
        if topic and _topic_key(topic) not in seen:
            seen.add(_topic_key(topic))
            parsed.append(topic)

    # Fallback for older OpenAlex work payloads. These legacy concepts do not
    # include field/domain metadata, so downstream filtering is intentionally
    # stricter and uses known in-domain concept IDs/names.
    if not parsed:
        for concept in record.get("concepts") or []:
            if not concept.get("display_name"):
                continue
            topic = SourceTopic(
                external_id=concept.get("id"),
                name=concept["display_name"],
                score=concept.get("score"),
                source="openalex_concept",
            )
            if _topic_key(topic) not in seen:
                seen.add(_topic_key(topic))
                parsed.append(topic)

    return parsed


def _topic_from_openalex_topic(raw_topic: dict) -> SourceTopic | None:
    if not raw_topic.get("display_name"):
        return None
    domain = raw_topic.get("domain") or {}
    field = raw_topic.get("field") or {}
    subfield = raw_topic.get("subfield") or {}
    return SourceTopic(
        external_id=raw_topic.get("id"),
        name=raw_topic["display_name"],
        score=raw_topic.get("score"),
        source="openalex_topic",
        domain_id=domain.get("id"),
        domain_name=domain.get("display_name"),
        field_id=field.get("id"),
        field_name=field.get("display_name"),
        subfield_id=subfield.get("id"),
        subfield_name=subfield.get("display_name"),
    )


def _topic_key(topic: SourceTopic) -> str:
    return topic.external_id or topic.name.lower()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
