"""One retrospective fidelity policy for both Part A benchmarks.

Held-out folds and independently excluded pairs gate selection. Reference-assisted
rankings are diagnostics only. Passing this policy is not deployment certification.
"""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from itertools import combinations, product
from typing import TypedDict

from benchmark_reference.experiments import ExperimentRun
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import BASELINES
from benchmark_reference.pruning_reporting import summarize_runs
from benchmark_reference.study_metrics import summarize_decisions, summarize_pair_transfer
from benchmark_reference.transfer import PairTransferRun
from benchmark_reference.uncertainty import validate_threshold


@dataclass(frozen=True, slots=True)
class FidelityPolicy:
    """Illustrative tolerances fixed before this ticket's new runs, after prior studies.

    Scores, widths and errors use 0..1 units. Fractions use all runs as denominator.
    Worst/minimum gates apply separately to every held-out model/pair/threshold.
    """

    worst_fold_mae: float = 0.03
    max_absolute_error: float = 0.08
    max_seed_score_std: float = 0.03
    max_mean_score_interval_width: float = 0.20
    min_score_interval_coverage: float = 0.95
    min_pair_interval_coverage: float = 0.95
    min_pair_order_agreement: float = 0.95
    min_pair_decisive_fraction: float = 0.80
    max_wrong_pair_fraction: float = 0.0
    min_threshold_point_agreement: float = 0.95
    min_threshold_decisive_fraction: float = 0.80
    max_false_threshold_fraction: float = 0.0


DEFAULT_POLICY = FidelityPolicy()


class FidelityPoint(TypedDict):
    strategy: str
    role: str
    keep_ratio: float
    realized_keep_ratio: float
    selected_count: int
    metrics: dict[str, float | None]
    failed_gates: list[str]


class SelectedPoint(FidelityPoint):
    status: str


class OperatingComparison(TypedDict):
    policy: dict[str, float]
    thresholds: list[float]
    points: list[FidelityPoint]
    selected: SelectedPoint | None
    score_folds: list[dict[str, object]]
    pair_folds: list[dict[str, object]]
    decision_folds: list[dict[str, object]]
    limitations: list[str]


LIMITATIONS = [
    "Retrospective illustrative policy, not a customer requirement or independent preregistration.",
    "Three models are a stress-test panel, not a random sample of future model families.",
    "Choosing methods/ratios on these folds reuses evaluation evidence; validate on fresh models.",
    "Intervals cover fixed recorded grades per run, not simultaneously after method/ratio search.",
    "Hash sampling approximates uniform sampling within fixed strata.",
    "Seed dispersion and Jaccard describe selection sensitivity, not independent model evidence.",
    "Reference-assisted whole-panel ordering is diagnostic and never a selection gate.",
    "AA-LCR judge variation is unmeasured; census removes sampling error, not judge error.",
    "No operating point here certifies deployment or supplies a calibrated unseen-model guarantee.",
    "Smallest means among tested candidate sizes only; baselines are never eligible.",
]


def _validate_panel(runs: Sequence[ExperimentRun], pairs: Sequence[PairTransferRun]) -> None:
    if not runs or not pairs:
        raise AnalysisError("Operating points require score and pair evidence")
    full = runs[0].full_scores
    models = set(full)
    methods = {(r.strategy, r.role) for r in runs}
    if len({name for name, _ in methods}) != len(methods) or any(
        role != ("comparison_baseline" if name in BASELINES else "candidate")
        for name, role in methods
    ):
        raise AnalysisError("Strategy roles must be unique; baseline names remain comparison-only")
    ratios = {r.keep_ratio for r in runs}
    seeds = {r.seed for r in runs}
    if len(models) < 3 or len(seeds) < 2:
        raise AnalysisError("Operating points require at least three models and two seeds")
    expected = set(product(methods, ratios, seeds, models))
    actual = [((r.strategy, r.role), r.keep_ratio, r.seed, r.held_out_model) for r in runs]
    pair_expected = set(product(methods, ratios, seeds, combinations(sorted(models), 2)))
    pair_actual = [((r.strategy, r.role), r.keep_ratio, r.seed, r.models) for r in pairs]
    if len(actual) != len(expected) or set(actual) != expected:
        raise AnalysisError("Score evidence must be a complete, unique, balanced panel")
    if len(pair_actual) != len(pair_expected) or set(pair_actual) != pair_expected:
        raise AnalysisError("Pair evidence must match the complete score panel")
    for run in runs:
        if (
            run.full_scores != full
            or run.population_count != runs[0].population_count
            or set(run.reference_models) != models - {run.held_out_model}
        ):
            raise AnalysisError("Score evidence has inconsistent population or target leakage")
    for pair in pairs:
        if not math.isclose(
            pair.full_difference, full[pair.models[0]] - full[pair.models[1]], abs_tol=1e-12
        ):
            raise AnalysisError("Pair full difference disagrees with score evidence")
        if pair.population_count != runs[0].population_count or set(
            pair.reference_models
        ) != models - set(pair.models):
            raise AnalysisError("Pair evidence has inconsistent population or target leakage")


