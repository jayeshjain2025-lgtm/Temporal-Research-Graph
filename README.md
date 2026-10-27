# Temporal Knowledge Graph for Research Intelligence

Phase 1 builds a small, correct, explainable temporal research knowledge graph for research on Knowledge Graphs, Temporal Knowledge Graphs, and Scholarly Knowledge Graphs.

PostgreSQL is the source of truth. NetworkX is an analytical projection rebuilt from database records.

## Why Temporal Modeling Matters

Research facts are not all timeless. A paper citation is an event tied to publication time. A researcher affiliation is valid over a period and may be open ended. Phase 1 keeps those meanings separate so later analysis can ask how fields, methods, datasets, and communities evolve without pretending every relationship has the same temporal semantics.

## Architecture

```mermaid
flowchart LR
    A[Research corpus: OpenAlex] --> B[Raw JSON in data/raw]
    B --> C[Pydantic validation]
    C --> D[Deterministic normalization]
    D --> E[PostgreSQL]
    E --> F[Relationship storage]
    F --> G[NetworkX graph]
    G --> H[Temporal and graph analysis]
```

## Entity Model

Implemented entities:

- `Researcher`: external ID, name, normalized name
- `Institution`: external ID, name
- `Paper`: external ID, title, abstract, publication date/year, venue, DOI, source, source URL
- `Topic`: name, normalized name, optional parent topic
- `Method`: name, normalized name, method type
- `Dataset`: name, normalized name
- `Technology`: name, normalized name, technology type
- `Claim`: text, normalized text, claim type (finding, method, comparison, limitation, dataset)

## Relationship Model

Implemented relationship tables:

- `Researcher AUTHORED Paper`
- `Researcher AFFILIATED_WITH Institution`
- `Paper CITES Paper`
- `Paper STUDIES Topic`
- `Paper USES_METHOD Method`
- `Paper USES_DATASET Dataset`
- `Paper USES_TECHNOLOGY Technology`
- `Topic SUBTOPIC_OF Topic`
- `Paper MAKES_CLAIM/SUPPORTS/CONTRADICTS Claim`
- `Claim SUPPORTS/CHALLENGES/REFINES/QUALIFIES Claim`

Relationships use foreign keys and unique constraints to support idempotent ingestion and persistence.

## Temporal Model

- Citations are event relationships. Their event date/year comes from the citing paper.
- Affiliations are valid-time relationships with `valid_from`, `valid_to`, and `observed_at`.
- Open-ended relationships use `valid_to = NULL`.
- Paper-topic/method/dataset/technology edges are observations from metadata or deterministic extraction and carry provenance.
- Claims maintain strict separation between publication time (`Paper.publication_year`), system observation time (`Provenance.observed_at`), and epistemic validity (validity intervals are never fabricated from publication dates).

## Evidence And Provenance

The `provenance` table stores:

- source type: `metadata`, `abstract`, `full_text`, `inferred`
- source identifier and URL
- evidence text/snippet when appropriate
- extraction method: `deterministic`, `manual`, `NLP`, `inferred`
- confidence
- observed time

Confidence is a heuristic field, not a calibrated scientific probability.

## Data Source

The initial implementation uses OpenAlex because it provides papers, authors, institutions, concepts, citations, publication dates, and identifiers. OpenAlex-specific code is isolated under `src/ingestion/openalex.py`; the pipeline accepts source-neutral `SourcePaper` records.

Raw responses are stored under `data/raw/`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/migrate.py
```

This setup assumes PostgreSQL is installed and running locally, with connection settings in `.env`.

## Ingestion

Ingest a bounded corpus. The `--corpus` value is a name you choose; papers ingested with the same name are grouped into that corpus. The default name is `default`:

```bash
python -m src.main ingest-openalex --max-results 150 --corpus tkg-literature
```

The default query targets Temporal Knowledge Graphs, Scholarly Knowledge Graphs, and Knowledge Graphs. Running ingestion repeatedly should not duplicate papers, researchers, topics, methods, datasets, or core relationships.

OpenAlex requires an API key for cursor pagination beyond the first page. Get a free key from [OpenAlex account settings](https://openalex.org/settings/api), add it to `.env` as `OPENALEX_API_KEY=...`, and keep the key private. The first page may succeed without a key, but fetching subsequent pages (such as when `--max-results` is greater than the page size) can return HTTP 401.

OpenAlex topic ingestion uses `primary_topic`/`topics` metadata when available, including domain, field, and subfield hierarchy. Legacy OpenAlex `concepts` are accepted only when their OpenAlex IDs or canonical names are explicitly relevant to the Phase 1 research domain. This prevents unrelated concepts such as biology, politics, surveying, archaeology, or particle-physics senses from becoming paper-topic edges.

If you ingested data before topic filtering was added, run:

```bash
python scripts/migrate.py
python scripts/clean_irrelevant_topics.py
```

## Graph Generation

The graph is built from PostgreSQL:

```python
from src.database.session import session_scope
from src.graph.build import build_graph

