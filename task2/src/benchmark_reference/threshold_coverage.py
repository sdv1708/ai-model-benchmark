"""Coverage study: how often each interval method holds the full-set score.

A cell is one stratifier, one stage size, and one true score. Each cell has
``coverage_subsets`` draws. A draw is a new simulated model and a new
stratified subset, so the draws are independent and a coverage count is
binomial. Every interval method sees the same draws.

A method covers a draw when its interval holds the simulated model's full-set
score. A method passes a cell when its coverage is at least the pass line: the
nominal coverage minus 3 standard errors, rounded to 3 decimals. For 2,000
draws at 95%, the pass line is 0.935. The study uses simulated models only.

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
from benchmark_reference.pruning import (
    CANDIDATES,
    ReferenceScores,
    reference_strata,
    select_strata,
    validate_references,
)
from benchmark_reference.threshold_intervals import (
    INTERVAL_METHODS,
    interval_bounds,
    stratum_counts,
)
from benchmark_reference.threshold_policy import ThresholdPolicy
from benchmark_reference.threshold_simulation import SimulationGenerator, target_pass_count
from benchmark_reference.threshold_study import true_score_labels

type CellKey = tuple[str, int, float, str]


@dataclass(frozen=True, slots=True)
class CoverageCell:
    """Coverage of one method in one cell. Misses are split by side."""

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

    def __init__(self, references: ReferenceScores, policy: ThresholdPolicy) -> None:
        self.generator = SimulationGenerator(references)
        self.groups = {s: reference_strata(references, strategy=s) for s in CANDIDATES}
        self.policy = policy
        self.alpha = Fraction(str(policy.alpha))

    def __call__(self, key: CellKey) -> tuple[CoverageCell, ...]:
        stratifier, size, score, label = key
        policy, population = self.policy, len(self.generator.ids)
        passes = target_pass_count(score, population)
        truth = Fraction(passes, population)
        covered = dict.fromkeys(INTERVAL_METHODS, 0)
        below = dict.fromkeys(INTERVAL_METHODS, 0)
        above = dict.fromkeys(INTERVAL_METHODS, 0)
        width = dict.fromkeys(INTERVAL_METHODS, Fraction(0))
        for replicate in range(policy.coverage_subsets):
            model_seed, selector_seed = _seeds(
                policy.simulation_seed, stratifier, size, label, replicate
            )
            grades = self.generator.draw(score, seed=model_seed)
            selection = select_strata(self.groups[stratifier], budget=size, seed=selector_seed)
            counts = stratum_counts(selection, grades)
            for method in INTERVAL_METHODS:
                lower, upper = interval_bounds(method, counts, alpha=self.alpha)
                width[method] += upper - lower
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
            )
            for method in INTERVAL_METHODS
        )


_WORKER_RUNNER: _CellRunner | None = None


def _start_worker(references: ReferenceScores, policy: ThresholdPolicy) -> None:
    global _WORKER_RUNNER
    _WORKER_RUNNER = _CellRunner(references, policy)


def _run_in_worker(key: CellKey) -> tuple[CoverageCell, ...]:
    if _WORKER_RUNNER is None:
        raise AnalysisError("Coverage worker was not started")
    return _WORKER_RUNNER(key)


def run_coverage_study(
    references: ReferenceScores, policy: ThresholdPolicy, *, workers: int = 1
) -> tuple[CoverageCell, ...]:
    """Run every method in every cell: each stratifier, stage size, and true score."""
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise AnalysisError("Coverage workers must be an integer of at least 1")
    population = len(validate_references(references))
    if policy.coverage_stage_sizes[-1] > population:
        raise AnalysisError(
            f"Coverage stage size {policy.coverage_stage_sizes[-1]} exceeds the "
            f"{population} questions"
        )
    labels = true_score_labels(policy)
    keys = [
        (stratifier, size, score, label)
        for stratifier in CANDIDATES
        for size in policy.coverage_stage_sizes
        for score, label in zip(policy.true_scores, labels, strict=True)
    ]
    if workers == 1:
        runner = _CellRunner(references, policy)
        return tuple(cell for key in keys for cell in runner(key))
    plain = {model: dict(scores) for model, scores in references.items()}
    with ProcessPoolExecutor(
        max_workers=min(workers, len(keys)),
        initializer=_start_worker,
        initargs=(plain, policy),
    ) as pool:
        return tuple(cell for cells in pool.map(_run_in_worker, keys) for cell in cells)


def summarize_coverage(
    cells: Sequence[CoverageCell], *, subsets: int, alpha: float
) -> dict[str, Any]:
    """Summarize each cell, each method in each setting, and each method overall.

    A setting is one stratifier and one stage size. A method passes a setting
    when it passes every true score. The summary rounds widths to 6 decimals. As
    a result, platform differences in the last bit of a bound cannot change the
    bytes.
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
        }
        for c in cells
    ]
    keys = sorted(
        {(c.stratifier, c.stage_size, c.method) for c in cells},
        key=lambda k: (CANDIDATES.index(k[0]), k[1], INTERVAL_METHODS.index(k[2])),
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
