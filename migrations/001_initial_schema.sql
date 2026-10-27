CREATE TABLE IF NOT EXISTS researchers (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_researchers_normalized_name ON researchers(normalized_name);

CREATE TABLE IF NOT EXISTS institutions (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(500) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS papers (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    abstract TEXT,
    publication_date DATE,
    publication_year INTEGER,
    venue VARCHAR(500),
    doi VARCHAR(255) UNIQUE,
    source VARCHAR(100) NOT NULL,
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_papers_publication_date ON papers(publication_date);
CREATE INDEX IF NOT EXISTS ix_papers_publication_year ON papers(publication_year);
CREATE INDEX IF NOT EXISTS ix_papers_year_date ON papers(publication_year, publication_date);

CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL UNIQUE,
    source VARCHAR(100),
    domain_name VARCHAR(255),
    field_name VARCHAR(255),
    subfield_name VARCHAR(255),
    parent_topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_topics_normalized_name ON topics(normalized_name);

CREATE TABLE IF NOT EXISTS methods (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    method_type VARCHAR(100) NOT NULL DEFAULT 'method',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_methods_name_type UNIQUE(normalized_name, method_type)
);
CREATE INDEX IF NOT EXISTS ix_methods_normalized_name ON methods(normalized_name);

CREATE TABLE IF NOT EXISTS datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_datasets_normalized_name ON datasets(normalized_name);

CREATE TABLE IF NOT EXISTS technologies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    technology_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_technologies_name_type UNIQUE(normalized_name, technology_type)
);
CREATE INDEX IF NOT EXISTS ix_technologies_normalized_name ON technologies(normalized_name);

CREATE TABLE IF NOT EXISTS claims (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provenance (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL CHECK (source_type in ('metadata','abstract','full_text','inferred')),
    source_identifier VARCHAR(255),
    source_url TEXT,
    evidence_text TEXT,
    extraction_method VARCHAR(50) NOT NULL CHECK (extraction_method in ('deterministic','manual','NLP','inferred')),
    confidence DOUBLE PRECISION CHECK (confidence is null or (confidence >= 0 and confidence <= 1)),
    observed_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS authorships (
    id SERIAL PRIMARY KEY,
    researcher_id INTEGER NOT NULL REFERENCES researchers(id) ON DELETE CASCADE,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_position INTEGER,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_authorship UNIQUE(researcher_id, paper_id)
);
CREATE INDEX IF NOT EXISTS ix_authorship_source_target ON authorships(researcher_id, paper_id);

CREATE TABLE IF NOT EXISTS affiliations (
    id SERIAL PRIMARY KEY,
    researcher_id INTEGER NOT NULL REFERENCES researchers(id) ON DELETE CASCADE,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
    valid_from DATE,
    valid_to DATE,
    observed_at TIMESTAMPTZ DEFAULT now(),
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_affiliation_period UNIQUE(researcher_id, institution_id, valid_from)
);
CREATE INDEX IF NOT EXISTS ix_affiliations_valid_from ON affiliations(valid_from);
CREATE INDEX IF NOT EXISTS ix_affiliations_valid_to ON affiliations(valid_to);
CREATE INDEX IF NOT EXISTS ix_affiliation_source_target ON affiliations(researcher_id, institution_id);

CREATE TABLE IF NOT EXISTS citations (
    id SERIAL PRIMARY KEY,
    citing_paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    cited_paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    event_date DATE,
    event_year INTEGER,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_citation UNIQUE(citing_paper_id, cited_paper_id)
);
CREATE INDEX IF NOT EXISTS ix_citations_event_date ON citations(event_date);
CREATE INDEX IF NOT EXISTS ix_citations_event_year ON citations(event_year);
CREATE INDEX IF NOT EXISTS ix_citation_source_target ON citations(citing_paper_id, cited_paper_id);

CREATE TABLE IF NOT EXISTS paper_topics (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_paper_topic UNIQUE(paper_id, topic_id)
);
CREATE INDEX IF NOT EXISTS ix_paper_topics_source_target ON paper_topics(paper_id, topic_id);

CREATE TABLE IF NOT EXISTS uses_methods (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_paper_method UNIQUE(paper_id, method_id)
);
CREATE INDEX IF NOT EXISTS ix_uses_methods_source_target ON uses_methods(paper_id, method_id);

CREATE TABLE IF NOT EXISTS dataset_usages (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_paper_dataset UNIQUE(paper_id, dataset_id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_usages_source_target ON dataset_usages(paper_id, dataset_id);

CREATE TABLE IF NOT EXISTS technology_usages (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    technology_id INTEGER NOT NULL REFERENCES technologies(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_paper_technology UNIQUE(paper_id, technology_id)
);

CREATE TABLE IF NOT EXISTS topic_hierarchy (
    id SERIAL PRIMARY KEY,
    child_topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    parent_topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_topic_hierarchy UNIQUE(child_topic_id, parent_topic_id)
);

CREATE TABLE IF NOT EXISTS paper_claims (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relation_type VARCHAR(30) NOT NULL CHECK (relation_type in ('MAKES_CLAIM','SUPPORTS','CONTRADICTS')),
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL,
    CONSTRAINT uq_paper_claim_relation UNIQUE(paper_id, claim_id, relation_type)
);

CREATE TABLE IF NOT EXISTS claim_relations (
    id SERIAL PRIMARY KEY,
    source_claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    target_claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relation_type VARCHAR(30) NOT NULL,
    provenance_id INTEGER REFERENCES provenance(id) ON DELETE SET NULL
);
