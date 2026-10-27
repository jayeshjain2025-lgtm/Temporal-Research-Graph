from pathlib import Path
import sys

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.session import make_engine


def main() -> None:
    migrations_dir = PROJECT_ROOT / "migrations"
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"))
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
        for migration in sorted(migrations_dir.glob("*.sql")):
            if migration.name in applied:
                continue
            conn.exec_driver_sql(migration.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:version)"), {"version": migration.name})
            print(f"applied {migration.name}")


if __name__ == "__main__":
    main()
