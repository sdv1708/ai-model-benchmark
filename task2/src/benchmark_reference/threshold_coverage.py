"""Coverage study: how often each interval method holds the full-set score.

A cell is one stratifier, one stage size, and one true score. The study runs
every stratifier of the benchmark of the reference panel. Each cell has
``coverage_subsets`` draws. A draw is a new simulated model and a new
stratified subset, so the draws are independent and a coverage count is
binomial. Every interval method sees the same draws.

A method covers a draw when its interval holds the simulated model's full-set
score. A method passes a cell when its coverage is at least the pass line: the
nominal coverage minus 3 standard errors, rounded to 3 decimals. For 2,000
draws at 95%, the pass line is 0.935. The study uses simulated models only.

With a cost model, each method also gets the expected token cost of a cell. A
draw that the method decides at stage 1 costs the tokens of its subset. A draw
that it escalates costs the tokens of the full set.

Every cell has its own seeds. Worker processes can therefore run the cells in
any order, and the result is the same for every worker count.
"""

import hashlib
import math
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import select_strata
from benchmark_reference.threshold_benchmarks import ReferencePanel
from benchmark_reference.threshold_cost import CostModel, Estimates
from benchmark_reference.threshold_intervals import (
    INTERVAL_METHODS,
    interval_bounds,
    stratum_counts,
)
from benchmark_reference.threshold_policy import ThresholdPolicy
from benchmark_reference.threshold_simulation import SimulationGenerator, target_pass_count
from benchmark_reference.threshold_study import check_benchmark, true_score_labels
from benchmark_reference.two_stage import classify_stage1

type CellKey = tuple[str, int, float, str]


@dataclass(frozen=True, slots=True)
class CoverageCell:
    """Coverage of one method in one cell. Misses are split by side.

    ``escalated`` counts the draws whose interval holds the threshold.
    ``expected`` is the mean tokens of a draw, or None without a cost model.
    """

    stratifier: str
    stage_size: int
    true_score: str
    full_passes: int
    method: str
    subsets: int
    covered: int
    truth_below: int
    truth_above: int
    mean_width: float
    escalated: int
    expected: Estimates | None

    @property
    def coverage(self) -> float:
        return self.covered / self.subsets


def coverage_pass_line(subsets: int, *, alpha: float) -> Fraction:
    """Nominal coverage minus 3 binomial standard errors, rounded to 3 decimals."""
    nominal = 1 - alpha
    line = nominal - 3 * math.sqrt(nominal * alpha / subsets)
    return Fraction(round(line * 1000), 1000)


