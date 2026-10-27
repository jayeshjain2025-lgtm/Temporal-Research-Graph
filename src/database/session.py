from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings


def make_engine(database_url: str | None = None):
    return create_engine(database_url or get_settings().database_url, future=True)


SessionLocal = sessionmaker(bind=make_engine(), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
