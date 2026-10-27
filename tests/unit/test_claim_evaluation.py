"""Tests for Phase 3 Milestone 3.6 — claim evaluation workflow and metrics.

Coverage
--------
EV1  compute_binary_metrics computes correct Precision, Recall, F1, and Accuracy
EV2  compute_binary_metrics handles zero denominator edge cases without crashing
EV3  evaluate_claim_extraction handles mixed TP, FP, FN, TN and type accuracy
EV4  evaluate_claim_extraction with empty annotations returns no_annotations_provided
EV5  evaluate_claim_relations calculates relation classification precision/recall
EV6  load_annotations_csv correctly parses boolean values (1, true, yes, 0, false)
EV7  export_annotation_sample_csv generates valid CSV with correct headers from papers
"""
import csv
from datetime import date
from pathlib import Path
import pytest

from src.analysis.claims.evaluation import (
    compute_binary_metrics,
    evaluate_claim_extraction,
    evaluate_claim_relations,
    export_annotation_sample_csv,
    export_relation_annotation_sample_csv,
    load_annotations_csv,
)
from src.models import Claim, Paper
from src.models.relationships import ClaimRelation


def test_compute_binary_metrics_standard():
    metrics = compute_binary_metrics(true_positives=8, false_positives=2, false_negatives=2, true_negatives=8)
    assert metrics["status"] == "evaluated"
    assert metrics["sample_size"] == 20
    assert metrics["precision"] == 0.8
    assert metrics["recall"] == 0.8
    assert metrics["f1"] == 0.8
    assert metrics["accuracy"] == 0.8


def test_compute_binary_metrics_zero_denominators():
    empty = compute_binary_metrics(0, 0, 0, 0)
    assert empty["status"] == "empty_sample"
    assert empty["precision"] is None
    assert empty["recall"] is None

    no_pred_pos = compute_binary_metrics(0, 0, 5, 5)
    assert no_pred_pos["precision"] is None
    assert no_pred_pos["recall"] == 0.0


def test_evaluate_claim_extraction():
    sample = [
        {"is_predicted_claim": True, "is_true_claim": True, "predicted_type": "finding", "true_type": "finding"},
        {"is_predicted_claim": True, "is_true_claim": True, "predicted_type": "method", "true_type": "method"},
        {"is_predicted_claim": True, "is_true_claim": True, "predicted_type": "comparison", "true_type": "finding"},  # type mismatch
        {"is_predicted_claim": True, "is_true_claim": False, "predicted_type": "finding", "true_type": "not_claim"},  # FP
        {"is_predicted_claim": False, "is_true_claim": True, "predicted_type": None, "true_type": "limitation"},      # FN
        {"is_predicted_claim": False, "is_true_claim": False, "predicted_type": None, "true_type": "not_claim"},     # TN
    ]
    res = evaluate_claim_extraction(sample)
    assert res["status"] == "evaluated"
    assert res["true_positives"] == 3
    assert res["false_positives"] == 1
    assert res["false_negatives"] == 1
    assert res["true_negatives"] == 1
    # Precision = 3 / (3 + 1) = 0.75
    assert res["precision"] == 0.75
    # Recall = 3 / (3 + 1) = 0.75
    assert res["recall"] == 0.75
    # Type accuracy for true positives: 2 matches out of 3 = 0.6667
    assert res["type_accuracy"] == 0.6667


def test_evaluate_claim_extraction_empty():
    res = evaluate_claim_extraction([])
    assert res["status"] == "no_annotations_provided"
    assert res["precision"] is None


def test_evaluate_claim_relations():
    sample = [
        {"predicted_relation": "SUPPORTS", "true_relation": "SUPPORTS"},
        {"predicted_relation": "CHALLENGES", "true_relation": "CHALLENGES"},
        {"predicted_relation": "SUPPORTS", "true_relation": "NO_RELATION"},  # FP
        {"predicted_relation": None, "true_relation": "REFINES"},            # FN
        {"predicted_relation": None, "true_relation": None},                 # TN
    ]
    res = evaluate_claim_relations(sample)
    assert res["true_positives"] == 2
    assert res["false_positives"] == 1
    assert res["false_negatives"] == 1
    assert res["precision"] == 0.6667
    assert res["recall"] == 0.6667


def test_load_annotations_csv(tmp_path: Path):
    csv_file = tmp_path / "annotations.csv"
    with csv_file.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sample_id", "is_predicted_claim", "is_true_claim", "true_type"])
        writer.writeheader()
        writer.writerow({"sample_id": "1", "is_predicted_claim": "1", "is_true_claim": "true", "true_type": "finding"})
        writer.writerow({"sample_id": "2", "is_predicted_claim": "0", "is_true_claim": "no", "true_type": "not_claim"})

    rows = load_annotations_csv(csv_file)
    assert len(rows) == 2
    assert rows[0]["is_predicted_claim"] is True
    assert rows[0]["is_true_claim"] is True
    assert rows[1]["is_predicted_claim"] is False
    assert rows[1]["is_true_claim"] is False


def test_export_annotation_sample_csv(session, tmp_path: Path):
    p = Paper(
        external_id="W_EVAL_1",
        title="Testing Claim Extraction",
        abstract="Our results demonstrate that graph embeddings improve temporal link prediction accuracy.",
        publication_year=2023,
        publication_date=date(2023, 1, 1),
        source="openalex",
    )
    session.add(p)
    session.flush()

    out_csv = tmp_path / "sample.csv"
    count = export_annotation_sample_csv(session, out_csv, limit_papers=5)
    assert count >= 1
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames
        assert "sample_id" in headers
        assert "candidate_sentence" in headers
        assert "predicted_type" in headers
        assert "is_true_claim" in headers
        first_row = next(reader)
        assert first_row["paper_external_id"] == "W_EVAL_1"
        assert first_row["predicted_type"] == "finding"


def test_export_relation_annotation_sample_csv(session, tmp_path: Path):
    c1 = Claim(text="Claim A text", normalized_text="claim a text", claim_type="finding")
    c2 = Claim(text="Claim B text", normalized_text="claim b text", claim_type="finding")
    session.add_all([c1, c2])
    session.flush()

    rel = ClaimRelation(
        source_claim_id=c1.id,
        target_claim_id=c2.id,
        relation_type="SUPPORTS",
    )
    session.add(rel)
    session.flush()

    out_csv = tmp_path / "relation_sample.csv"
    count = export_relation_annotation_sample_csv(session, out_csv, limit=10)
    assert count == 1
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames
        assert "sample_id" in headers
        assert "source_claim_id" in headers
        assert "source_claim_text" in headers
        assert "target_claim_id" in headers
        assert "target_claim_text" in headers
        assert "predicted_relation" in headers
        assert "true_relation" in headers
        first_row = next(reader)
        assert first_row["predicted_relation"] == "SUPPORTS"
        assert first_row["source_claim_text"] == "Claim A text"
        assert first_row["target_claim_text"] == "Claim B text"
