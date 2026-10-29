"""Finite-population binary score intervals, requiring only sampled target grades.

Invert equal-tail hypergeometric tests with integer arithmetic. Bonferroni across
occupied strata gives a conservative confidence set for their population-weighted
mean under stratified simple random sampling without replacement. No Gaussian
approximation, estimated target variance, or unseen target grade is needed.
"""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Literal

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import SelectedSample

type Decision = Literal["go", "no_go", "inconclusive"]


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    lower: float
    upper: float
    confidence: float

    def decision(self, threshold: float) -> Decision:
        """GO means the full finite-population mean meets the supplied threshold."""
        validate_threshold(threshold)
        if self.lower >= threshold:
            return "go"
        if self.upper < threshold:
            return "no_go"
        return "inconclusive"


def validate_confidence(confidence: float) -> None:
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not math.isfinite(confidence)
        or not 0 < confidence < 1
    ):
        raise AnalysisError("confidence must be finite and in (0, 1)")


def validate_threshold(threshold: float) -> None:
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int | float)
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 1
    ):
        raise AnalysisError("thresholds must be finite and in [0, 1]")


@lru_cache(maxsize=32768)
def _count_bounds(
    population: int, sampled: int, successes: int, failure: Fraction
) -> tuple[int, int]:
    """First/last feasible population counts accepted by both one-sided tests."""
    cutoff = failure / 2
    denominator = math.comb(population, sampled)

    def accepted(count: int, *, upper_tail: bool) -> bool:
        low, high = max(0, sampled + count - population), min(sampled, count)
        if upper_tail:
            low = max(low, successes)
        else:
            high = min(high, successes)
        numerator = sum(
            math.comb(count, observed) * math.comb(population - count, sampled - observed)
            for observed in range(low, high + 1)
        )
        return numerator * cutoff.denominator >= denominator * cutoff.numerator

    # Tail probabilities are monotone in the unknown total number of successes.
    low, high = successes, population - sampled + successes
    while low < high:
        middle = (low + high) // 2
        if accepted(middle, upper_tail=True):
            high = middle
        else:
            low = middle + 1
    lower = low
    low, high = successes, population - sampled + successes
    while low < high:
        middle = (low + high + 1) // 2
        if accepted(middle, upper_tail=False):
            low = middle
        else:
            high = middle - 1
    return lower, low


def pooled_count_bounds(
    population: int, sampled: int, successes: int, *, alpha: Fraction
) -> tuple[int, int]:
    """Equal-tail exact hypergeometric bounds on the population success count.

    This pools every sampled question as one simple random sample, ignoring strata.
    A census (``sampled == population``) returns ``(successes, successes)``.
    """
    if (
        any(type(value) is not int for value in (population, sampled, successes))
        or not 1 <= sampled <= population
        or not 0 <= successes <= sampled
        or not 0 < alpha < 1
    ):
        raise AnalysisError("Pooled bounds require 0 <= successes <= sampled <= population")
    return _count_bounds(population, sampled, successes, alpha)


def clopper_pearson_upper(failures: int, trials: int, *, alpha: float = 0.05) -> float:
    """One-sided exact upper bound on a binomial rate: P(X <= failures | p) = alpha.

    The bound assumes independent trials.
    """
    if (
        type(failures) is not int
        or type(trials) is not int
        or not 0 <= failures <= trials
        or trials < 1
        or not 0 < alpha < 1
    ):
        raise AnalysisError("Binomial bounds require 0 <= failures <= trials and trials >= 1")
    if failures == trials:
        return 1.0

    def cdf(p: float) -> float:
        return math.fsum(
            math.exp(
                math.lgamma(trials + 1)
                - math.lgamma(k + 1)
                - math.lgamma(trials - k + 1)
                + k * math.log(p)
                + (trials - k) * math.log1p(-p)
            )
            for k in range(failures + 1)
        )

    # The binomial CDF falls as p rises, so bisection finds the unique root.
    low, high = 0.0, 1.0
    for _ in range(80):
        middle = (low + high) / 2
        if cdf(middle) > alpha:
            low = middle
        else:
            high = middle
    return high