with session_scope() as session:
    graph = build_graph(session)
```

NetworkX nodes include papers, researchers, topics, methods, datasets, technologies, institutions, and claims where present. Edges retain relationship type and provenance/temporal metadata.

To create a visualizable graph file for the whole database or one corpus, run:

```powershell
python scripts/export_graph.py --corpus tkg-literature --output data/tkg-literature.gexf
```

The visual export defaults to papers, topics, methods, and datasets, and keeps up to 100 papers with the most connections. This leaves out the many author and affiliation nodes that can overwhelm a first view. To include all papers, pass `--max-papers 0`; to add authors or institutions, pass a larger `--node-types` list, for example `--node-types paper,topic,method,dataset,researcher,institution`.

Open the resulting `.gexf` file in [Gephi](https://gephi.org/). Try ForceAtlas 2 to arrange the graph, then run the Noverlap layout to separate crowded nodes. Hide node labels initially and enable them as you zoom in. Omit `--corpus` to export all database records. The graph builder creates a NetworkX object in memory; this script exports a simplified view for visual inspection.

### List corpora in PostgreSQL

Each ingestion run tags its papers with the name passed to `--corpus`. To list corpus names, metadata, and paper counts from your local PostgreSQL database:

```powershell
psql -h localhost -p 5432 -U postgres -d research_kg -c "SELECT c.id, c.name, c.source, c.query, COUNT(pc.paper_id) AS paper_count FROM corpora c LEFT JOIN paper_corpora pc ON pc.corpus_id = c.id GROUP BY c.id, c.name, c.source, c.query ORDER BY c.name;"
```

Use a corpus name to scope Phase 2 analysis with `--corpus` (omit the option to analyze all papers):

```bash
python -m src.main evolution --start-year 2021 --end-year 2026 --corpus tkg-literature
```

## Demo

After ingestion:

```bash
python -m src.main demo --output data/demo_report.json
```

The report includes papers per year, active researchers per year, major topics, method adoption, dataset usage, important researchers, important papers, communities, centrality, and examples of relationships appearing or disappearing over time.

The `demo` report aggregates all papers in the database. Use the Phase 2 `evolution --corpus <name>` command below for corpus-scoped analysis.

### Verify corpus imports

After ingestion, this query reports distinct papers, authors, methods, datasets, and topics assigned to each corpus. These are database totals; the ingestion command's JSON counters count processed records/links and can repeat on later runs.

```powershell
psql -h localhost -p 5432 -U postgres -d research_kg -c "SELECT c.name, (SELECT count(DISTINCT pc.paper_id) FROM paper_corpora pc WHERE pc.corpus_id=c.id) AS papers, (SELECT count(DISTINCT a.researcher_id) FROM paper_corpora pc JOIN authorships a ON a.paper_id=pc.paper_id WHERE pc.corpus_id=c.id) AS authors, (SELECT count(DISTINCT um.method_id) FROM paper_corpora pc JOIN uses_methods um ON um.paper_id=pc.paper_id WHERE pc.corpus_id=c.id) AS methods, (SELECT count(DISTINCT du.dataset_id) FROM paper_corpora pc JOIN dataset_usages du ON du.paper_id=pc.paper_id WHERE pc.corpus_id=c.id) AS datasets, (SELECT count(DISTINCT pt.topic_id) FROM paper_corpora pc JOIN paper_topics pt ON pt.paper_id=pc.paper_id WHERE pc.corpus_id=c.id) AS topics FROM corpora c ORDER BY c.name;"
```

OpenAlex work IDs are unique in the `papers` table. To check corpus overlap, inspect papers linked to multiple corpora:

```sql
SELECT p.external_id, p.title, count(DISTINCT pc.corpus_id) AS corpus_count
FROM papers p JOIN paper_corpora pc ON pc.paper_id = p.id
GROUP BY p.id, p.external_id, p.title
HAVING count(DISTINCT pc.corpus_id) > 1;
```

## Phase 2 Evolution Analysis

Run temporal research-evolution analysis over a year range:

```bash
python -m src.main evolution --start-year 2021 --end-year 2026
```

Add `--corpus <name>` to restrict this report to papers tagged with that corpus name.

Equivalent analysis module command:

```bash
python -m src.analysis evolution --start-year 2021 --end-year 2026
```

This writes structured output to:

```text
data/evolution_report.json
```

The Phase 2 report includes:

- cumulative yearly graph snapshots
- paper and researcher growth
- topic activity and growth rates
- method adoption rates
- dataset usage trends
- new relationships first observed by year
- relationships not observed after previous snapshots
- degree and betweenness centrality
- connected components
- structural community detection

Important interpretation note: a relationship being "not observed" in a later snapshot means it is absent from the bounded corpus snapshot, not that the real-world relationship stopped existing.

## Phase 3 Claim Intelligence and Temporal Reasoning

Phase 3 introduces evidence-backed research claim extraction, inter-claim relationship modeling, and temporal claim evolution queries against PostgreSQL.

```mermaid
flowchart TD
    A[Paper Abstract] --> B[Sentence Segmentation & Normalization]
    B --> C[Candidate Claim Extractor]
    C -->|Finding, Method, Comparison, Limitation| D[Canonical Claim Dedup: normalized_text]
    D --> E[PaperClaim Associations: MAKES_CLAIM, SUPPORTS, CONTRADICTS]
    D --> F[Inter-Claim Relations: SUPPORTS, CHALLENGES, REFINES, QUALIFIES]
    E --> G[(PostgreSQL)]
    F --> G
    G --> H[Temporal Reasoning & Observation Windows]
    H --> I[Claim Intelligence Report: JSON & Summary]
    H --> J[Human-in-the-Loop Evaluation: Precision & Recall]
