"""Verify panel fingerprints against pinned public question columns, without inference.

Run in the EvalScope environment (fsspec, aiohttp and pyarrow are already present).
Only question/identity columns are fetched over HTTP byte ranges; large hidden-test
columns are excluded. This research check requires internet, but no credential.
"""

import argparse
import hashlib
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmark_reference.reporting import validate_output_location

DATASET = "marianna13/livecodebench_code_generation_lite_parquet"
REVISION = "e70df9620dd54c12afac5e2881355de6f9ece2e9"


def read_shard(index: int) -> list[dict[str, str]]:
    """Project only the small columns needed to check original problem identity."""
    fsspec = importlib.import_module("fsspec")
    parquet = importlib.import_module("pyarrow.parquet")
    root = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}"
    url = f"{root}/release_v5/test-{index:05d}-of-00009.parquet?download=true"
    with fsspec.open(url, "rb", block_size=256 * 1024).open() as stream:
        table = parquet.ParquetFile(stream).read(
            columns=["question_content", "question_id", "platform", "contest_date"]
        )
    rows: list[dict[str, str]] = table.to_pylist()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_output_location(args.output.parent, args.panel.parent, output_names=[args.output.name])
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    wanted = {task["question_sha256"] for task in panel["tasks"]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [row for shard in pool.map(read_shard, range(9)) for row in shard]
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        normalized = row["question_content"].replace("\r\n", "\n").replace("\r", "\n").strip()
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if fingerprint in wanted:
            if fingerprint in found:
                raise ValueError("Duplicate public source question fingerprint")
            found[fingerprint] = row
    if len(found) != len(wanted):
        raise ValueError(f"Public source misses {len(wanted - found.keys())} reference questions")
    result = {
        "dataset": DATASET,
        "revision": REVISION,
        "subset": "release_v5",
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