def score_interval(
    selection: Sequence[SelectedSample], observed_grades: Mapping[int, float], *, confidence: float
) -> ConfidenceInterval:
    """Use selected grades only; callers must supply a probability sampling design.

    Valid for the two stratified candidates and uniform-random comparison, not
    deterministic easiest/hardest selection. Fixed hash seeds approximate random
    priorities; the nominal design guarantee assumes uniform within-stratum draws.
    It is per fixed model/design/budget, not simultaneous across a searched curve.
    """
    validate_confidence(confidence)
    lower, upper, population = _stratified_counts(
        selection, observed_grades, 1 - Fraction(str(confidence))
    )
    return ConfidenceInterval(lower / population, upper / population, confidence)


def _stratified_counts(
    selection: Sequence[SelectedSample], observed_grades: Mapping[int, float], failure: Fraction
) -> tuple[int, int, int]:
    ids = {item.index for item in selection}
    if not selection or len(ids) != len(selection) or set(observed_grades) != ids:
        raise AnalysisError("Interval requires unique selections and exactly their observed grades")
    groups: dict[str, list[SelectedSample]] = defaultdict(list)
    for item in selection:
        score = observed_grades[item.index]
        if isinstance(score, bool) or not isinstance(score, int | float) or score not in (0, 1):
            raise AnalysisError("Interval requires binary observed grades")
        groups[item.stratum].append(item)
    population = sum(items[0].population_count for items in groups.values())
    failure_per_group = failure / len(groups)
    lower = upper = 0
    for items in groups.values():
        first = items[0]
        if (
            type(first.population_count) is not int
            or type(first.selected_count) is not int
            or not 1 <= first.selected_count <= first.population_count
            or first.selected_count != len(items)
            or any(
                item.population_count != first.population_count
                or item.selected_count != first.selected_count
                for item in items
            )
        ):
            raise AnalysisError("Interval stratum counts are inconsistent")
        expected_weight = first.population_count / (population * first.selected_count)
        if any(not math.isclose(item.weight, expected_weight, rel_tol=1e-12) for item in items):
            raise AnalysisError("Interval requires population weights consistent with strata")
        bounds = _count_bounds(
            first.population_count,
            first.selected_count,
            sum(int(observed_grades[item.index]) for item in items),
            failure_per_group,
        )
        lower += bounds[0]
        upper += bounds[1]
    return lower, upper, population


def paired_difference_interval(
    selection: Sequence[SelectedSample],
    observed_a: Mapping[int, float],
    observed_b: Mapping[int, float],
    *,
    confidence: float,
) -> ConfidenceInterval:
    """Bound P(A passes,B fails) - P(B passes,A fails) on the same tasks.

    Common successes and common failures cancel in the paired difference. Use
    simultaneous exact bounds on the two directional discordance counts, rather
    than subtracting intervals for the individual model means. Bonferroni requires
    no independence between either the models or these mutually exclusive events.
    """
    validate_confidence(confidence)
    ids = {item.index for item in selection}
    if set(observed_a) != ids or set(observed_b) != ids:
        raise AnalysisError("Paired intervals require both models on exactly the selected tasks")
    for grades in (observed_a, observed_b):
        if any(
            isinstance(grade, bool) or not isinstance(grade, int | float) or grade not in (0, 1)
            for grade in grades.values()
        ):
            raise AnalysisError("Paired intervals require binary observed grades")
    failure_per_direction = (1 - Fraction(str(confidence))) / 2
    positive = _stratified_counts(
        selection,
        {i: float(observed_a[i] > observed_b[i]) for i in ids},
        failure_per_direction,
    )
    negative = _stratified_counts(
        selection,
        {i: float(observed_b[i] > observed_a[i]) for i in ids},
        failure_per_direction,
    )
    return ConfidenceInterval(
        (positive[0] - negative[1]) / positive[2],
        (positive[1] - negative[0]) / positive[2],
        confidence,
    )
