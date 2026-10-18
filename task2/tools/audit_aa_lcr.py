"""Independent replay against raw AA-LCR grades; no benchmark_reference imports.

Run from task2/: python tools/audit_aa_lcr.py --data-root ../Evals --reports output/aa-lcr-pruning
Shares only the independent exact linear interval inverter with the LCB auditor.
"""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from audit_lcb import audit_bounds


def band(values: dict[int, int], index: int) -> int:
    lower = sum(v < values[index] for v in values.values())
    equal = sum(v == values[index] for v in values.values())
    return min(2, (3 * (2 * lower + equal)) // (2 * len(values)))


def audit_selection(
    selection: dict[str, Any],
    grades: dict[str, dict[int, float]],
    lengths: dict[int, int],
    documents: dict[int, int],
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = selection["samples"]
    population = len(lengths)
    assert (
        len(members)
        == len({x["index"] for x in members})
        == math.ceil(population * selection["keep_ratio"])
    )
    assert math.isclose(sum(x["weight"] for x in members), 1)
    groups: dict[int, str] = {}
    for index in lengths:
        if selection["strategy"] == "metadata_stratified":
            group = f"length:{band(lengths, index)}|documents:{band(documents, index)}"
        elif selection["strategy"] == "length_difficulty_stratified":
            passes = sum(int(grades[m][index]) for m in selection["reference_models"])
            group = f"length:{band(lengths, index)}|passes:{passes}"
        else:
            group = "comparison_only"
        groups[index] = group
    sizes = Counter(groups.values())
    sampled = Counter(x["stratum"] for x in members)
    assert sizes.keys() == sampled.keys()
    for item in members:
        key = groups[item["index"]]
        assert item["stratum"] == key
        assert item["population_count"] == sizes[key]
        assert item["selected_count"] == sampled[key]
        assert math.isclose(item["weight"], sizes[key] / (population * sampled[key]))
    return members


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args()
    root, reports = args.data_root, args.reports
    manifest = json.loads((reports / "manifest.json").read_text())
    for source in manifest["inputs"]:
        assert hashlib.sha256((root / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    for name, digest in manifest["output_sha256"].items():
        assert hashlib.sha256((reports / name).read_bytes()).hexdigest() == digest
    implementation = Path(__file__).parents[1] / "src/benchmark_reference"
    for name, digest in manifest["implementation_sha256"].items():
        assert (
            hashlib.sha256((implementation / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            == digest
        )
    grades: dict[str, dict[int, float]] = {}
    lengths: dict[int, int] = {}
    documents: dict[int, int] = {}
    for source in manifest["inputs"]:
        for line in (root / source["path"]).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            index = row["index"]
            if "/reviews/" in source["path"]:
                model = Path(source["path"]).stem.split("__")[1]
                grades.setdefault(model, {})[index] = row["sample_score"]["score"]["value"]["acc"]
            else:
                tokens = row["metadata"]["input_tokens"]
                count = len(
                    {u.strip() for u in row["metadata"]["data_source_urls"].split(";") if u.strip()}
                )
                assert lengths.setdefault(index, tokens) == tokens
                assert documents.setdefault(index, count) == count
    full = {m: sum(v.values()) / len(v) for m, v in grades.items()}
    report = json.loads((reports / "fidelity.json").read_text())
    selections = [
        json.loads(line) for line in (reports / "selections.jsonl").read_text().splitlines()
    ]
    for run, selection in zip(report["runs"], selections, strict=True):
        assert run["held_out_model"] not in selection["reference_models"]
        members = audit_selection(selection, grades, lengths, documents)
        for model in grades:
            estimate = sum(x["weight"] * grades[model][x["index"]] for x in members)
            assert math.isclose(estimate, run["estimated_scores"][model], abs_tol=1e-12)
            assert full[model] == run["full_scores"][model]
            if run["score_intervals"][model] is not None:
                low, high = audit_bounds(members, grades[model], manifest["confidence"])
                assert math.isclose(
                    float(low), run["score_intervals"][model]["lower"], abs_tol=1e-12
                )
                assert math.isclose(
                    float(high), run["score_intervals"][model]["upper"], abs_tol=1e-12
                )
    selections = [
        json.loads(line) for line in (reports / "pair_selections.jsonl").read_text().splitlines()
    ]
    for run, selection in zip(report["pair_transfer_runs"], selections, strict=True):
        a, b = run["models"]
        assert not set((a, b)) & set(selection["reference_models"])
        members = audit_selection(selection, grades, lengths, documents)
        difference = sum(
            x["weight"] * (grades[a][x["index"]] - grades[b][x["index"]]) for x in members
        )
        assert math.isclose(difference, run["estimated_difference"], abs_tol=1e-12)
        interval = run["difference_interval"]
        if interval is not None:
            forward = {i: float(grades[a][i] > grades[b][i]) for i in lengths}
            backward = {i: float(grades[b][i] > grades[a][i]) for i in lengths}
            a_low, a_high = audit_bounds(members, forward, manifest["confidence"], families=2)
            b_low, b_high = audit_bounds(members, backward, manifest["confidence"], families=2)
            assert math.isclose(float(a_low - b_high), interval["lower"], abs_tol=1e-12)
            assert math.isclose(float(a_high - b_low), interval["upper"], abs_tol=1e-12)
    noise = json.loads((reports / "judge_noise.json").read_text())
    assert noise["estimated_judge_flip_rate"] is noise["estimated_judge_variance"] is None
    assert noise["answers_with_repeat_reviews"] == 0
    assert noise["recorded_grade_count"] == sum(map(len, grades.values()))
    for row in noise["full_pair_tipping"]:
        a, b = row["models"]
        assert row["minimum_total_flips_to_tie"] == abs(
            sum(grades[a].values()) - sum(grades[b].values())
        )
    print(
        f"Audited {len(report['runs'])} score runs, {len(report['pair_transfer_runs'])} pair runs, "
        f"all intervals, metadata strata, weights and provenance. Full scores: {full}"
    )


if __name__ == "__main__":
    main()
