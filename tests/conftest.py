import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.base import Base
from src.models import *  # noqa: F403


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as session:
        yield session
