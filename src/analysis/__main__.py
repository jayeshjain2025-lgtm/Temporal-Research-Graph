import argparse
import json
from pathlib import Path

from src.analysis.evolution.reports.evolution_report import build_evolution_report, format_evolution_summary
from src.database.session import session_scope


def main() -> None:
    parser = argparse.ArgumentParser(description="Research KG analysis commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evolution = subparsers.add_parser("evolution")
    evolution.add_argument("--start-year", type=int, required=True)
    evolution.add_argument("--end-year", type=int, required=True)
    evolution.add_argument("--output", default="data/evolution_report.json")
    evolution.add_argument("--json-only", action="store_true")

    args = parser.parse_args()
    if args.command == "evolution":
        if args.end_year < args.start_year:
            raise SystemExit("--end-year must be greater than or equal to --start-year")
        with session_scope() as session:
            report = build_evolution_report(session, args.start_year, args.end_year)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        if args.json_only:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_evolution_summary(report))
            print(f"\nStructured JSON written to {output}")


if __name__ == "__main__":
    main()
