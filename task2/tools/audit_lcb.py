"""Independent stdlib replay of saved selections against raw coding review grades.

Run from task2/: python tools/audit_lcb.py --data-root ../Evals --reports output/lcb-pruning
Does not import benchmark_reference or rerun its normalization/selection/aggregation.
"""

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args()
    root: Path = args.data_root
    reports: Path = args.reports
    manifest = json.loads((reports / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["inputs"]:
        assert hashlib.sha256((root / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    for name, digest in manifest["output_sha256"].items():
        assert hashlib.sha256((reports / name).read_bytes()).hexdigest() == digest
    code = Path(__file__).resolve().parents[1] / "src/benchmark_reference"
    for name, digest in manifest["implementation_sha256"].items():
        canonical_source = (code / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical_source).hexdigest() == digest

    grades: dict[str, dict[int, float]] = {}
    for path in sorted((root / "Part 1/reviews").glob("live_code_bench_v5__*.jsonl")):
        values: dict[int, float] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            index, score = row["index"], row["sample_score"]["score"]["value"]["pass"]
            assert index not in values and type(index) is int and score in (0, 1)
            values[index] = score
        assert len(values) == 315
        grades[path.stem.split("__")[1]] = values
    assert len(grades) == 3
    normalized = json.loads((reports / "scores.json").read_text(encoding="utf-8"))["samples"]
    assert len(normalized) == 945
    for sample in normalized:
        assert sample["score"] == grades[sample["model"]][sample["index"]]
    full = {model: sum(values.values()) / 315 for model, values in grades.items()}
    fidelity = json.loads((reports / "fidelity.json").read_text(encoding="utf-8"))
    selections = (reports / "selections.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(selections) == len(fidelity["runs"]) == manifest["run_count"]
    errors: dict[tuple[str, float, str], list[float]] = defaultdict(list)
    for line, run in zip(selections, fidelity["runs"], strict=True):
        selection = json.loads(line)
        for key in ("held_out_model", "strategy", "keep_ratio", "seed", "reference_models", "role"):
            assert selection[key] == run[key]
        assert selection["held_out_model"] not in selection["reference_models"]
        assert set(selection["reference_models"]) == set(grades) - {selection["held_out_model"]}
        members = selection["samples"]
        assert len({item["index"] for item in members}) == math.ceil(315 * selection["keep_ratio"])
        assert math.isclose(sum(item["weight"] for item in members), 1)
        assert run["full_scores"] == full
        for model in grades:
            estimate = sum(item["weight"] * grades[model][item["index"]] for item in members)
            assert math.isclose(estimate, run["estimated_scores"][model], abs_tol=1e-12)
        held = selection["held_out_model"]
        error = abs(run["estimated_scores"][held] - full[held])
        assert error == run["held_out_absolute_error"]
        for model in (held, "__all__"):
            errors[(run["strategy"], run["keep_ratio"], model)].append(error)
    for row in fidelity["summary"]:
        observed_errors = errors[(row["strategy"], row["keep_ratio"], row["held_out_model"])]
        assert math.isclose(statistics.mean(observed_errors), row["held_out_mae"], abs_tol=1e-12)
        assert max(observed_errors) == row["held_out_max_absolute_error"]
    print(f"Audited {len(selections)} selections, all score estimates, summaries and hashes.")


if __name__ == "__main__":
    main()