```

### 1. Candidate Claim Extraction

- **Extractor Module**: `src/analysis/claims/extractor.py`
- **Candidate Categories**: `finding`, `proposed method`, `comparison`, `limitation`, `dataset evaluation`.
- **Epistemic Principle**: Sentences are extracted based on explicit epistemic markers (e.g., *"experiments show that"*, *"we propose"*, *"outperforms"*). It favors precision over false claim density and skips non-claim boilerplate.
- **Offsets & Provenance**: Each candidate preserves original text, normalized representation, sentence position index, and character start/end offsets.
- **Protocol Interface**: Implements `ClaimExtractorProtocol` and `DeterministicClaimExtractor`, enabling future LLM extractors to be swapped in without modifying persistence or temporal queries.

### 2. Additive Schema & Persistence

- **Migration**: `migrations/004_claim_phase3.sql` (additive only; preserves all Phase 1–2 tables and data).
  - Adds nullable `claim_type VARCHAR(30)` to `claims`.
  - Adds `UNIQUE(source_claim_id, target_claim_id, relation_type)` to `claim_relations` for idempotent upserts.
- **Persistence Repository**: `src/repositories/claims.py`
  - `upsert_claim()`: Reuses canonical claim instances by matching `normalized_text`.
  - `link_paper_claim()`: Idempotently links papers to claims (`MAKES_CLAIM`, `SUPPORTS`, `CONTRADICTS`).
  - `upsert_claim_provenance()`: Captures source paper ID, exact evidence sentence, extraction method, and heuristic confidence.
- **Transaction Pipeline**: `src/analysis/claims/pipeline.py`
  - Orchestrates extract $\rightarrow$ deduplicate $\rightarrow$ upsert $\rightarrow$ link within the caller's transaction. Gracefully skips papers without abstracts.

### 3. Claim Relationship Analysis

- **Module**: `src/analysis/claims/relations.py`
- **Supported Relationships**:
  - `SUPPORTS`: Corroboration signals (*"consistent with"*, *"confirms"*, *"corroborates"*).
  - `CHALLENGES`: Counter-evidence signals (*"contradicts"*, *"fails to"*, *"inconsistent with"*).
  - `REFINES`: Precision narrowing (*"more specifically"*, *"in particular"*, *"restricts to"*).
  - `QUALIFIES`: Conditionality / caveats (*"however"*, *"under specific conditions"*, *"unless"*).
- **Guardrails**:
  - Requires explicit lexical indicators; shared topics or different wording alone do **not** trigger relationships.
  - Rejects sentiment-only matches to prevent false contradictions.
  - Directional: earlier claim $\leftarrow$ later commentary claim.

### 4. Temporal Claim Evolution Queries

- **Module**: `src/analysis/claims/temporal.py`
- **Analytical Queries**:
  - `claim_history(session, claim_id)`: Chronological history of observations, papers, evidence, and relations for a claim.
  - `papers_reporting_claim(session, claim_id)`: Papers making or supporting a claim.
  - `papers_challenging_claim(session, claim_id)`: Papers directly contradicting or linked via inter-claim `CHALLENGES`/`QUALIFIES`.
  - `claims_timeline(session, start_year, end_year)`: Active claim counts and category breakdown by publication year.
  - `newly_observed_claims()`: Claims first observed in a given publication period.
  - `claim_observation_gaps()`: Identifies intervening gaps and discontinued observations.
- **Epistemic Invariant**: Publication time (`Paper.publication_year`), system observation time (`Provenance.observed_at`), and epistemic validity are strictly separated. Absence from a year's snapshot is never interpreted as proof of real-world invalidity.

### 5. Research Intelligence Report CLI

Run the claim intelligence report for a year range and optional corpus:

```bash
python -m src.main claims --start-year 2020 --end-year 2026 --corpus tkg-literature --output data/claim_report.json
```

Output options:
- Human-readable summary output in terminal (default)
- `--json-only`: Machine-readable JSON output to stdout
- `--output <path>`: Writes complete structured report to disk (default: `data/claim_report.json`)

### 6. Human Evaluation Workflow

- **Evaluation Module**: `src/analysis/claims/evaluation.py`
- **CLI Script**: `scripts/evaluate_claims.py`
- **Strict Metric Rule**: Precision and recall are calculated **only** when a human-annotated sample is provided.

Workflow:
1. Export a candidate sample from database papers:
   ```bash
   python -m scripts.evaluate_claims --export data/claim_annotations_sample.csv --limit 30
   ```
2. Annotate `is_true_claim` (1 or 0) and `true_type` in the generated CSV.
3. Evaluate metrics:
   ```bash
   python -m scripts.evaluate_claims --input data/claim_annotations_sample.csv --output data/claim_eval_metrics.json
   ```

## Analytical Queries

Implemented analyses include:

- paper activity per year
- active researchers per year
- method adoption rate per year
- dataset usage over time
- topic growth over time
- new and disappearing relationships
- degree centrality
- betweenness centrality
- connected components
- greedy modularity communities
- researcher collaboration graph
- topic-method graph
- claim emergence, adoption, and observation gaps
- claim support vs contradiction history

Disappearing relationships mean "not observed recently in this bounded corpus"; they do not mean the relationship became false.

## Tests

Run the full automated test suite (over 100 tests covering unit models, normalization, Phase 2 evolution, Phase 3 extraction, persistence, relations, temporal queries, reports, and evaluation):

```bash
pytest -v --ignore=tests/integration -q
```

Run specific Phase 3 test modules:

```bash
pytest tests/unit/test_claim_extractor_phase3.py -v
pytest tests/unit/test_claim_persistence.py -v
pytest tests/unit/test_claim_relations.py -v
pytest tests/unit/test_claim_temporal.py -v
pytest tests/unit/test_claim_report.py -v
pytest tests/unit/test_claim_evaluation.py -v
```

PostgreSQL migration integration test:

```bash
set TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/research_kg
pytest -m integration
```

## Current Limitations

- Method, dataset, and technology extraction uses small deterministic vocabularies.
- OpenAlex topics are filtered using available hierarchy metadata; no curated project ontology is provided yet.
- Referenced works become citation edges only when both papers are in the local corpus.
- Claim extraction and claim relationship detection currently utilize deterministic, evidence-grounded rules. An LLM-assisted extractor conforming to `ClaimExtractorProtocol` can be plugged in for higher recall.
- Absence of a claim or relationship indicates lack of observation within the bounded ingested corpus, not proof of non-existence or scientific falsification.
- No vector database, Neo4j, or large-scale multi-node infrastructure are used.

## Future Phases

Likely future work includes:
- LLM-assisted claim extraction implementing `ClaimExtractorProtocol` with few-shot schema validation.
- Cross-paper semantic coreference resolution for claims with varying sentence surface structures.
- Interactive web visualizer / dashboard for temporal claim exploration and contradiction graph traversal.
- Automated hypothesis generation from qualified or challenged claim clusters.