def _extreme(
    rows: Sequence[dict[str, object]], field: str, *, minimum: bool = False
) -> float | None:
    values = [row[field] for row in rows]
    if not values or any(not isinstance(v, int | float) or not math.isfinite(v) for v in values):
        return None
    numbers = [float(v) for v in values if isinstance(v, int | float)]
    return min(numbers) if minimum else max(numbers)


def compare_operating_points(
    runs: Sequence[ExperimentRun],
    pair_runs: Sequence[PairTransferRun],
    *,
    thresholds: Sequence[float],
    policy: FidelityPolicy = DEFAULT_POLICY,
) -> OperatingComparison:
    """Compute identical gates for either benchmark; return every failure, not a best seed.

    The caller supplies explicit customer/example thresholds. Pooled averages cannot
    hide a failing fold. Missing uncertainty is a failure, and abstention never counts
    as a correct decision. Ties prefer smallest count, worst-fold MAE, then name.
    """
    if not thresholds or len(set(thresholds)) != len(thresholds):
        raise AnalysisError("Operating points require nonempty unique thresholds")
    for threshold in thresholds:
        validate_threshold(threshold)
    for name, limit in asdict(policy).items():
        if isinstance(limit, bool) or not math.isfinite(limit) or not 0 <= limit <= 1:
            raise AnalysisError(f"Invalid fidelity policy limit: {name}")
    _validate_panel(runs, pair_runs)
    score_rows = summarize_runs(runs)
    pair_rows = summarize_pair_transfer(pair_runs)
    decision_rows = summarize_decisions(runs, thresholds)
    points: list[FidelityPoint] = []
    for strategy, ratio in sorted({(r.strategy, r.keep_ratio) for r in runs}):
        group = [r for r in runs if r.strategy == strategy and r.keep_ratio == ratio]
        scores = [
            r
            for r in score_rows
            if r["strategy"] == strategy
            and r["keep_ratio"] == ratio
            and r["held_out_model"] != "__all__"
        ]
        pairs = [
            r
            for r in pair_rows
            if r["strategy"] == strategy and r["keep_ratio"] == ratio and r["pair"] != "__all__"
        ]
        decisions = [
            r
            for r in decision_rows
            if r["strategy"] == strategy
            and r["keep_ratio"] == ratio
            and r["held_out_model"] != "__all__"
        ]
        metrics = {
            "worst_fold_mae": _extreme(scores, "held_out_mae"),
            "max_absolute_error": _extreme(scores, "held_out_max_absolute_error"),
            "max_seed_score_std": _extreme(scores, "held_out_error_std"),
            "max_mean_score_interval_width": _extreme(scores, "mean_interval_width"),
            "min_score_interval_coverage": _extreme(
                scores, "held_out_interval_coverage", minimum=True
            ),
            "min_pair_order_agreement": _extreme(pairs, "pair_order_agreement", minimum=True),
            "min_pair_interval_coverage": _extreme(pairs, "interval_coverage", minimum=True),
            "min_pair_decisive_fraction": _extreme(pairs, "decisive_fraction", minimum=True),
            "max_wrong_pair_fraction": _extreme(pairs, "wrong_decisive_fraction"),
            "min_threshold_point_agreement": _extreme(
                decisions, "point_decision_agreement", minimum=True
            ),
            "min_threshold_decisive_fraction": _extreme(
                decisions, "decisive_fraction", minimum=True
            ),
            "max_false_threshold_fraction": _extreme(
                [
                    {
                        "false": (_extreme([r], "false_go_fraction") or 0)
                        + (_extreme([r], "false_no_go_fraction") or 0)
                    }
                    for r in decisions
                ],
                "false",
            ),
        }
        failures = []
        for name, limit in asdict(policy).items():
            value = metrics[name]
            if value is None or (
                value < limit - 1e-12 if name.startswith("min_") else value > limit + 1e-12
            ):
                failures.append(name)
        points.append(
            FidelityPoint(
                strategy=strategy,
                role=group[0].role,
                keep_ratio=ratio,
                realized_keep_ratio=len(group[0].selection) / group[0].population_count,
                selected_count=len(group[0].selection),
                metrics=metrics,
                failed_gates=failures,
            )
        )
    eligible = [p for p in points if p["role"] == "candidate" and not p["failed_gates"]]
    eligible.sort(
        key=lambda p: (
            p["selected_count"],
            p["metrics"]["worst_fold_mae"] or 0,
            p["strategy"],
            p["keep_ratio"],
        )
    )
    selected = None
    if eligible:
        chosen = eligible[0]
        selected = SelectedPoint(
            **chosen,
            status=(
                "full_reference_fallback"
                if chosen["realized_keep_ratio"] == 1
                else "provisional_recorded_grade_point"
            ),
        )
    return OperatingComparison(
        policy=asdict(policy),
        thresholds=sorted(thresholds),
        points=points,
        selected=selected,
        score_folds=score_rows,
        pair_folds=pair_rows,
        decision_folds=decision_rows,
        limitations=LIMITATIONS.copy(),
    )
