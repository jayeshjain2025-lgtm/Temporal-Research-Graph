from datetime import date

from sqlalchemy import select

from src.models import Affiliation
from src.repositories.upsert import link_affiliation, upsert_institution, upsert_researcher


def test_open_ended_affiliation(session):
    researcher = upsert_researcher(session, external_id="A1", name="Ada Lovelace")
    institution = upsert_institution(session, external_id="I1", name="Example University")
    link_affiliation(session, researcher, institution, date(2020, 1, 1), None)
    session.commit()

    affiliation = session.scalar(select(Affiliation))
    assert affiliation.valid_from == date(2020, 1, 1)
    assert affiliation.valid_to is None
