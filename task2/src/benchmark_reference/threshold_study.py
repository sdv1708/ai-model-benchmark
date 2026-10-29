"""Run the two-stage policy on simulated models and summarize each true score.

Each true score gets ``len(seeds) * models_per_seed`` simulated models. The probe
for a selector seed depends on reference grades only. It is therefore the same
for every simulated model that uses that seed. A wrong decision is a final
decision that differs from the decision on the simulated model's full set.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, SelectedSample, validate_references
from benchmark_reference.threshold_policy import ThresholdPolicy
from benchmark_reference.threshold_simulation import SimulationGenerator, target_pass_count
from benchmark_reference.two_stage import (
    FinalDecision,
    TwoStageDecision,
    decide_two_stage,
    full_set_decision,
    select_stage1,
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


@dataclass(frozen=True, slots=True)
class ReferencePanel:
    """Reference grades and the SHA-256 of the exact bytes they were parsed from."""

    references: ReferenceScores
    sha256: str


def load_reference_panel(path: Path, *, benchmark: str) -> ReferencePanel:
    """Read the committed reference panel; reject another benchmark or bad grades."""
    try:
        data = path.read_bytes()
        panel = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read reference panel {path}: {exc}") from exc
    if not isinstance(panel, dict) or panel.get("schema_version") != 1:
        raise AnalysisError(f"Reference panel {path} must have schema_version 1")
    provenance = panel.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("benchmark") != benchmark:
        raise AnalysisError(f"Reference panel {path} is not for policy benchmark {benchmark!r}")
    tasks = panel.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise AnalysisError(f"Reference panel {path} has no tasks")
    references: dict[str, dict[int, float]] = {}
    for task in tasks:
        index = task.get("index") if isinstance(task, dict) else None
        scores = task.get("scores") if isinstance(task, dict) else None
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(scores, dict):
            raise AnalysisError(f"Reference panel {path} has an invalid task")
        for model, score in scores.items():
            if index in references.setdefault(model, {}):
                raise AnalysisError(f"Reference panel {path} repeats task {index}")
            references[model][index] = score
    validate_references(references)
    grades = {
        model: {i: float(s) for i, s in scores.items()} for model, scores in references.items()
    }
    return ReferencePanel(grades, hashlib.sha256(data).hexdigest())


def _model_seed(simulation_seed: int, true_score: str, selector_seed: int, replicate: int) -> int:
    text = f"threshold-sim-v1:{simulation_seed}:{true_score}:{selector_seed}:{replicate}"
    return int.from_bytes(hashlib.sha256(text.encode("ascii")).digest()[:8], "big")


def run_simulated_study(
    references: ReferenceScores, policy: ThresholdPolicy
) -> tuple[SimulatedDecision, ...]:
    """Decide every simulated model in the policy grid; real grades are not used."""
    generator = SimulationGenerator(references)
    population = len(generator.ids)
    labels = [f"{score:.2f}" for score in policy.true_scores]
    if len(set(labels)) != len(labels):
        raise AnalysisError("Policy true_scores must differ at two decimal places")
    probes: dict[int, tuple[SelectedSample, ...]] = {}

    def cached_probe(
        references: ReferenceScores, *, stratifier: str, size: int, seed: int
    ) -> tuple[SelectedSample, ...]:
        if seed not in probes:
            probes[seed] = select_stage1(references, stratifier=stratifier, size=size, seed=seed)
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
