"""Decision and transfer summaries; keep abstention separate from correctness."""

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from benchmark_reference.experiments import ExperimentRun
from benchmark_reference.transfer import PairTransferRun
from benchmark_reference.uncertainty import Decision


@dataclass(frozen=True, slots=True)
class ThresholdDecision:
    threshold: float
    decision: Decision
    full_decision: Decision
    point_decision: Decision


def threshold_decisions(run: ExperimentRun, thresholds: Sequence[float]) -> list[ThresholdDecision]:
    interval = run.score_intervals[run.held_out_model]
    return [
        ThresholdDecision(
            threshold,
            interval.decision(threshold) if interval else "inconclusive",
            "go" if run.full_scores[run.held_out_model] >= threshold else "no_go",
            "go" if run.estimates[run.held_out_model] >= threshold else "no_go",
        )
        for threshold in sorted(thresholds)
    ]


def summarize_decisions(
    runs: Sequence[ExperimentRun], thresholds: Sequence[float]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float, str, float], list[ThresholdDecision]] = defaultdict(list)
    for run in runs:
        for decision in threshold_decisions(run, thresholds):
            for model in (run.held_out_model, "__all__"):
                grouped[(run.strategy, run.keep_ratio, model, decision.threshold)].append(decision)
    return [
        {
            "strategy": strategy,
            "keep_ratio": ratio,
            "held_out_model": model,
            "threshold": threshold,
            "run_count": len(decisions),
            "decisive_fraction": statistics.mean(d.decision != "inconclusive" for d in decisions),
            "false_go_fraction": statistics.mean(
                d.decision == "go" and d.full_decision == "no_go" for d in decisions
            ),
            "false_no_go_fraction": statistics.mean(
                d.decision == "no_go" and d.full_decision == "go" for d in decisions
            ),
            "point_decision_agreement": statistics.mean(
                d.point_decision == d.full_decision for d in decisions
            ),
        }
        for (strategy, ratio, model, threshold), decisions in sorted(grouped.items())
    ]


def summarize_pair_transfer(runs: Sequence[PairTransferRun]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float, str], list[PairTransferRun]] = defaultdict(list)
    for run in runs:
        for pair in (" / ".join(run.models), "__all__"):
            grouped[(run.strategy, run.keep_ratio, pair)].append(run)
    rows: list[dict[str, object]] = []
    for (strategy, ratio, pair), group in sorted(grouped.items()):
        bounded = [run for run in group if run.difference_interval is not None]
        decisive = [run for run in group if run.conclusion != "inconclusive"]
        wrong_decisions = sum(
            (run.conclusion == "a_above_b" and run.full_difference <= 0)
            or (run.conclusion == "b_above_a" and run.full_difference >= 0)
            or (run.conclusion == "tie" and abs(run.full_difference) > 1e-12)
            for run in decisive
        )
        rows.append(
            {
                "strategy": strategy,
                "role": group[0].role,
                "keep_ratio": ratio,
                "pair": pair,
                "selected_count": len(group[0].selection),
                "run_count": len(group),
                "difference_mae": statistics.mean(
                    abs(run.estimated_difference - run.full_difference) for run in group
                ),
                "pair_order_agreement": statistics.mean(run.relation_preserved for run in group),
                "interval_count": len(bounded),
                "interval_coverage": statistics.mean(
                    run.difference_interval.lower - 1e-12
                    <= run.full_difference
                    <= run.difference_interval.upper + 1e-12
                    for run in bounded
                    if run.difference_interval is not None
                )
                if bounded
                else None,
                "mean_interval_width": statistics.mean(
                    run.difference_interval.upper - run.difference_interval.lower
                    for run in bounded
                    if run.difference_interval is not None
                )
                if bounded
                else None,
                "decisive_fraction": len(decisive) / len(group),
                "wrong_decisive_fraction": wrong_decisions / len(group),
            }
        )
    return rows
