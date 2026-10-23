"""Export the validated AA-LCR historical panel, optionally verify pinned source metadata.

The panel contains no answers or model generations. Native EvalScope selection uses
it without importing this analysis package or making inference calls.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.long_context import extract_metadata
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location

SOURCE_REVISION = "bdae010bbce259820c0e34c1d7cce210d966fb75"


def fingerprint(question: str) -> str:
    """Use the native content identity, independent of source row position."""
    return hashlib.sha256(
        question.replace("\r\n", "\n").replace("\r", "\n").strip().encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_output_location(
            args.output.parent, args.data_root, output_names=[args.output.name]
        )
        pairs = [p for p in discover_pairs(args.data_root) if p.benchmark == "aa_lcr"]
        samples = [sample for pair in pairs for sample in analyze_pair(pair)]
        metadata = extract_metadata(samples)
        scores = {
            pair.model: {s.index: int(s.score) for s in samples if s.model == pair.model}
            for pair in pairs
        }
        questions: dict[int, str] = {}
        for sample in samples:
            raw = sample.metadata["sample_metadata"]
            assert isinstance(raw, dict)
            question = raw["question"]
            assert isinstance(question, str)
            questions[sample.index] = question
        if len(metadata) != 100 or any(set(values) != set(metadata) for values in scores.values()):
            raise AnalysisError("The complete aligned 100-question AA-LCR panel is required")
        with args.source_csv.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        source = {fingerprint(row["question"]): row for row in rows}
        if len(source) != 100 or len(rows) != 100:
            raise AnalysisError("Expected 100 unique pinned source questions")
        # Five supplied questions contain UTF-8 decoded as Mac Roman. Verify the
        # exact reversible transformation; do not apply fuzzy/semantic matching.
        legacy = {
            fingerprint(row["question"].encode("utf-8").decode("mac_roman")): row for row in rows
        }
        canonical: dict[int, str] = {}
        repaired: list[int] = []
        for index, question in questions.items():
            row = source.get(fingerprint(question))
            if row is None:
                row = legacy.get(fingerprint(question))
                repaired.append(index)
            if row is None:
                raise AnalysisError(f"Pinned AA-LCR question mismatch at {index}")
            canonical[index] = row["question"]
        tasks = [
            {
                "index": index,
                "question_sha256": fingerprint(canonical[index]),
                "scores": {name: scores[name][index] for name in sorted(scores)},
                "input_tokens": task.input_tokens,
                "source_urls": list(task.source_urls),
            }
            for index, task in metadata.items()
        ]
        if len({task["question_sha256"] for task in tasks}) != 100:
            raise AnalysisError("Ambiguous AA-LCR question fingerprints")
        for task in tasks:
            row = source.get(str(task["question_sha256"]))
            if (
                row is None
                or int(row["input_tokens"]) != task["input_tokens"]
                or sorted(
                    {url.strip() for url in row["data_source_urls"].split(";") if url.strip()}
                )
                != task["source_urls"]
            ):
                raise AnalysisError(f"Pinned AA-LCR source mismatch at {task['index']}")
        verification = {
            "verified": True,
            "unique_matches": 100,
            "exact_question_matches": 100 - len(repaired),
            "utf8_decoded_as_mac_roman_indices": sorted(repaired),
            "csv_sha256": hashlib.sha256(args.source_csv.read_bytes()).hexdigest(),
            "scope": "Question identity, benchmark token counts and canonical URL sets",
        }
        files = sorted({p.predictions for p in pairs} | {p.reviews for p in pairs})
        panel = {
            "schema_version": 1,
            "tasks": tasks,
            "provenance": {
                "benchmark": "aa_lcr",
                "source_revision": SOURCE_REVISION,
                "source_verification": verification,
                "cross_model_identity": (
                    "supplied shared index; cross-model question/metadata agreement"
                ),
                "judge_noise": "One recorded grade per answer; repeat-judge variance unmeasured",
                "source_sha256": {
                    path.relative_to(args.data_root).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in files
                },
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(panel, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    except (AnalysisError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"export-aa-lcr-panel: {exc}\n")
    print(f"Exported {len(tasks)} AA-LCR questions; source verified={bool(args.source_csv)}")


if __name__ == "__main__":
    main()
