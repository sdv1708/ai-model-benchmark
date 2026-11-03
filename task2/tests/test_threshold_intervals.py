"""The four stage-1 interval methods at the public interval seam."""

from fractions import Fraction

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_intervals import (
    INTERVAL_METHODS,
    StratumCount,
    interval_bounds,
    stratum_counts,
)
from benchmark_reference.two_stage import select_stage1
from benchmark_reference.uncertainty import pooled_count_bounds, score_interval

ALPHA = Fraction(1, 20)


@pytest.mark.parametrize(
    ("method", "interior_only"),
    [("stratified_wilson", False), ("stratified_bootstrap_percentile", True)],
)
@pytest.mark.parametrize("sampled", [32, 63, 158])
def test_with_one_stratum_the_stratified_methods_agree_with_the_exact_interval(
    method: str, interior_only: bool, sampled: int
) -> None:
    # Stated tolerance: each bound is within 2 / n of the exact bound, the score of two
    # sampled questions. Wilson meets it at every observed score. The bootstrap meets it
    # for observed scores from 0.2 to 0.8 only. An all-pass or all-fail sample has no
    # bootstrap variance, so its bootstrap interval has width 0.
    population = 315
    tolerance = Fraction(2, sampled)
    for successes in range(sampled + 1):
        if interior_only and not 0.2 <= successes / sampled <= 0.8:
            continue
        low, high = pooled_count_bounds(population, sampled, successes, alpha=ALPHA)
        lower, upper = interval_bounds(
            method, [StratumCount(population, sampled, successes)], alpha=ALPHA
        )
        assert abs(lower - Fraction(low, population)) <= tolerance
        assert abs(upper - Fraction(high, population)) <= tolerance


@pytest.mark.parametrize("sampled", [5, 32, 63, 158])
def test_with_one_stratum_bonferroni_is_the_exact_interval(sampled: int) -> None:
    # With one stratum, alpha / H is alpha, so the tolerance is 0.
    for successes in range(sampled + 1):
        low, high = pooled_count_bounds(315, sampled, successes, alpha=ALPHA)
        assert interval_bounds(
            "stratified_bonferroni_hypergeometric",
            [StratumCount(315, sampled, successes)],
            alpha=ALPHA,
        ) == (Fraction(low, 315), Fraction(high, 315))


@pytest.mark.parametrize("method", INTERVAL_METHODS)
def test_a_census_gives_width_zero_at_the_full_set_score(method: str) -> None:
    strata = [StratumCount(40, 40, 13), StratumCount(25, 25, 25), StratumCount(3, 3, 0)]
    assert interval_bounds(method, strata, alpha=ALPHA) == (Fraction(38, 68), Fraction(38, 68))


@pytest.mark.parametrize("method", INTERVAL_METHODS)
def test_every_interval_stays_in_the_feasible_range(method: str) -> None:
    # The sampled passes are known, so the full-set count lies in
    # [sum(s_h), sum(N_h - n_h + s_h)]. Near-census strata test the clip.
    cases = [
        [StratumCount(10, 9, 9)],
        [StratumCount(10, 9, 0), StratumCount(50, 5, 3)],
        [StratumCount(80, 16, 7), StratumCount(90, 18, 9), StratumCount(70, 69, 40)],
        [StratumCount(315, 284, 150)],
    ]
    for strata in cases:
        lower, upper = interval_bounds(method, strata, alpha=ALPHA)
        population = sum(s.population for s in strata)
        floor = Fraction(sum(s.successes for s in strata), population)
        ceiling = Fraction(sum(s.population - s.sampled + s.successes for s in strata), population)
        assert floor <= lower <= upper <= ceiling


def test_bonferroni_matches_the_recorded_per_stratum_interval() -> None:
    references = {
        m: {i: float((i * (j + 2)) % 5 < 2) for i in range(60)} for j, m in enumerate("abc")
    }
    selection = select_stage1(references, stratifier="response_stratified", size=20, seed=4)
    grades = {i: float(i % 3 != 0) for i in range(60)}
    recorded = score_interval(
        selection, {s.index: grades[s.index] for s in selection}, confidence=0.95
    )
    lower, upper = interval_bounds(
        "stratified_bonferroni_hypergeometric", stratum_counts(selection, grades), alpha=ALPHA
    )
    assert (float(lower), float(upper)) == (recorded.lower, recorded.upper)


def test_wilson_with_a_large_stratum_is_the_textbook_wilson_interval() -> None:
    # Wilson 95% interval for 30 of 100: [0.2189, 0.3958]. One million questions make
    # the finite-population correction negligible.
    lower, upper = interval_bounds(
        "stratified_wilson", [StratumCount(1_000_000, 100, 30)], alpha=ALPHA
    )
    assert abs(float(lower) - 0.2189) < 1e-4
    assert abs(float(upper) - 0.3958) < 1e-4


def test_wilson_uses_the_kish_effective_sample_size_for_unequal_allocation() -> None:
    # Equal strata with 10 and 90 sampled: n_eff = 1 / (0.25 / 10 + 0.25 / 90) = 36,
    # not 100. Wilson for 0.5 with n = 36 is [0.3447, 0.6553].
    strata = [StratumCount(1_000_000, 10, 5), StratumCount(1_000_000, 90, 45)]
    lower, upper = interval_bounds("stratified_wilson", strata, alpha=ALPHA)
    assert abs(float(lower) - 0.3447) < 1e-4
    assert abs(float(upper) - 0.6553) < 1e-4


