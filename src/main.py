import argparse
import json
import logging
from pathlib import Path

from src.analysis.claims.pipeline import run_corpus_relation_pass
from src.analysis.claims.reports.claim_report import build_claim_report, format_claim_summary
from src.analysis.demo import research_evolution_report
from src.analysis.evolution.corpus_filter import corpus_paper_ids
from src.analysis.evolution.reports.evolution_report import build_evolution_report, format_evolution_summary
from src.config.settings import get_settings
from src.database.session import session_scope
from src.ingestion.openalex import OpenAlexSource
from src.ingestion.pipeline import IngestionPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal research knowledge graph CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest-openalex")
    ingest_parser.add_argument("--query", default='"temporal knowledge graph" OR "scholarly knowledge graph" OR "knowledge graph"')
    ingest_parser.add_argument("--max-results", type=int, default=None)
    ingest_parser.add_argument("--corpus", default="default", help="Named corpus to tag ingested papers into (default: 'default')")

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("--output", default="data/demo_report.json")

    evolution_parser = subparsers.add_parser("evolution")
    evolution_parser.add_argument("--start-year", type=int, required=True)
    evolution_parser.add_argument("--end-year", type=int, required=True)
    evolution_parser.add_argument("--output", default="data/evolution_report.json")
    evolution_parser.add_argument("--json-only", action="store_true")
    evolution_parser.add_argument("--corpus", default=None, help="Restrict analysis to a named corpus (default: all papers)")

    claims_parser = subparsers.add_parser("claims", help="Claim intelligence and temporal reasoning report")
    claims_parser.add_argument("--start-year", type=int, required=True)
    claims_parser.add_argument("--end-year", type=int, required=True)
    claims_parser.add_argument("--output", default="data/claim_report.json")
    claims_parser.add_argument("--json-only", action="store_true")
    claims_parser.add_argument("--corpus", default=None, help="Restrict analysis to a named corpus (default: all papers)")

    relate_parser = subparsers.add_parser(
        "relate-claims",
        help=(
            "Detect and persist cross-paper claim relations for a corpus. "
            "Run this after 'ingest-openalex' to populate claim-claim relationships."
        ),
    )
    relate_parser.add_argument(
        "--corpus",
        default=None,
        help="Restrict relation detection to a named corpus (default: all papers)",
    )

    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    if args.command == "ingest-openalex":
        papers = OpenAlexSource(settings).fetch(args.query, max_results=args.max_results)
        with session_scope() as session:
            counts = IngestionPipeline(session, corpus_name=args.corpus, corpus_query=args.query).ingest(papers)
        print(json.dumps(counts, indent=2, default=str))
    elif args.command == "demo":
        with session_scope() as session:
            report = research_evolution_report(session)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, default=str))
    elif args.command == "evolution":
        if args.end_year < args.start_year:
            raise SystemExit("--end-year must be greater than or equal to --start-year")
        with session_scope() as session:
            report = build_evolution_report(session, args.start_year, args.end_year, corpus_name=args.corpus)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        if args.json_only:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_evolution_summary(report))
            print(f"\nStructured JSON written to {output}")
    elif args.command == "claims":
        if args.end_year < args.start_year:
            raise SystemExit("--end-year must be greater than or equal to --start-year")
        with session_scope() as session:
            report = build_claim_report(session, args.start_year, args.end_year, corpus_name=args.corpus)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        if args.json_only:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_claim_summary(report))
            print(f"\nStructured JSON written to {output}")
    elif args.command == "relate-claims":
        with session_scope() as session:
            pids = corpus_paper_ids(session, args.corpus)
            counts = run_corpus_relation_pass(session, paper_ids=pids)
        corpus_label = args.corpus or "all"
        print(f"Corpus: {corpus_label}")
        print(json.dumps(counts, indent=2, default=str))


if __name__ == "__main__":
    main()
