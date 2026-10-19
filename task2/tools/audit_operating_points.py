"""Independently reconstruct policy gates from saved runs; imports no pipeline code.

Run the raw-data auditors too: this checks the additional issue #17 decision layer.
Use normal Python, without -O (assertions are the audit checks).
"""

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def audit(reports: Path) -> None:
    manifest = json.loads((reports / "manifest.json").read_text())
    report = json.loads((reports / "operating_points.json").read_text())
    assert manifest["production_certified"] is False
    assert report["plan"]["policy"] == manifest["policy"]
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((reports / name).read_bytes()).hexdigest() == expected, name
    code = Path(__file__).resolve().parents[1] / "src/benchmark_reference"
    for name, expected in manifest["implementation_sha256"].items():
        assert (
            hashlib.sha256((code / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            == expected
        ), name
    curves = list(csv.DictReader((reports / "curves.csv").open(newline="")))
    points_checked = 0
    for benchmark, comparison in report["benchmarks"].items():
        fidelity = json.loads((reports / benchmark / "fidelity.json").read_text())
        score_groups: dict[tuple[str, float, str], list[Any]] = defaultdict(list)
        pair_groups: dict[tuple[str, float, tuple[str, ...]], list[Any]] = defaultdict(list)
        for run in fidelity["runs"]:
            score_groups[(run["strategy"], run["keep_ratio"], run["held_out_model"])].append(run)
        for run in fidelity["pair_transfer_runs"]:
            pair_groups[(run["strategy"], run["keep_ratio"], tuple(run["models"]))].append(run)
        for point in comparison["points"]:
            metrics: dict[str, list[float | None]] = defaultdict(list)
            for (strategy, ratio, model), group in score_groups.items():
                if (strategy, ratio) != (point["strategy"], point["keep_ratio"]):
                    continue
                signed = [r["estimated_scores"][model] - r["full_scores"][model] for r in group]
                metrics["worst_fold_mae"].append(statistics.mean(map(abs, signed)))
                metrics["max_absolute_error"].append(max(map(abs, signed)))
                metrics["max_seed_score_std"].append(statistics.stdev(signed))
                intervals = [r["score_intervals"][model] for r in group]
                bounded = all(i is not None for i in intervals)
                metrics["max_mean_score_interval_width"].append(
                    statistics.mean(i["upper"] - i["lower"] for i in intervals) if bounded else None
                )
                metrics["min_score_interval_coverage"].append(
                    statistics.mean(
                        r["score_intervals"][model]["lower"] - 1e-12
                        <= r["full_scores"][model]
                        <= r["score_intervals"][model]["upper"] + 1e-12
                        for r in group
                    )
                    if bounded
                    else None
                )
                for threshold in comparison["thresholds"]:
                    correct = decisive = false = 0
                    for run in group:
                        truth = run["full_scores"][model] >= threshold
                        correct += (run["estimated_scores"][model] >= threshold) == truth
                        interval = run["score_intervals"][model]
                        decision = None
                        if interval:
                            assert interval["confidence"] == 0.95
                            if interval["lower"] >= threshold:
                                decision = True
                            elif interval["upper"] < threshold:
                                decision = False
                        decisive += decision is not None
                        false += decision is not None and decision != truth
                    metrics["min_threshold_point_agreement"].append(correct / len(group))
                    metrics["min_threshold_decisive_fraction"].append(decisive / len(group))
                    metrics["max_false_threshold_fraction"].append(false / len(group))
            for (strategy, ratio, _), group in pair_groups.items():
                if (strategy, ratio) != (point["strategy"], point["keep_ratio"]):
                    continue

                def sign(value: float) -> int:
                    return 0 if abs(value) <= 1e-12 else (1 if value > 0 else -1)

                metrics["min_pair_order_agreement"].append(
                    statistics.mean(
                        sign(r["full_difference"]) == sign(r["estimated_difference"]) for r in group
                    )
                )
                metrics["min_pair_decisive_fraction"].append(
                    statistics.mean(r["conclusion"] != "inconclusive" for r in group)
                )
                metrics["max_wrong_pair_fraction"].append(
                    statistics.mean(
                        (r["conclusion"] == "a_above_b" and r["full_difference"] <= 0)
                        or (r["conclusion"] == "b_above_a" and r["full_difference"] >= 0)
                        or (r["conclusion"] == "tie" and abs(r["full_difference"]) > 1e-12)
                        for r in group
                    )
                )
                intervals = [r["difference_interval"] for r in group]
                metrics["min_pair_interval_coverage"].append(
                    statistics.mean(
                        r["difference_interval"]["lower"] - 1e-12
                        <= r["full_difference"]
                        <= r["difference_interval"]["upper"] + 1e-12
                        for r in group
                    )
                    if all(i is not None for i in intervals)
                    else None
                )
            failures = []
            for name, limit in manifest["policy"].items():
                values = metrics[name]
                value = (
                    None
                    if any(v is None for v in values)
                    else (
                        min(v for v in values if v is not None)
                        if name.startswith("min_")
                        else max(v for v in values if v is not None)
                    )
                )
                recorded = point["metrics"][name]
                assert value is recorded is None or (
                    value is not None
                    and recorded is not None
                    and math.isclose(value, recorded, abs_tol=1e-12)
                ), (benchmark, point, name)
                if value is None or (
                    value < limit - 1e-12 if name.startswith("min_") else value > limit + 1e-12
                ):
                    failures.append(name)
            assert set(failures) == set(point["failed_gates"])
            curve = next(
                r
                for r in curves
                if r["benchmark"] == benchmark
                and r["strategy"] == point["strategy"]
                and float(r["keep_ratio"]) == point["keep_ratio"]
            )
            assert set(filter(None, curve["failed_gates"].split(";"))) == set(failures)
            assert curve["eligible"] == str(point["role"] == "candidate" and not failures)
            points_checked += 1
        eligible = sorted(
            (p for p in comparison["points"] if p["role"] == "candidate" and not p["failed_gates"]),
            key=lambda p: (
                p["selected_count"],
                p["metrics"]["worst_fold_mae"],
                p["strategy"],
                p["keep_ratio"],
            ),
        )
        selected = comparison["selected"]
        if not eligible:
            assert selected is None
        else:
            assert {k: v for k, v in selected.items() if k != "status"} == eligible[0]
    print(
        f"Independently audited {points_checked} fidelity points, all gates, selections and hashes."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    audit(parser.parse_args().reports)