def test_wilson_narrows_with_the_finite_population_correction() -> None:
    # Half of a 126-question stratum: the variance factor is (126 - 63) / 125.
    corrected = interval_bounds("stratified_wilson", [StratumCount(126, 63, 30)], alpha=ALPHA)
    large = interval_bounds("stratified_wilson", [StratumCount(10**9, 63, 30)], alpha=ALPHA)
    assert corrected[1] - corrected[0] < 0.75 * (large[1] - large[0])


def test_the_bootstrap_interval_is_a_fixed_function_of_the_stratum_counts() -> None:
    strata = [StratumCount(80, 16, 7), StratumCount(90, 18, 9), StratumCount(70, 14, 12)]
    first = interval_bounds("stratified_bootstrap_percentile", strata, alpha=ALPHA)
    again = interval_bounds("stratified_bootstrap_percentile", strata[::-1], alpha=ALPHA)
    assert first == again
    assert first[0] < Fraction(28, 48) < first[1]


def test_unknown_methods_and_invalid_inputs_are_rejected() -> None:
    with pytest.raises(AnalysisError, match="Unknown interval method"):
        interval_bounds("normal", [StratumCount(10, 5, 2)], alpha=ALPHA)
    with pytest.raises(AnalysisError, match="alpha"):
        interval_bounds("stratified_wilson", [StratumCount(10, 5, 2)], alpha=Fraction(0))
    with pytest.raises(AnalysisError, match="stratum"):
        interval_bounds("stratified_wilson", [], alpha=ALPHA)
    with pytest.raises(AnalysisError, match="successes"):
        StratumCount(10, 5, 6)


def test_every_method_has_a_name() -> None:
    assert INTERVAL_METHODS == (
        "pooled_exact_hypergeometric",
        "stratified_bonferroni_hypergeometric",
        "stratified_wilson",
        "stratified_bootstrap_percentile",
    )


def test_a_selected_question_without_a_grade_is_rejected() -> None:
    references = {m: {i: float((i + j) % 4 == 0) for i in range(40)} for j, m in enumerate("abc")}
    selection = select_stage1(references, stratifier="difficulty_stratified", size=12, seed=0)
    grades = {item.index: 1.0 for item in selection[1:]}
    with pytest.raises(AnalysisError, match="no grade"):
        stratum_counts(selection, grades)


# AA-LCR strata can be small: the committed panel has strata of 2 and 3 questions,
# and a 12-question probe samples one question from each length x difficulty stratum.
# Worked example: a census of a one-question stratum with 1 pass, and one sampled
# question (a failure) from a stratum of 9. Exact bounds at alpha 0.05:
# - Pooled: N = 10, n = 2, 1 pass. P(X >= 1 | K = 1) = 1 - C(9,2)/C(10,2) = 0.2 and
#   P(X <= 1 | K = 9) = 1 - C(9,2)/C(10,2) = 0.2, both >= 0.025. So K is 1 to 9.
# - Bonferroni: the census stratum gives exactly 1 pass. The other gives 0 to 8 passes,
#   because P(X = 0 | K = 8) = 1/9 >= 0.0125 and P(X = 0 | K = 9) = 0. So K is 1 to 9.
# - Wilson: point 0.1, Kish size 1 / (0.9^2 * 8 / 8) = 1.2346. The lower bound 0.003
#   is below the floor 1/10 of the passes already seen, so the clip raises it to 0.1.
# - Bootstrap: no stratum has two sampled questions, so it adds no width.
SMALL_STRATA = [StratumCount(1, 1, 1), StratumCount(9, 1, 0)]


@pytest.mark.parametrize(
    ("method", "lower", "upper"),
    [
        ("pooled_exact_hypergeometric", Fraction(1, 10), Fraction(9, 10)),
        ("stratified_bonferroni_hypergeometric", Fraction(1, 10), Fraction(9, 10)),
        ("stratified_bootstrap_percentile", Fraction(1, 10), Fraction(1, 10)),
    ],
)
def test_strata_with_one_question_give_the_worked_exact_bounds(
    method: str, lower: Fraction, upper: Fraction
) -> None:
    assert interval_bounds(method, SMALL_STRATA, alpha=ALPHA) == (lower, upper)


def test_wilson_with_one_sampled_question_per_stratum_matches_the_worked_example() -> None:
    lower, upper = interval_bounds("stratified_wilson", SMALL_STRATA, alpha=ALPHA)
    assert lower == Fraction(1, 10)
    assert abs(float(upper) - 0.8024) < 1e-3


@pytest.mark.parametrize("method", INTERVAL_METHODS)
def test_a_probe_of_one_question_strata_is_a_census_with_width_zero(method: str) -> None:
    strata = [StratumCount(1, 1, 1), StratumCount(1, 1, 0), StratumCount(1, 1, 1)]
    assert interval_bounds(method, strata, alpha=ALPHA) == (Fraction(2, 3), Fraction(2, 3))
