from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/research_kg"
    openalex_mailto: str | None = None
    openalex_api_key: str | None = None
    openalex_per_page: int = Field(default=50, ge=1, le=200)
    openalex_max_results: int = Field(default=150, ge=1, le=500)
    raw_data_dir: Path = Path("data/raw")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