def _seeds(
    simulation_seed: int, stratifier: str, size: int, true_score: str, replicate: int
) -> tuple[int, int]:
    text = f"threshold-coverage-v1:{simulation_seed}:{stratifier}:{size}:{true_score}:{replicate}"
    digest = hashlib.sha256(text.encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")


class _CellRunner:
    """Run the draws of one cell. The constructor builds the generator and strata once."""

    def __init__(
        self, panel: ReferencePanel, policy: ThresholdPolicy, costs: CostModel | None
    ) -> None:
        self.generator = SimulationGenerator(panel.references)
        self.groups = {s: panel.strata(s) for s in panel.stratifiers}
        self.policy = policy
        self.alpha = Fraction(str(policy.alpha))
        self.threshold = Fraction(str(policy.threshold))
        self.costs = costs

    def __call__(self, key: CellKey) -> tuple[CoverageCell, ...]:
        stratifier, size, score, label = key
        policy, population = self.policy, len(self.generator.ids)
        passes = target_pass_count(score, population)
        truth = Fraction(passes, population)
        covered = dict.fromkeys(INTERVAL_METHODS, 0)
        below = dict.fromkeys(INTERVAL_METHODS, 0)
        above = dict.fromkeys(INTERVAL_METHODS, 0)
        width = dict.fromkeys(INTERVAL_METHODS, Fraction(0))
        escalated = dict.fromkeys(INTERVAL_METHODS, 0)
        # Low, mean, and high subset tokens, summed over the draws decided at stage 1.
        decided = dict.fromkeys(INTERVAL_METHODS, Estimates.zero())
        for replicate in range(policy.coverage_subsets):
            model_seed, selector_seed = _seeds(
                policy.simulation_seed, stratifier, size, label, replicate
            )
            grades = self.generator.draw(score, seed=model_seed)
            selection = select_strata(self.groups[stratifier], budget=size, seed=selector_seed)
            counts = stratum_counts(selection, grades)
            subset = None
            if self.costs is not None:
                subset = self.costs.tokens(item.index for item in selection)
            for method in INTERVAL_METHODS:
                lower, upper = interval_bounds(method, counts, alpha=self.alpha)
                width[method] += upper - lower
                if classify_stage1(lower, upper, self.threshold) == "ESCALATE":
                    escalated[method] += 1
                elif subset is not None:
                    decided[method] += subset
                if truth < lower:
                    below[method] += 1
                elif truth > upper:
                    above[method] += 1
                else:
                    covered[method] += 1
        return tuple(
            CoverageCell(
                stratifier,
                size,
                label,
                passes,
                method,
                policy.coverage_subsets,
                covered[method],
                below[method],
                above[method],
                float(width[method] / policy.coverage_subsets),
                escalated[method],
                self._expected(decided[method], escalated[method]),
            )
            for method in INTERVAL_METHODS
        )

    def _expected(self, decided: Estimates, escalated: int) -> Estimates | None:
        if self.costs is None:
            return None
        total = decided + self.costs.full.scale(escalated)
        return total.scale(Fraction(1, self.policy.coverage_subsets))


_WORKER_RUNNER: _CellRunner | None = None


def _start_worker(panel: ReferencePanel, policy: ThresholdPolicy, costs: CostModel | None) -> None:
    global _WORKER_RUNNER
    _WORKER_RUNNER = _CellRunner(panel, policy, costs)


def _run_in_worker(key: CellKey) -> tuple[CoverageCell, ...]:
    if _WORKER_RUNNER is None:
        raise AnalysisError("Coverage worker was not started")
    return _WORKER_RUNNER(key)


def run_coverage_study(
    panel: ReferencePanel,
    policy: ThresholdPolicy,
    *,
    costs: CostModel | None = None,
    workers: int = 1,
) -> tuple[CoverageCell, ...]:
    """Run every method in every cell: each panel stratifier, stage size, and true score."""
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise AnalysisError("Coverage workers must be an integer of at least 1")
    check_benchmark(panel, policy)
    population = len(panel.questions)
    if policy.coverage_stage_sizes[-1] > population:
        raise AnalysisError(
            f"Coverage stage size {policy.coverage_stage_sizes[-1]} exceeds the "
            f"{population} questions"
        )
    labels = true_score_labels(policy)
    keys = [
        (stratifier, size, score, label)
        for stratifier in panel.stratifiers
        for size in policy.coverage_stage_sizes
        for score, label in zip(policy.true_scores, labels, strict=True)
    ]
    if workers == 1:
        runner = _CellRunner(panel, policy, costs)
        return tuple(cell for key in keys for cell in runner(key))
    with ProcessPoolExecutor(
        max_workers=min(workers, len(keys)),
        initializer=_start_worker,
        initargs=(panel, policy, costs),
    ) as pool:
        return tuple(cell for cells in pool.map(_run_in_worker, keys) for cell in cells)


def _cost_fraction(cell: CoverageCell, full: Estimates | None) -> dict[str, float] | None:
    if cell.expected is None or full is None:
        return None
    return cell.expected.ratio(full).rounded(6)


def _mean_cost(records: Sequence[dict[str, Any]]) -> float | None:
    """Mean of the mean-estimate cost fraction, each true score with equal weight."""
    fractions = [r["expected_cost_fraction"] for r in records]
    if not fractions or any(f is None for f in fractions):
        return None
    return round(math.fsum(f["mean"] for f in fractions) / len(fractions), 6)


def summarize_coverage(
    cells: Sequence[CoverageCell],
    *,
    subsets: int,
    alpha: float,
    full_tokens: Estimates | None = None,
) -> dict[str, Any]:
    """Summarize each cell, each method in each setting, and each method overall.

    A setting is one stratifier and one stage size. A method passes a setting
    when it passes every true score. The summary rounds widths to 6 decimals. As
    a result, platform differences in the last bit of a bound cannot change the
    bytes. With ``full_tokens``, each cell also gets its expected cost as a
    fraction of one full run.
    """
    line = coverage_pass_line(subsets, alpha=alpha)

    def passes(cell: CoverageCell) -> bool:
        return cell.covered * line.denominator >= line.numerator * cell.subsets

    records = [
        {
            "stratifier": c.stratifier,
            "stage_size": c.stage_size,
            "true_score": c.true_score,
            "full_passes": c.full_passes,
            "method": c.method,
            "subsets": c.subsets,
            "covered": c.covered,
            "coverage": c.coverage,
            "truth_below_interval": c.truth_below,
            "truth_above_interval": c.truth_above,
            "mean_width": round(c.mean_width, 6),
            "passes": passes(c),
            "escalated": c.escalated,
            "expected_cost_fraction": _cost_fraction(c, full_tokens),
        }
        for c in cells
    ]
    by_key: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for c, record in zip(cells, records, strict=True):
        by_key.setdefault((c.stratifier, c.stage_size, c.method), []).append(record)
    # Stratifiers keep the order of the cells, which is the order of the panel.
    stratifiers = list(dict.fromkeys(c.stratifier for c in cells))
    keys = sorted(
        {(c.stratifier, c.stage_size, c.method) for c in cells},
        key=lambda k: (stratifiers.index(k[0]), k[1], INTERVAL_METHODS.index(k[2])),
    )
    groups: list[dict[str, Any]] = []
    for stratifier, size, method in keys:
        members = [
            c for c in cells if (c.stratifier, c.stage_size, c.method) == (stratifier, size, method)
        ]
        lowest = min(members, key=lambda c: (c.covered, c.true_score))
        groups.append(
            {
                "method": method,
                "stratifier": stratifier,
                "stage_size": size,
                "min_coverage": lowest.coverage,
                "min_coverage_true_score": lowest.true_score,
                "failing_true_scores": [c.true_score for c in members if not passes(c)],
                "passes": all(passes(c) for c in members),
                "mean_width": round(math.fsum(c.mean_width for c in members) / len(members), 6),
                "mean_expected_cost_fraction": _mean_cost(by_key[(stratifier, size, method)]),
            }
        )
    methods = []
    for method in INTERVAL_METHODS:
        mine = [c for c in cells if c.method == method]
        if not mine:
            continue
        methods.append(
            {
                "method": method,
                "passes_every_cell": all(passes(c) for c in mine),
                "cells_failed": sum(not passes(c) for c in mine),
                "cells": len(mine),
                "min_coverage": min(c.coverage for c in mine),
                "mean_width": round(math.fsum(c.mean_width for c in mine) / len(mine), 6),
            }
        )
    return {
        "subsets_per_cell": subsets,
        "nominal_coverage": 1 - alpha,
        "pass_line": float(line),
        "methods": methods,
        "groups": groups,
        "cells": records,
    }
