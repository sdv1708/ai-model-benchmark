"""Stage-1 intervals for the full-set score of a stratified probe.

Every method reads only the counts of each occupied stratum ``h``: its question
count ``N_h``, its sampled count ``n_h``, and the passes ``s_h`` among them. The
stratum share is ``W_h = N_h / N``.

- ``pooled_exact_hypergeometric`` ignores the strata. It inverts the exact
  hypergeometric test for all sampled questions as one simple random sample.
- ``stratified_bonferroni_hypergeometric`` gives each stratum an exact interval
  at ``alpha / H`` and adds the bounds. It adds the worst case of every stratum,
  so it is a conservative reference.
- ``stratified_wilson`` is the Wilson score interval for the stratified estimate.
  It uses the Kish effective sample size with the finite-population correction.
- ``stratified_bootstrap_percentile`` is the percentile interval of the Rao-Wu
  rescaling bootstrap. Its variance is the unbiased stratified variance with
  the finite-population correction.

The sampled passes are known, so the full-set pass count is at least
``sum(s_h)`` and at most ``sum(N_h - n_h + s_h)``. Each method clips its
interval to that feasible range. The clip never removes the true score, and a
census therefore gives width 0.
"""

import bisect
import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from statistics import NormalDist

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import SelectedSample
from benchmark_reference.uncertainty import pooled_count_bounds

POOLED_EXACT = "pooled_exact_hypergeometric"
BONFERRONI = "stratified_bonferroni_hypergeometric"
WILSON = "stratified_wilson"
BOOTSTRAP = "stratified_bootstrap_percentile"
INTERVAL_METHODS = (POOLED_EXACT, BONFERRONI, WILSON, BOOTSTRAP)
BOOTSTRAP_REPLICATES = 1999


@dataclass(frozen=True, slots=True, order=True)
class StratumCount:
    """One occupied stratum: ``successes`` passes among ``sampled`` of ``population``."""

    population: int
    sampled: int
    successes: int

    def __post_init__(self) -> None:
        if (
            any(type(v) is not int for v in (self.population, self.sampled, self.successes))
            or not 1 <= self.sampled <= self.population
            or not 0 <= self.successes <= self.sampled
        ):
            raise AnalysisError("A stratum needs 0 <= successes <= sampled <= population")


def stratum_counts(
    selection: Sequence[SelectedSample], grades: Mapping[int, float]
) -> tuple[StratumCount, ...]:
    """Counts for each stratum of a selection, in stratum-name order.

    ``grades`` must hold a binary grade for every selected question. The function
    does not read the grades of other questions.
    """
    groups: dict[str, list[SelectedSample]] = defaultdict(list)
    for item in selection:
        groups[item.stratum].append(item)
    if not groups or len({item.index for item in selection}) != len(selection):
        raise AnalysisError("Interval requires a nonempty selection of unique questions")
    counts: list[StratumCount] = []
    for key in sorted(groups):
        items = groups[key]
        first = items[0]
        if first.selected_count != len(items) or any(
            (item.population_count, item.selected_count)
            != (first.population_count, first.selected_count)
            for item in items
        ):
            raise AnalysisError(f"Stratum {key!r} counts are inconsistent")
        passes = 0
        for item in items:
            # One read for each grade: a membership test would read the grade twice.
            try:
                grade = grades[item.index]
            except KeyError:
                raise AnalysisError(f"Question {item.index} has no grade") from None
            if isinstance(grade, bool) or not isinstance(grade, int | float) or grade not in (0, 1):
                raise AnalysisError(f"Grade for question {item.index} must be binary")
            passes += int(grade)
        counts.append(StratumCount(first.population_count, first.selected_count, passes))
    return tuple(counts)


def interval_bounds(
    method: str, strata: Sequence[StratumCount], *, alpha: Fraction
) -> tuple[Fraction, Fraction]:
    """The ``1 - alpha`` interval for the full-set score, as exact fractions."""
    if method not in INTERVAL_METHODS:
        raise AnalysisError(f"Unknown interval method {method!r}; choose {INTERVAL_METHODS}")
    if not isinstance(alpha, Fraction) or not 0 < alpha < 1:
        raise AnalysisError("Interval alpha must be a fraction in (0, 1)")
    if not strata or any(not isinstance(s, StratumCount) for s in strata):
        raise AnalysisError("Interval requires at least one stratum count")
    # The sort makes the interval independent of the order of the strata.
    ordered = tuple(sorted(strata))
    population = sum(s.population for s in ordered)
    if method == POOLED_EXACT:
        low, high = pooled_count_bounds(
            population,
            sum(s.sampled for s in ordered),
            sum(s.successes for s in ordered),
            alpha=alpha,
        )
        lower, upper = Fraction(low, population), Fraction(high, population)
    elif method == BONFERRONI:
        bounds = [
            pooled_count_bounds(s.population, s.sampled, s.successes, alpha=alpha / len(ordered))
            for s in ordered
        ]
        lower = Fraction(sum(b[0] for b in bounds), population)
        upper = Fraction(sum(b[1] for b in bounds), population)
    elif method == WILSON:
        lower, upper = _wilson(ordered, alpha)
    else:
        lower, upper = _bootstrap(ordered, alpha)
    floor = Fraction(sum(s.successes for s in ordered), population)
    ceiling = Fraction(sum(s.population - s.sampled + s.successes for s in ordered), population)
    # Clip each bound into [floor, ceiling], so the clip also keeps lower <= upper.
    return min(max(lower, floor), ceiling), max(min(upper, ceiling), floor)


