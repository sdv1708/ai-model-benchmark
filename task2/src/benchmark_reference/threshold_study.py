"""Run the two-stage policy on simulated models and summarize each true score.

Each true score gets ``len(seeds) * models_per_seed`` simulated models. The probe
for a selector seed depends on the reference panel only: the reference grades
and, for AA-LCR, the question metadata. It is therefore the same for every
simulated model that uses that seed. A wrong decision is a final
decision that differs from the decision on the simulated model's full set.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, SelectedSample, select_strata
from benchmark_reference.threshold_benchmarks import ReferencePanel
from benchmark_reference.threshold_policy import ThresholdPolicy
from benchmark_reference.threshold_simulation import SimulationGenerator, target_pass_count
from benchmark_reference.two_stage import (
    FinalDecision,
    TwoStageDecision,
    decide_two_stage,
    full_set_decision,
)
from benchmark_reference.uncertainty import clopper_pearson_upper


@dataclass(frozen=True, slots=True)
class SimulatedDecision:
    """One simulated model, its full-set truth, and the two-stage result."""

    true_score: str
    full_passes: int
    truth: FinalDecision
    selector_seed: int
    replicate: int
    model_seed: int
    result: TwoStageDecision

    @property
    def wrong(self) -> bool:
        return self.result.decision != self.truth


def _model_seed(simulation_seed: int, true_score: str, selector_seed: int, replicate: int) -> int:
    text = f"threshold-sim-v1:{simulation_seed}:{true_score}:{selector_seed}:{replicate}"
    return int.from_bytes(hashlib.sha256(text.encode("ascii")).digest()[:8], "big")


def score_labels(scores: Sequence[float], *, name: str) -> list[str]:
    """Two-decimal labels of ``scores``. Two scores must not share a label."""
    labels = [f"{score:.2f}" for score in scores]
    if len(set(labels)) != len(labels):
        raise AnalysisError(f"Policy {name} must differ at two decimal places")
    return labels


def true_score_labels(policy: ThresholdPolicy) -> list[str]:
    """The true scores of the decision study as two-decimal labels."""
    return score_labels(policy.true_scores, name="true_scores")


def check_benchmark(panel: ReferencePanel, policy: ThresholdPolicy) -> None:
    """Stop when the policy section is for another benchmark than the panel."""
    if policy.benchmark != panel.benchmark:
        raise AnalysisError(
            f"Policy section for benchmark {policy.benchmark!r} cannot run on the "
            f"{panel.benchmark!r} reference panel"
        )


def run_simulated_study(
    panel: ReferencePanel, policy: ThresholdPolicy
) -> tuple[SimulatedDecision, ...]:
    """Decide every simulated model in the policy grid; real grades are not used."""
    check_benchmark(panel, policy)
    references = panel.references
    generator = SimulationGenerator(references)
    population = len(generator.ids)
    labels = true_score_labels(policy)
    groups = panel.strata(policy.stratifier)
    probes: dict[int, tuple[SelectedSample, ...]] = {}

    def cached_probe(
        references: ReferenceScores, *, stratifier: str, size: int, seed: int
    ) -> tuple[SelectedSample, ...]:
        # The panel strata replace the reference-only strata of ``select_stage1``.
        if seed not in probes:
            probes[seed] = select_strata(groups, budget=size, seed=seed)
        return probes[seed]

    threshold = Fraction(str(policy.threshold))
    rows: list[SimulatedDecision] = []
    for score, label in zip(policy.true_scores, labels, strict=True):
        passes = target_pass_count(score, population)
        truth = full_set_decision(passes, population, threshold)
        for selector_seed in policy.seeds:
            for replicate in range(policy.models_per_seed):
                model_seed = _model_seed(policy.simulation_seed, label, selector_seed, replicate)
                grades = generator.draw(score, seed=model_seed)
                result = decide_two_stage(
                    references, grades, policy=policy, seed=selector_seed, selector=cached_probe
                )
                rows.append(
                    SimulatedDecision(
                        label, passes, truth, selector_seed, replicate, model_seed, result
                    )
                )
    return tuple(rows)


def summarize(rows: Sequence[SimulatedDecision], *, population: int) -> list[dict[str, Any]]:
    """One record per true score, in policy order."""
    groups: dict[str, list[SimulatedDecision]] = {}
    for row in rows:
        groups.setdefault(row.true_score, []).append(row)
    summary: list[dict[str, Any]] = []
    for label, members in groups.items():
        draws = len(members)
        counts: Mapping[str, int] = {
            name: sum(row.result.stage1_result == name for row in members)
            for name in ("GO", "NO GO", "ESCALATE")
        }
        decided = counts["GO"] + counts["NO GO"]
        wrong = sum(row.wrong for row in members)
        first = members[0]
        summary.append(
            {
                "true_score": label,
                "full_passes": first.full_passes,
                "full_score": first.full_passes / population,
                "truth": first.truth,
                "draws": draws,
                "stage1_go": counts["GO"],
                "stage1_no_go": counts["NO GO"],
                "escalate": counts["ESCALATE"],
                "decided_at_stage1": decided,
                "decisive_fraction": decided / draws,
                "wrong_decisions": wrong,
                "wrong_decision_rate": wrong / draws,
                # Rounded so that platform differences in lgamma cannot change bytes.
                "wrong_rate_upper95": round(clopper_pearson_upper(wrong, draws), 6),
                "mean_questions_graded": math.fsum(r.result.questions_graded for r in members)
                / draws,
            }
        )
    return summary
