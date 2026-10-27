"""Human annotation and evaluation workflow for research claims — Phase 3, Milestone 3.6.

Usage
-----
1. Export a candidate sample for human annotation:
       python -m scripts.evaluate_claims --export data/claim_annotations_sample.csv --limit 25
   Or export candidate relationships:
       python -m scripts.evaluate_claims --export-relations data/relation_annotations_sample.csv --limit 50

2. Open CSV in Excel/editor and fill in human annotations:
       Claims: is_true_claim (1 for true claim, 0 for false positive), true_type (finding, method, ...)
       Relations: true_relation (SUPPORTS, CHALLENGES, REFINES, QUALIFIES, or NO_RELATION)

3. Run evaluation to compute Precision, Recall, and F1:
       python -m scripts.evaluate_claims --input data/claim_annotations_sample.csv --output data/claim_eval_metrics.json
       python -m scripts.evaluate_claims --input data/relation_annotations_sample.csv --output data/relation_eval_metrics.json
"""
import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from src.analysis.claims.evaluation import (
    evaluate_claim_extraction,
    evaluate_claim_relations,
    export_annotation_sample_csv,
    export_relation_annotation_sample_csv,
    load_annotations_csv,
)
from src.database.session import session_scope


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate claim extraction and relations against human ground truth")
    parser.add_argument(
        "--export",
        metavar="CSV_PATH",
        default=None,
        help="Export candidate claims to a CSV template for human annotation",
    )
    parser.add_argument(
        "--export-relations",
        metavar="CSV_PATH",
        default=None,
        help="Export candidate claim relations to a CSV template for human annotation",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Number of items/papers to sample for export template (default: 25)",
    )
    parser.add_argument(
        "--input",
        metavar="CSV_PATH",
        default="data/claim_annotations_sample.csv",
        help="Path to human-annotated CSV file (default: data/claim_annotations_sample.csv)",
    )
    parser.add_argument(
        "--output",
        metavar="JSON_PATH",
        default=None,
        help="Optional path to write evaluation results as JSON",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.export:
        print(f"Exporting claim annotation template to {args.export} (sampling up to {args.limit} papers)...")
        with session_scope() as session:
            count = export_annotation_sample_csv(session, args.export, limit_papers=args.limit)
        print(f"Exported {count} candidate claims to {args.export}.")
        print("Please annotate 'is_true_claim' (1/0) and 'true_type' before running evaluation.")
        return

    if args.export_relations:
        print(f"Exporting relation annotation template to {args.export_relations} (sampling up to {args.limit} relations)...")
        with session_scope() as session:
            count = export_relation_annotation_sample_csv(session, args.export_relations, limit=args.limit)
        print(f"Exported {count} candidate relations to {args.export_relations}.")
        print("Please annotate 'true_relation' (SUPPORTS, CHALLENGES, REFINES, QUALIFIES, NO_RELATION) before running evaluation.")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Note: Annotation file {input_path} does not exist yet.")
        print("To generate an annotation template from your database papers, run:")
        print(f"    python -m scripts.evaluate_claims --export {args.input} --limit 25")
        sys.exit(0)

    # Detect if CSV is for relations or claims by inspecting header
    with input_path.open("r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []

    is_relation_file = "predicted_relation" in fields or "true_relation" in fields

    if is_relation_file:
        with input_path.open("r", encoding="utf-8-sig") as fh:
            records = list(csv.DictReader(fh))
        annotated = [r for r in records if r.get("true_relation") and str(r.get("true_relation")).strip()]
        if not annotated:
            print(f"Found {len(records)} relation rows in {input_path}, but none have 'true_relation' annotated.")
            sys.exit(0)

        results = evaluate_claim_relations(annotated)
        print("\n" + "=" * 60)
        print("CLAIM RELATION EVALUATION REPORT")
        print("=" * 60)
        print(f"Annotated Samples: {results.get('sample_size', 0)}")
        print(f"True Positives:    {results.get('true_positives', 0)}")
        print(f"False Positives:   {results.get('false_positives', 0)}")
        print(f"False Negatives:   {results.get('false_negatives', 0)}")
        print(f"True Negatives:    {results.get('true_negatives', 0)}")
        print("-" * 60)
        prec = results.get("precision")
        rec = results.get("recall")
        f1 = results.get("f1")
        print(f"Precision:         {f'{prec:.2%}' if prec is not None else 'N/A'}")
        print(f"Recall:            {f'{rec:.2%}' if rec is not None else 'N/A'}")
        print(f"F1 Score:          {f'{f1:.2%}' if f1 is not None else 'N/A'}")
        print("=" * 60)
    else:
        records = load_annotations_csv(input_path)
        annotated = [r for r in records if r.get("is_true_claim") is not None and str(r.get("is_true_claim")) != ""]
        if not annotated:
            print(f"Found {len(records)} candidate rows in {input_path}, but none have been annotated yet.")
            print("Fill in 'is_true_claim' (1 or 0) for evaluated rows to compute metrics.")
            sys.exit(0)

        results = evaluate_claim_extraction(annotated)
        print("\n" + "=" * 60)
        print("CLAIM EXTRACTION EVALUATION REPORT")
        print("=" * 60)
        print(f"Annotated Samples: {results.get('sample_size', 0)}")
        print(f"True Positives:    {results.get('true_positives', 0)}")
        print(f"False Positives:   {results.get('false_positives', 0)}")
        print(f"False Negatives:   {results.get('false_negatives', 0)}")
        print(f"True Negatives:    {results.get('true_negatives', 0)}")
        print("-" * 60)
        prec = results.get("precision")
        rec = results.get("recall")
        f1 = results.get("f1")
        t_acc = results.get("type_accuracy")
        print(f"Precision:         {f'{prec:.2%}' if prec is not None else 'N/A'}")
        print(f"Recall:            {f'{rec:.2%}' if rec is not None else 'N/A'}")
        print(f"F1 Score:          {f'{f1:.2%}' if f1 is not None else 'N/A'}")
        print(f"Category Accuracy: {f'{t_acc:.2%}' if t_acc is not None else 'N/A'}")
        print("=" * 60)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nEvaluation metrics written to {out_p}")


if __name__ == "__main__":
    main()
