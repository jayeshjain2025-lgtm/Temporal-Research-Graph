"""Claim extraction and relationship evaluation module — Phase 3, Milestone 3.6.

Implements evaluation metrics calculation (Precision, Recall, F1) for:
1. Candidate claim extraction (valid claim sentence vs non-claim)
2. Claim categorization (finding, method, comparison, limitation, dataset)
3. Claim relationship detection and classification (SUPPORTS, CHALLENGES, REFINES, QUALIFIES)

Strict epistemic rule:
Precision and recall are computed ONLY when a human-annotated ground truth sample
is provided.  Without ground truth, metrics return status='no_ground_truth'.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.claims.extractor import extract_claim_candidates
from src.models import Paper


def compute_binary_metrics(
    true_positives: int,
    false_positives: int,
    false_negatives: int,
    true_negatives: int = 0,
) -> dict[str, Any]:
    """Compute precision, recall, and F1 given contingency counts.

    Returns None for precision / recall when the denominator is zero.
    """
    total = true_positives + false_positives + false_negatives + true_negatives
    if total == 0:
        return {
            "status": "empty_sample",
            "sample_size": 0,
            "precision": None,
            "recall": None,
            "f1": None,
            "accuracy": None,
        }

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else None
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else None
    )
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * (precision * recall) / (precision + recall)
    else:
        f1 = None

    accuracy = (true_positives + true_negatives) / total if total > 0 else None

    return {
        "status": "evaluated",
        "sample_size": total,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
    }


def evaluate_claim_extraction(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate candidate claim extraction against human ground truth annotations.

    Each annotation dict must have:
    - ``is_predicted_claim``: bool (model extracted this sentence as a claim)
    - ``is_true_claim``: bool (human marked this sentence as an actual claim)
    - Optional ``predicted_type``: str
    - Optional ``true_type``: str

    Returns
    -------
    dict with overall binary extraction metrics and category confusion breakdown.
    """
    if not annotations:
        return {
            "status": "no_annotations_provided",
            "sample_size": 0,
            "precision": None,
            "recall": None,
            "f1": None,
            "type_accuracy": None,
        }

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    type_matches = 0
    type_evaluated = 0

    for item in annotations:
        pred = bool(item.get("is_predicted_claim", False))
        true = bool(item.get("is_true_claim", False))

        if pred and true:
            tp += 1
            # Check type classification accuracy for true positives
            pred_type = item.get("predicted_type")
            true_type = item.get("true_type")
            if pred_type and true_type:
                type_evaluated += 1
                if pred_type.strip().lower() == true_type.strip().lower():
                    type_matches += 1
        elif pred and not true:
            fp += 1
        elif not pred and true:
            fn += 1
        else:
            tn += 1

    metrics = compute_binary_metrics(tp, fp, fn, tn)
    type_acc = (type_matches / type_evaluated) if type_evaluated > 0 else None
    metrics["type_accuracy"] = round(type_acc, 4) if type_acc is not None else None
    metrics["type_sample_size"] = type_evaluated
    return metrics


def evaluate_claim_relations(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate candidate claim relationship detection against human ground truth.

    Each annotation dict must have:
    - ``predicted_relation``: str | None (e.g. 'SUPPORTS', 'CHALLENGES', or None)
    - ``true_relation``: str | None (ground truth label, or None/NO_RELATION)
    """
    if not annotations:
        return {
            "status": "no_annotations_provided",
            "sample_size": 0,
            "precision": None,
            "recall": None,
            "f1": None,
        }

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for item in annotations:
        pred = item.get("predicted_relation")
        true = item.get("true_relation")

        pred_has_rel = bool(pred and pred.strip().upper() not in {"NONE", "NO_RELATION", ""})
        true_has_rel = bool(true and true.strip().upper() not in {"NONE", "NO_RELATION", ""})

        if pred_has_rel and true_has_rel:
            # Check if relation type matched
            if pred.strip().upper() == true.strip().upper():
                tp += 1
            else:
                # Wrong relation type counts as a classification error
                fp += 1
                fn += 1
        elif pred_has_rel and not true_has_rel:
            fp += 1
        elif not pred_has_rel and true_has_rel:
            fn += 1
        else:
            tn += 1

    return compute_binary_metrics(tp, fp, fn, tn)


def load_annotations_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load human annotation records from a CSV file."""
    csv_path = Path(path)
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for r in reader:
            # Convert boolean fields
            row_dict: dict[str, Any] = dict(r)
            if "is_true_claim" in row_dict:
                val = str(row_dict["is_true_claim"]).strip().lower()
                row_dict["is_true_claim"] = val in {"1", "true", "yes", "y"}
            if "is_predicted_claim" in row_dict:
                val = str(row_dict["is_predicted_claim"]).strip().lower()
                row_dict["is_predicted_claim"] = val in {"1", "true", "yes", "y"}
            rows.append(row_dict)
        return rows


def export_annotation_sample_csv(
    session: Session,
    output_path: Path | str,
    limit_papers: int = 20,
) -> int:
    """Generate a sample CSV file for human annotation from database papers.

    Extracts candidate sentences using deterministic rules and formats them
    for human review (is_true_claim: 1/0, true_type: finding/method/comparison/limitation/not_claim).

    Returns
    -------
    Number of candidate sentences written to CSV.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    papers = session.execute(
        select(Paper)
        .where(Paper.abstract.is_not(None))
        .order_by(Paper.publication_year.desc().nulls_last(), Paper.id.asc())
        .limit(limit_papers)
    ).scalars().all()

    rows = []
    sample_id = 1
    for p in papers:
        candidates = extract_claim_candidates(p.abstract or "")
        for c in candidates:
            rows.append({
                "sample_id": sample_id,
                "paper_external_id": p.external_id,
                "paper_title": p.title,
                "publication_year": p.publication_year,
                "candidate_sentence": c.text,
                "predicted_type": c.claim_type,
                "heuristic_confidence": c.confidence,
                "is_predicted_claim": 1,
                "is_true_claim": "",  # To be annotated by human (1 or 0)
                "true_type": "",      # To be annotated by human
                "annotator_notes": "",
            })
            sample_id += 1

    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def export_relation_annotation_sample_csv(
    session: Session,
    output_path: Path | str,
    limit: int = 50,
) -> int:
    """Generate a sample CSV file for human annotation of claim relationships.

    Exports detected ClaimRelations with source/target claim texts for human validation
    (true_relation: SUPPORTS, CHALLENGES, REFINES, QUALIFIES, or NO_RELATION).

    Returns
    -------
    Number of relation candidates written to CSV.
    """
    from src.models import Claim
    from src.models.relationships import ClaimRelation

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    relations = session.execute(
        select(ClaimRelation)
        .order_by(ClaimRelation.id.asc())
        .limit(limit)
    ).scalars().all()

    rows = []
    sample_id = 1
    for r in relations:
        source_c = session.get(Claim, r.source_claim_id)
        target_c = session.get(Claim, r.target_claim_id)
        rows.append({
            "sample_id": sample_id,
            "source_claim_id": r.source_claim_id,
            "source_claim_text": source_c.text if source_c else "",
            "target_claim_id": r.target_claim_id,
            "target_claim_text": target_c.text if target_c else "",
            "predicted_relation": r.relation_type,
            "true_relation": "",  # To be annotated by human
            "annotator_notes": "",
        })
        sample_id += 1

    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
