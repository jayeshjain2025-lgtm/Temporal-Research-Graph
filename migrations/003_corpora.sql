CREATE TABLE IF NOT EXISTS corpora (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    source VARCHAR(100),
    query TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_corpora_name UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS paper_corpora (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    corpus_id INTEGER NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_paper_corpus UNIQUE(paper_id, corpus_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_corpora_source_target ON paper_corpora(paper_id, corpus_id);
