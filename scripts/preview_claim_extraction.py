"""Preview candidate claims extracted from provenance evidence records.

Usage
-----
1. Export a CSV from psql::

    \\copy (
        SELECT id, source_identifier, evidence_text, confidence
        FROM provenance
        WHERE source_type = '"'"'abstract'"'"'
          AND evidence_text IS NOT NULL
          AND BTRIM(evidence_text) <> '"'"''"'"'
        ORDER BY id
        LIMIT 100
    ) TO '"'"'claim_extraction_preview.csv'"'"' WITH (FORMAT CSV, HEADER TRUE);

2. Run this script from the project root::

    python scripts/preview_claim_extraction.py

Notes
-----
* Each provenance row is treated as an independent text unit.
* If evidence_text contains sentence *fragments* rather than a full abstract,
  candidate yield will be lower than when extracting from whole abstracts.
  That is expected behaviour — fragments often do not contain the epistemic
  markers the extractor targets.
"""
import csv
import sys
from pathlib import Path

from src.analysis.claims.extractor import extract_claim_candidates

INPUT = Path("claim_extraction_preview.csv")

_SEP = "=" * 80


def main() -> None:
    if not INPUT.exists():
        print(
            f"[error] {INPUT} not found.\n"
            "Export it first with the \\copy command shown at the top of this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    with INPUT.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    total_evidence = 0
    total_candidates = 0
    type_counts: dict[str, int] = {}

    for row in rows:
        evidence = (row.get("evidence_text") or "").strip()
        if not evidence:
            continue

        total_evidence += 1
        candidates = extract_claim_candidates(evidence)
        total_candidates += len(candidates)

        for c in candidates:
            type_counts[c.claim_type] = type_counts.get(c.claim_type, 0) + 1

        if candidates:
            print(f"\n{_SEP}")
            print(f"Provenance ID : {row['id']}")
            print(f"Source        : {row.get('source_identifier', '(none)')}")
            confidence = row.get("confidence", "")
            if confidence:
                print(f"Confidence    : {confidence}")
            print(f"Candidates    : {len(candidates)}")
            print()
            for i, c in enumerate(candidates, 1):
                print(f"  [{i}] type={c.claim_type}")
                # Wrap display text at 72 chars for readability
                words = c.text.split()
                line = "      "
                for word in words:
                    if len(line) + len(word) + 1 > 76:
                        print(line)
                        line = "      " + word
                    else:
                        line = line + (" " if line.strip() else "") + word
                if line.strip():
                    print(line)
                print()

    # Summary
    print(f"\n{_SEP}")
    print("SUMMARY")
    print(f"  Evidence records processed : {total_evidence}")
    print(f"  Total candidates extracted : {total_candidates}")
    if total_evidence:
        ratio = total_candidates / total_evidence
        print(f"  Candidates per record      : {ratio:.2f}")
    if type_counts:
        print("  By claim type:")
        for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {ctype:<12} {count}")
    print(_SEP)

    if total_candidates == 0:
        print(
            "\n[note] No candidates found.  If evidence_text contains sentence "
            "fragments rather than full abstracts, this is expected.  "
            "Re-run against full paper abstracts from the papers table for "
            "a more representative yield estimate."
        )


if __name__ == "__main__":
    main()
