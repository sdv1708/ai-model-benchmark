"""Verify panel fingerprints against pinned public question columns, without inference.

Run with the ``public-source`` extra:
``uv run --extra public-source python tools/verify_lcb_source.py --panel ... --output ...``.
Only question/identity columns are fetched over HTTP byte ranges; large hidden-test
columns are excluded. This research check requires internet, but no credential.
"""

import argparse
import json
from pathlib import Path

from benchmark_reference.public_lcb import (
    DATASET,
    DATASET_REVISION,
    DATASET_SUBSET,
    question_fingerprint,
    read_dataset_rows,
)
from benchmark_reference.reporting import validate_output_location


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_output_location(args.output.parent, args.panel.parent, output_names=[args.output.name])
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    wanted = {task["question_sha256"] for task in panel["tasks"]}
    rows = read_dataset_rows()
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        fingerprint = question_fingerprint(row["question_content"])
        if fingerprint in wanted:
            if fingerprint in found:
                raise ValueError("Duplicate public source question fingerprint")
            found[fingerprint] = row
    if len(found) != len(wanted):
        raise ValueError(f"Public source misses {len(wanted - found.keys())} reference questions")
    result = {
        "dataset": DATASET,
        "revision": DATASET_REVISION,
        "subset": DATASET_SUBSET,
        "source_count": len(rows),
        "reference_count": len(wanted),
        "matched": len(found),
        "missing": [],
        "matched_date_min": min(row["contest_date"] for row in found.values()),
        "matched_date_max": max(row["contest_date"] for row in found.values()),
        "method": "Projected parquet question columns over HTTP ranges; no inference or grading.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Matched {len(found)} reference questions uniquely in {len(rows)} public source rows")


if __name__ == "__main__":
    main()
