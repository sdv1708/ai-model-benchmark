"""Error-rate study: wrong decisions of the stage-1 probe, and the distance to decide.

The study answers two questions. How often does the probe decide wrong? How far
from the threshold must a model be for the probe to decide?

A cell is one generator, one stratifier, one stage size, and one true score. Each
cell has ``error_draws`` draws. A draw is a new simulated model and a new
stratified subset, so the draws in a cell are independent and a count is
binomial. Every interval method sees the same draws.

Two generators make the simulated models:

- ``rasch`` draws a Rasch-style model from the reference difficulty
  (``SimulationGenerator``).
- ``reference_flip`` starts from the real grades of one reference model and flips
  random grades until the pass count reaches the chosen score
  (``FlipGenerator``). Draw ``r`` of a cell starts from reference model
  ``r mod M`` in name order, so each reference model gets an equal share.

Only stage 1 can decide wrong, because the census has no sampling error. A GO
at stage 1 is wrong when the full-set score is below the threshold. A NO GO at
stage 1 is wrong when the full-set score is at or above the threshold. A setting
is one generator, stratifier, stage size, and method. A setting passes when its
wrong-decision rate is at most the pass line at every true score. The pass line
is alpha plus 3 binomial standard errors, rounded to 3 decimals. For 1,000 draws
at alpha 0.05, it is 0.071.

The distance to decide is d95. Take the grid true scores at distance ``d`` or
more from the threshold. d95 is the smallest ``d`` at which the probe decides at
stage 1 in at least 95% of the draws at each of these true scores. Each side of
the threshold gets its own d95. The full-set truth sets the side of a true
score: GO is above, NO GO is below. A side that does not reach 95% at its
farthest true score has no d95. The d95 of a setting is the larger of the two
sides.

The seeds of a draw depend on the generator, the true score, and the draw
number only. All stratifiers and stage sizes therefore see the same simulated
models and the same selection seeds, so a comparison of two settings is paired.
Worker processes can run the cells in any order, and the result is the same for
every worker count.
"""

import hashlib
import math
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, select_strata
from benchmark_reference.threshold_benchmarks import ReferencePanel
from benchmark_reference.threshold_cost import CostModel, Estimates
from benchmark_reference.threshold_intervals import (
    INTERVAL_METHODS,
    interval_bounds,
    stratum_counts,
)
from benchmark_reference.threshold_policy import ThresholdPolicy
from benchmark_reference.threshold_simulation import (
    FlipGenerator,
    SimulationGenerator,
    target_pass_count,
)
from benchmark_reference.threshold_study import check_benchmark, score_labels
from benchmark_reference.two_stage import FinalDecision, classify_stage1, full_set_decision

RASCH = "rasch"
FLIP = "reference_flip"
GENERATORS = (RASCH, FLIP)
DECIDE_LEVEL = Fraction(95, 100)

type ErrorKey = tuple[str, str, int, float, str]


@dataclass(frozen=True, slots=True)
class ErrorRateCell:
    """Stage-1 results of one method in one cell.

    ``expected`` is the mean tokens of a draw, or None without a cost model. A
    draw that stage 1 decides costs its subset; an escalated draw costs a full run.
    """

    generator: str
    stratifier: str
    stage_size: int
    true_score: str
    full_passes: int
    truth: FinalDecision
    method: str
    draws: int
    stage1_go: int
    stage1_no_go: int
    escalated: int
    expected: Estimates | None

    @property
    def decided(self) -> int:
        return self.stage1_go + self.stage1_no_go

    @property
    def wrong(self) -> int:
        return self.stage1_no_go if self.truth == "GO" else self.stage1_go


def error_rate_pass_line(draws: int, *, alpha: float) -> Fraction:
    """Alpha plus 3 binomial standard errors, rounded to 3 decimals."""
    line = alpha + 3 * math.sqrt(alpha * (1 - alpha) / draws)
    return Fraction(round(line * 1000), 1000)


