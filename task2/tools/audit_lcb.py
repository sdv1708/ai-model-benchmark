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
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=32768)
def exact_counts(
    population: int, sampled: int, successes: int, failure: Fraction
) -> tuple[int, int]:
    """Independent linear inversion; production uses a binary search instead."""
    denominator = math.comb(population, sampled)
    cutoff = failure / 2

    def tail(count: int, upper: bool) -> Fraction:
        support = range(max(0, sampled + count - population), min(sampled, count) + 1)
        numerator = sum(
            math.comb(count, x) * math.comb(population - count, sampled - x)
            for x in support
            if (x >= successes if upper else x <= successes)
        )
        return Fraction(numerator, denominator)

    lower, upper = successes, population - sampled + successes
    while tail(lower, True) < cutoff:
        lower += 1
    while tail(upper, False) < cutoff:
        upper -= 1
    return lower, upper


def audit_bounds(
    members: list[dict[str, Any]],
    grades: dict[int, float],
    confidence: float,
    families: int = 1,
) -> tuple[Fraction, Fraction]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in members:
        groups[item["stratum"]].append(item)
    population = sum(group[0]["population_count"] for group in groups.values())
    failure = (1 - Fraction(str(confidence))) / (len(groups) * families)
    bounds = [
        exact_counts(
            group[0]["population_count"],
            len(group),
            sum(int(grades[item["index"]]) for item in group),
            failure,
        )
        for group in groups.values()
    ]
    return (
        Fraction(sum(low for low, _ in bounds), population),
        Fraction(sum(high for _, high in bounds), population),
    )


def audit_selection(
    selection: dict[str, Any],
    grades: dict[str, dict[int, float]],
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = selection["samples"]
    count = math.ceil(315 * selection["keep_ratio"])
    assert len(members) == len({item["index"] for item in members}) == count
    assert math.isclose(sum(item["weight"] for item in members), 1)
    references = selection["reference_models"]
    groups: dict[str, int] = defaultdict(int)
    expected_group = {}
    for index in next(iter(grades.values())):
        pattern = [int(grades[model][index]) for model in references]
        if selection["strategy"] == "response_stratified":
            group = "pattern:" + "".join(map(str, pattern))
        elif selection["strategy"] == "difficulty_stratified":
            group = f"passes:{sum(pattern)}/{len(pattern)}"
        else:
            group = "comparison_only"
        groups[group] += 1
        expected_group[index] = group
    sampled: dict[str, int] = defaultdict(int)
    for item in members:
        assert item["stratum"] == expected_group[item["index"]]
        sampled[item["stratum"]] += 1
    assert sampled.keys() == groups.keys()
    for item in members:
        size, selected = groups[item["stratum"]], sampled[item["stratum"]]
        assert item["population_count"] == size and item["selected_count"] == selected
        assert math.isclose(item["weight"], size / (315 * selected))
    return members


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args()
    # N=50,n=10,x=3: K=4 has upper tail .021754 and K=32 lower tail
    # .017635, both below .025. Thus the inclusive non-rejected counts are [5,31].
    assert exact_counts(50, 10, 3, Fraction(1, 20)) == (5, 31)
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
        members = audit_selection(selection, grades)
        assert run["full_scores"] == full
        for model in grades:
            estimate = sum(item["weight"] * grades[model][item["index"]] for item in members)
            assert math.isclose(estimate, run["estimated_scores"][model], abs_tol=1e-12)
            interval = run["score_intervals"][model]
            if interval is not None:
                assert tuple(
                    map(float, audit_bounds(members, grades[model], manifest["confidence"]))
                ) == (
                    interval["lower"],
                    interval["upper"],
                )
        held = selection["held_out_model"]
        error = abs(run["estimated_scores"][held] - full[held])
        assert error == run["held_out_absolute_error"]
        for decision in run["threshold_decisions"]:
            interval = run["score_intervals"][held]
            threshold = decision["threshold"]
            expected = "inconclusive"
            if interval is not None:
                if interval["lower"] >= threshold:
                    expected = "go"
                elif interval["upper"] < threshold:
                    expected = "no_go"
            assert decision["decision"] == expected
            assert decision["full_decision"] == ("go" if full[held] >= threshold else "no_go")
            assert decision["point_decision"] == (
                "go" if run["estimated_scores"][held] >= threshold else "no_go"
            )
        for model in (held, "__all__"):
            errors[(run["strategy"], run["keep_ratio"], model)].append(error)
    for row in fidelity["summary"]:
        observed_errors = errors[(row["strategy"], row["keep_ratio"], row["held_out_model"])]
        assert math.isclose(statistics.mean(observed_errors), row["held_out_mae"], abs_tol=1e-12)
        assert max(observed_errors) == row["held_out_max_absolute_error"]
    paired_selections = (reports / "pair_selections.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(paired_selections) == len(fidelity["pair_transfer_runs"])
    pair_errors: dict[tuple[str, float, str], list[float]] = defaultdict(list)
    for line, run in zip(paired_selections, fidelity["pair_transfer_runs"], strict=True):
        selection = json.loads(line)
        a, b = selection["models"]
        assert not set((a, b)) & set(selection["reference_models"])
        assert set(selection["reference_models"]) == set(grades) - {a, b}
        for key in ("models", "reference_models", "strategy", "role", "keep_ratio", "seed"):
            assert selection[key] == run[key]
        members = audit_selection(selection, grades)
        estimate = sum(
            item["weight"] * (grades[a][item["index"]] - grades[b][item["index"]])
            for item in members
        )
        truth = sum(grades[a][i] - grades[b][i] for i in grades[a]) / 315
        assert math.isclose(estimate, run["estimated_difference"], abs_tol=1e-12)
        assert truth == run["full_difference"]
        interval = run["difference_interval"]
        conclusion = "inconclusive"
        if interval is not None:
            positive = {i: float(grades[a][i] > grades[b][i]) for i in grades[a]}
            negative = {i: float(grades[b][i] > grades[a][i]) for i in grades[a]}
            low_p, high_p = audit_bounds(members, positive, manifest["confidence"], families=2)
            low_n, high_n = audit_bounds(members, negative, manifest["confidence"], families=2)
            assert interval["lower"] == float(low_p - high_n)
            assert interval["upper"] == float(high_p - low_n)
            if interval["lower"] > 0:
                conclusion = "a_above_b"
            elif interval["upper"] < 0:
                conclusion = "b_above_a"
            elif interval["lower"] == interval["upper"] == 0:
                conclusion = "tie"
        assert run["conclusion"] == conclusion
        for pair in (" / ".join((a, b)), "__all__"):
            pair_errors[(run["strategy"], run["keep_ratio"], pair)].append(abs(estimate - truth))
    for row in fidelity["pair_transfer_summary"]:
        observed_errors = pair_errors[(row["strategy"], row["keep_ratio"], row["pair"])]
        assert math.isclose(statistics.mean(observed_errors), row["difference_mae"], abs_tol=1e-12)
    print(
        f"Audited {len(selections)} score and {len(paired_selections)} pair-transfer selections, "
        "exact intervals, decisions, summaries and hashes."
    )


if __name__ == "__main__":
    main()