def estimate(strata: Sequence[StratumCount]) -> Fraction:
    """The stratified estimate: the sum of ``W_h * s_h / n_h``."""
    population = sum(s.population for s in strata)
    return sum((Fraction(s.population * s.successes, s.sampled) for s in strata), Fraction(0)) / (
        population
    )


def _wilson(strata: tuple[StratumCount, ...], alpha: Fraction) -> tuple[Fraction, Fraction]:
    point = estimate(strata)
    population = sum(s.population for s in strata)
    # Kish: n_eff = 1 / sum(W_h^2 / n_h), here with each term times the exact
    # without-replacement factor (N_h - n_h) / (N_h - 1). A census stratum adds 0.
    inverse = sum(
        (
            Fraction(s.population, population) ** 2
            * Fraction(s.population - s.sampled, (s.population - 1) * s.sampled)
            for s in strata
            if s.sampled < s.population
        ),
        Fraction(0),
    )
    if inverse == 0:
        return point, point
    n = 1 / float(inverse)
    p = float(point)
    z = NormalDist().inv_cdf(1 - float(alpha) / 2)
    scale = 1 + z * z / n
    center = (p + z * z / (2 * n)) / scale
    half = z / scale * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Fraction(max(0.0, center - half)), Fraction(min(1.0, center + half))


@lru_cache(maxsize=4096)
def _binomial_cdf(trials: int, successes: int, sampled: int) -> tuple[float, ...]:
    """CDF of Binomial(``trials``, ``successes / sampled``), from exact integers."""
    total = sampled**trials
    cumulative, cdf = 0, []
    for x in range(trials + 1):
        cumulative += math.comb(trials, x) * successes**x * (sampled - successes) ** (trials - x)
        cdf.append(cumulative / total)
    cdf[-1] = 1.0
    return tuple(cdf)


@lru_cache(maxsize=65536)
def _bootstrap(strata: tuple[StratumCount, ...], alpha: Fraction) -> tuple[Fraction, Fraction]:
    """Percentile bounds from ``BOOTSTRAP_REPLICATES`` Rao-Wu resamples.

    Each replicate draws ``m_h = n_h - 1`` questions with replacement from the
    sample of stratum ``h``. With ``x`` passes, the stratum mean becomes
    ``p_h + sqrt(1 - n_h / N_h) * (x / m_h - p_h)``. The replicate variance is
    then the unbiased estimate ``(1 - f_h) * s^2 / n_h``. A census stratum, a
    stratum with one sampled question, or an all-pass or all-fail sample keeps
    its mean. Such a stratum adds no width.

    The seed comes from the counts, so the interval is a fixed function of the
    data.
    """
    text = f"threshold-bootstrap-v2:{alpha}:" + ";".join(
        f"{s.population},{s.sampled},{s.successes}" for s in strata
    )
    rng = random.Random(int.from_bytes(hashlib.sha256(text.encode("ascii")).digest()[:8], "big"))
    draw = rng.random
    fixed = Fraction(0)
    columns: list[list[float]] = []
    for s in strata:
        mean = s.successes / s.sampled
        if s.sampled in (1, s.population) or s.successes in (0, s.sampled):
            fixed += Fraction(s.population * s.successes, s.sampled)
            continue
        trials = s.sampled - 1
        cdf = _binomial_cdf(trials, s.successes, s.sampled)
        scale = math.sqrt(1 - s.sampled / s.population)
        # Estimated passes in the stratum for each resampled pass count x.
        values = [s.population * (mean + scale * (x / trials - mean)) for x in range(trials + 1)]
        columns.append(
            [values[bisect.bisect_right(cdf, draw())] for _ in range(BOOTSTRAP_REPLICATES)]
        )
    population = sum(s.population for s in strata)
    if not columns:
        return fixed / population, fixed / population
    totals = sorted(map(sum, zip(*columns, strict=True)))
    rank = max(1, math.floor((BOOTSTRAP_REPLICATES + 1) * alpha / 2))
    return (
        (fixed + Fraction(totals[rank - 1])) / population,
        (fixed + Fraction(totals[BOOTSTRAP_REPLICATES - rank])) / population,
    )