class Generators:
    """Both generators on one reference panel."""

    def __init__(self, references: ReferenceScores) -> None:
        self.rasch = SimulationGenerator(references)
        self.flip = FlipGenerator(references)

    def draw(
        self, generator: str, true_score: float, *, seed: int, replicate: int
    ) -> dict[int, float]:
        """Grades of one simulated model. A flip draw rotates through the reference models."""
        if generator == RASCH:
            return self.rasch.draw(true_score, seed=seed)
        if generator == FLIP:
            base = self.flip.models[replicate % len(self.flip.models)]
            return self.flip.draw(true_score, seed=seed, base=base)
        raise AnalysisError(f"Unknown generator {generator!r}; choose one of {GENERATORS}")


def _seeds(simulation_seed: int, generator: str, label: str, replicate: int) -> tuple[int, int]:
    """The model seed and the selection seed of one draw.

    The stratifier and the stage size are not inputs, so every setting gets the
    same draws: common random numbers for the comparison of settings.
    """
    text = f"threshold-error-v2:{simulation_seed}:{generator}:{label}:{replicate}"
    digest = hashlib.sha256(text.encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")


class _CellRunner:
    """Run the draws of one cell. The constructor builds the generators and strata once."""

    def __init__(
        self, panel: ReferencePanel, policy: ThresholdPolicy, costs: CostModel | None
    ) -> None:
        self.generators = Generators(panel.references)
        self.groups = {s: panel.strata(s) for s in panel.stratifiers}
        self.policy = policy
        self.population = len(panel.questions)
        self.alpha = Fraction(str(policy.alpha))
        self.threshold = Fraction(str(policy.threshold))
        self.costs = costs

    def __call__(self, key: ErrorKey) -> tuple[ErrorRateCell, ...]:
        generator, stratifier, size, score, label = key
        draws = self.policy.error_draws
        passes = target_pass_count(score, self.population)
        truth = full_set_decision(passes, self.population, self.threshold)
        go = dict.fromkeys(INTERVAL_METHODS, 0)
        no_go = dict.fromkeys(INTERVAL_METHODS, 0)
        # Low, mean, and high subset tokens, summed over the draws decided at stage 1.
        decided = dict.fromkeys(INTERVAL_METHODS, Estimates.zero())
        for replicate in range(draws):
            model_seed, selector_seed = _seeds(
                self.policy.simulation_seed, generator, label, replicate
            )
            grades = self.generators.draw(generator, score, seed=model_seed, replicate=replicate)
            selection = select_strata(self.groups[stratifier], budget=size, seed=selector_seed)
            counts = stratum_counts(selection, grades)
            subset = None
            if self.costs is not None:
                subset = self.costs.tokens(item.index for item in selection)
            for method in INTERVAL_METHODS:
                lower, upper = interval_bounds(method, counts, alpha=self.alpha)
                result = classify_stage1(lower, upper, self.threshold)
                if result == "ESCALATE":
                    continue
                if result == "GO":
                    go[method] += 1
                else:
                    no_go[method] += 1
                if subset is not None:
                    decided[method] += subset
        cells = []
        for method in INTERVAL_METHODS:
            escalated = draws - go[method] - no_go[method]
            cells.append(
                ErrorRateCell(
                    generator=generator,
                    stratifier=stratifier,
                    stage_size=size,
                    true_score=label,
                    full_passes=passes,
                    truth=truth,
                    method=method,
                    draws=draws,
                    stage1_go=go[method],
                    stage1_no_go=no_go[method],
                    escalated=escalated,
                    expected=self._expected(decided[method], escalated),
                )
            )
        return tuple(cells)

    def _expected(self, decided: Estimates, escalated: int) -> Estimates | None:
        if self.costs is None:
            return None
        total = decided + self.costs.full.scale(escalated)
        return total.scale(Fraction(1, self.policy.error_draws))


_WORKER_RUNNER: _CellRunner | None = None


def _start_worker(panel: ReferencePanel, policy: ThresholdPolicy, costs: CostModel | None) -> None:
    global _WORKER_RUNNER
    _WORKER_RUNNER = _CellRunner(panel, policy, costs)


def _run_in_worker(key: ErrorKey) -> tuple[ErrorRateCell, ...]:
    if _WORKER_RUNNER is None:
        raise AnalysisError("Error-rate worker was not started")
    return _WORKER_RUNNER(key)


def run_error_rate_study(
    panel: ReferencePanel,
    policy: ThresholdPolicy,
    *,
    costs: CostModel | None = None,
    workers: int = 1,
) -> tuple[ErrorRateCell, ...]:
    """Every method in every cell: each generator, panel stratifier, stage size, and true score."""
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise AnalysisError("Error-rate workers must be an integer of at least 1")
    check_benchmark(panel, policy)
    population = len(panel.questions)
    if policy.error_stage_sizes[-1] > population:
        raise AnalysisError(
            f"Error-rate stage size {policy.error_stage_sizes[-1]} exceeds the "
            f"{population} questions"
        )
    labels = score_labels(policy.error_true_scores, name="error_rate true_scores")
    keys = [
        (generator, stratifier, size, score, label)
        for generator in GENERATORS
        for stratifier in panel.stratifiers
        for size in policy.error_stage_sizes
        for score, label in zip(policy.error_true_scores, labels, strict=True)
    ]
    if workers == 1:
        runner = _CellRunner(panel, policy, costs)
        return tuple(cell for key in keys for cell in runner(key))
    with ProcessPoolExecutor(
        max_workers=min(workers, len(keys)),
        initializer=_start_worker,
        initargs=(panel, policy, costs),
    ) as pool:
        # Large chunks keep the pickling cost small next to the work of each cell.
        chunk = max(1, len(keys) // (4 * workers))
        return tuple(
            cell for cells in pool.map(_run_in_worker, keys, chunksize=chunk) for cell in cells
        )


def distance_to_decide(
    points: Sequence[tuple[Fraction, Fraction]], *, level: Fraction = DECIDE_LEVEL
) -> dict[str, Fraction | None]:
    """d95 below the threshold, at or above it, and for both sides.

    ``points`` holds, for each true score, its signed distance from the
    threshold and its share decided at stage 1. A negative distance is below the
    threshold. A distance of 0 is on the side at or above the threshold.
    """

    def side(distances: list[tuple[Fraction, Fraction]]) -> Fraction | None:
        # Walk from the farthest point inward. The distance is the last point
        # before the first point that fails the level.
        found: Fraction | None = None
        for distance, share in sorted(distances, reverse=True):
            if share < level:
                break
            found = distance
        return found

    below = side([(-d, share) for d, share in points if d < 0])
    above = side([(d, share) for d, share in points if d >= 0])
    both = None if below is None or above is None else max(below, above)
    return {"below": below, "above": above, "both": both}


def _as_float(value: Fraction | None) -> float | None:
    return None if value is None else float(value)


def _signed_distance(cell: ErrorRateCell, threshold: Fraction) -> Fraction:
    """Distance of the grid true score from the threshold, with the side of the truth.

    The truth sets the side, so a GO model is never on the side below the threshold.
    """
    distance = abs(Fraction(cell.true_score) - threshold)
    return distance if cell.truth == "GO" else -distance


def _cost_fraction(cell: ErrorRateCell, full: Estimates | None) -> dict[str, float] | None:
    if cell.expected is None or full is None:
        return None
    return cell.expected.ratio(full).rounded(6)


def summarize_error_rate(
    cells: Sequence[ErrorRateCell],
    *,
    threshold: float,
    draws: int,
    alpha: float,
    full_tokens: Estimates | None = None,
) -> dict[str, Any]:
    """Summarize each cell, each setting, and each setting across both generators.

    A setting is one generator, stratifier, stage size, and method. A combined
    setting drops the generator: it passes when it passes for every generator,
    and its d95 is the largest d95 of the generators.
    """
    line = error_rate_pass_line(draws, alpha=alpha)
    limit = Fraction(str(threshold))

    def passes(cell: ErrorRateCell) -> bool:
        return cell.wrong * line.denominator <= line.numerator * cell.draws

    records: list[dict[str, Any]] = [
        {
            "generator": c.generator,
            "stratifier": c.stratifier,
            "stage_size": c.stage_size,
            "true_score": c.true_score,
            "full_passes": c.full_passes,
            "truth": c.truth,
            "method": c.method,
            "draws": c.draws,
            "stage1_go": c.stage1_go,
            "stage1_no_go": c.stage1_no_go,
            "escalated": c.escalated,
            "decided_share": round(c.decided / c.draws, 6),
            "wrong": c.wrong,
            "wrong_rate": round(c.wrong / c.draws, 6),
            "passes": passes(c),
            "expected_cost_fraction": _cost_fraction(c, full_tokens),
        }
        for c in cells
    ]
    groups: dict[tuple[str, str, int, str], list[ErrorRateCell]] = {}
    costs: dict[tuple[str, str, int, str], list[dict[str, float] | None]] = {}
    for c, record in zip(cells, records, strict=True):
        key = (c.generator, c.stratifier, c.stage_size, c.method)
        groups.setdefault(key, []).append(c)
        costs.setdefault(key, []).append(record["expected_cost_fraction"])
    settings: list[dict[str, Any]] = []
    for key, members in groups.items():
        generator, stratifier, size, method = key
        worst = max(members, key=lambda c: (Fraction(c.wrong, c.draws), c.true_score))
        distance = distance_to_decide(
            [(_signed_distance(c, limit), Fraction(c.decided, c.draws)) for c in members]
        )
        fractions = costs[key]
        mean_cost = (
            None
            if any(f is None for f in fractions)
            else round(math.fsum(f["mean"] for f in fractions if f) / len(fractions), 6)
        )
        settings.append(
            {
                "generator": generator,
                "stratifier": stratifier,
                "stage_size": size,
                "method": method,
                "true_scores": len(members),
                "passes": all(passes(c) for c in members),
                "failing_true_scores": [c.true_score for c in members if not passes(c)],
                "max_wrong_rate": round(worst.wrong / worst.draws, 6),
                "max_wrong_rate_true_score": worst.true_score,
                "wrong": sum(c.wrong for c in members),
                "draws": sum(c.draws for c in members),
                "decided_share": round(
                    sum(c.decided for c in members) / sum(c.draws for c in members), 6
                ),
                "d95_below": _as_float(distance["below"]),
                "d95_above": _as_float(distance["above"]),
                "d95": _as_float(distance["both"]),
                # Each true score of the grid has equal weight: a uniform prior on the grid.
                "mean_expected_cost_fraction": mean_cost,
            }
        )
    combined: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for setting in settings:
        key3 = (setting["stratifier"], setting["stage_size"], setting["method"])
        combined.setdefault(key3, []).append(setting)
    both: list[dict[str, Any]] = []
    for (stratifier, size, method), members3 in combined.items():
        both.append(
            {
                "stratifier": stratifier,
                "stage_size": size,
                "method": method,
                "generators": [m["generator"] for m in members3],
                "passes_both_generators": all(m["passes"] for m in members3),
                "failing_generators": [m["generator"] for m in members3 if not m["passes"]],
                "max_wrong_rate": max(m["max_wrong_rate"] for m in members3),
                "d95_by_generator": {m["generator"]: m["d95"] for m in members3},
                "d95_below": _largest(m["d95_below"] for m in members3),
                "d95_above": _largest(m["d95_above"] for m in members3),
                "d95": _largest(m["d95"] for m in members3),
                "decided_share_by_generator": {
                    m["generator"]: m["decided_share"] for m in members3
                },
                "mean_expected_cost_fraction_by_generator": {
                    m["generator"]: m["mean_expected_cost_fraction"] for m in members3
                },
            }
        )
    return {
        "generators": sorted({c.generator for c in cells}, key=GENERATORS.index),
        "draws_per_cell": draws,
        "alpha": alpha,
        "pass_line": float(line),
        "decide_level": float(DECIDE_LEVEL),
        "threshold": threshold,
        "settings": settings,
        "combined": both,
        "cells": records,
    }


def _largest(values: Iterable[float | None]) -> float | None:
    """The largest distance, or None when any generator has no distance."""
    found = list(values)
    return None if any(v is None for v in found) else max(v for v in found if v is not None)
