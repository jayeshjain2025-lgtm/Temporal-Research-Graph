from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Corpus, PaperCorpus


def corpus_paper_ids(session: Session, corpus_name: str | None) -> set[int] | None:
    if not corpus_name:
        return None
    corpus = session.scalar(select(Corpus).where(Corpus.name == corpus_name))
    if not corpus:
        return set()
    return set(session.scalars(select(PaperCorpus.paper_id).where(PaperCorpus.corpus_id == corpus.id)).all())


def apply_paper_filter(statement, paper_ids: set[int] | None, paper_model):
    if paper_ids is None:
        return statement
    if not paper_ids:
        return statement.where(False)
    return statement.where(paper_model.id.in_(paper_ids))
