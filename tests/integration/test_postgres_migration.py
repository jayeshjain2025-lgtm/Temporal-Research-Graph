import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.integration
def test_initial_migration_runs_against_postgres():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    engine = create_engine(database_url, future=True)
    migration = Path("migrations/001_initial_schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(migration))
        assert conn.execute(text("SELECT to_regclass('public.papers')")).scalar() == "papers"
