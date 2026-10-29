"""Two-stage threshold decision: a stratified probe, then a census when undecided.

Decision question: is the full-set score at or above threshold ``t``?

1. Select the stage-1 probe from reference grades only, then grade it.
2. Compute the pooled exact ``1 - alpha`` interval (95% at alpha 0.05).
3. Lower bound at or above ``t``: GO.
4. Upper bound below ``t``: NO GO.
5. Otherwise ESCALATE: grade the remaining questions and decide on the census.
   The census has no sampling error.

The selector receives reference grades only. It runs before any target grade is
read. Bounds stay exact fractions, so a boundary tie cannot flip on rounding.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, Protocol

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import (
    ReferenceScores,
    SelectedSample,
    reference_strata,
    select_strata,
    validate_references,
)
from benchmark_reference.threshold_policy import POOLED_EXACT, ThresholdPolicy, alpha_spending
from benchmark_reference.uncertainty import pooled_count_bounds

type Stage1Result = Literal["GO", "NO GO", "ESCALATE"]
type FinalDecision = Literal["GO", "NO GO"]


class Stage1Selector(Protocol):
    """Choose the stage-1 questions. Only reference grades are an input."""

    def __call__(
        self, references: ReferenceScores, *, stratifier: str, size: int, seed: int
    ) -> tuple[SelectedSample, ...]: ...


@dataclass(frozen=True, slots=True)
class TwoStageDecision:
    """Stage-1 evidence and the final decision. A census has equal final bounds."""

    stage1_size: int
    stage1_successes: int
    stage1_lower: Fraction
    stage1_upper: Fraction
    stage1_result: Stage1Result
    decision: FinalDecision
    decided_stage: int
    final_lower: Fraction
    final_upper: Fraction
    questions_graded: int


def select_stage1(
    references: ReferenceScores, *, stratifier: str, size: int, seed: int
) -> tuple[SelectedSample, ...]:
    """Stratified probe of exactly ``size`` questions from reference grades."""
    return select_strata(reference_strata(references, strategy=stratifier), budget=size, seed=seed)


def full_set_decision(passes: int, population: int, threshold: Fraction) -> FinalDecision:
    """The decision on the full set: the ground truth for one target."""
    return "GO" if Fraction(passes, population) >= threshold else "NO GO"


def _grade(target: Mapping[int, float], index: int) -> int:
    score = target[index]
    if isinstance(score, bool) or not isinstance(score, int | float) or score not in (0, 1):
        raise AnalysisError(f"Target grade for question {index} must be binary")
    return int(score)


def _classify(lower: Fraction, upper: Fraction, threshold: Fraction) -> Stage1Result:
    if lower >= threshold:
        return "GO"
    if upper < threshold:
        return "NO GO"
    return "ESCALATE"


def decide_two_stage(
    references: ReferenceScores,
    target: Mapping[int, float],
    *,
    policy: ThresholdPolicy,
    seed: int,
    selector: Stage1Selector = select_stage1,
) -> TwoStageDecision:
    """Apply the policy to one target; read only the grades each stage needs."""
    if policy.interval_method != POOLED_EXACT:
        raise AnalysisError(f"Unsupported interval method {policy.interval_method!r}")
    population = validate_references(references)
    if set(target) != set(population):
        raise AnalysisError("Target grades must cover exactly the reference questions")
    if policy.stage1_size > len(population):
        raise AnalysisError("Policy stage1_size exceeds the number of questions")
    selection = selector(
        references, stratifier=policy.stratifier, size=policy.stage1_size, seed=seed
    )
    chosen = [item.index for item in selection]
    if len(chosen) != policy.stage1_size or len(set(chosen)) != len(chosen):
        raise AnalysisError("Selector must return the policy stage1_size unique questions")
    if not set(chosen) <= set(population):
        raise AnalysisError("Selector returned questions outside the reference questions")
    threshold = Fraction(str(policy.threshold))
    alpha = Fraction(str(alpha_spending(policy)[0]))
    successes = sum(_grade(target, index) for index in chosen)
    low, high = pooled_count_bounds(len(population), len(chosen), successes, alpha=alpha)
    lower, upper = Fraction(low, len(population)), Fraction(high, len(population))
    result = _classify(lower, upper, threshold)
    if result != "ESCALATE":
        return TwoStageDecision(
            stage1_size=len(chosen),
            stage1_successes=successes,
            stage1_lower=lower,
            stage1_upper=upper,
            stage1_result=result,
            decision=result,
            decided_stage=1,
            final_lower=lower,
            final_upper=upper,
            questions_graded=len(chosen),
        )
    # Census: the remaining questions complete the full set, so the score is exact.
    chosen_set = set(chosen)
    total = successes + sum(_grade(target, i) for i in population if i not in chosen_set)
    score = Fraction(total, len(population))
    return TwoStageDecision(
        stage1_size=len(chosen),
        stage1_successes=successes,
        stage1_lower=lower,
        stage1_upper=upper,
        stage1_result=result,
        decision=full_set_decision(total, len(population), threshold),
        decided_stage=2,
        final_lower=score,
        final_upper=score,
        questions_graded=len(population),
    )
