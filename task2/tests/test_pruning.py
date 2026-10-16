"""Public selector contracts: coverage, reproducibility and strict reference-only fitting."""

import math
from itertools import combinations

import pytest

from benchmark_reference.experiments import evaluate_experiment, ordering_fidelity
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import BASELINES, CANDIDATES, select_samples


def test_response_coverage_retains_opposite_disagreements_and_population_mass() -> None:
    # Eight tasks, four behavior patterns; the agreeing-pass stratum has five tasks.
    refs = {
        "a": {i: float(i != 0 and i != 2) for i in range(8)},
        "b": {i: float(i != 0 and i != 1) for i in range(8)},
    }
    selected = select_samples(refs, strategy="response_stratified", keep_ratio=0.5, seed=7)
    assert len(selected) == 4
    assert {item.index for item in selected} >= {0, 1, 2}
    assert sorted(item.weight for item in selected) == [0.125, 0.125, 0.125, 0.625]
    assert math.fsum(item.weight for item in selected) == 1


def test_experiment_keeps_target_grades_out_of_every_selected_fold() -> None:
    scores = {
        "a": dict(enumerate([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
        "b": dict(enumerate([0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
        "target": dict(enumerate([0.0] * 8)),
    }
    first = evaluate_experiment(scores, keep_ratios=(0.5,), seeds=(7,))
    scores["target"] = dict(enumerate([1.0] * 8))
    second = evaluate_experiment(scores, keep_ratios=(0.5,), seeds=(7,))
    for before, after in zip(first, second, strict=True):
        if before.held_out_model == "target":
            assert before.selection == after.selection
            assert before.reference_models == ("a", "b")
            assert before.estimates["target"] == 0
            assert after.estimates["target"] == 1


@pytest.mark.parametrize("strategy", CANDIDATES)
def test_selection_is_unique_order_independent_and_seeded(strategy: str) -> None:
    refs = {"a": dict.fromkeys(range(40), 1.0), "b": dict.fromkeys(range(40), 0.0)}
    selected = select_samples(refs, strategy=strategy, keep_ratio=0.21, seed=0)
    reordered = {
        model: dict(reversed(list(values.items()))) for model, values in reversed(refs.items())
    }
    assert selected == select_samples(reordered, strategy=strategy, keep_ratio=0.21, seed=0)
    assert len({item.index for item in selected}) == 9  # ceil(40 * .21)
    assert selected != select_samples(refs, strategy=strategy, keep_ratio=0.21, seed=1)


def test_weights_correct_for_rare_stratum_oversampling() -> None:
    scores = {
        "a": dict(enumerate([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
        "b": dict(enumerate([0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
        "target": dict(enumerate([0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
    }
    run = next(
        run
        for run in evaluate_experiment(scores, keep_ratios=(0.5,), seeds=(7,))
        if run.strategy == "response_stratified" and run.held_out_model == "target"
    )
    assert run.full_scores["target"] == 0.75
    assert run.estimates["target"] == 0.75
    assert run.raw_subset_means["target"] == 0.5


def test_difficulty_merges_opposite_disagreements_but_covers_pass_counts() -> None:
    refs = {
        "a": dict(enumerate([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
        "b": dict(enumerate([0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0])),
    }
    selected = select_samples(refs, strategy="difficulty_stratified", keep_ratio=0.375, seed=7)
    assert {item.stratum for item in selected} == {"passes:0/2", "passes:1/2", "passes:2/2"}
    assert sorted(item.weight for item in selected) == [0.125, 0.25, 0.625]
    with pytest.raises(AnalysisError, match="cannot cover 4"):
        select_samples(refs, strategy="response_stratified", keep_ratio=0.375, seed=7)


@pytest.mark.parametrize("strategy", BASELINES)
def test_trivial_baselines_are_unavailable_as_candidates(strategy: str) -> None:
    with pytest.raises(AnalysisError, match="Unknown candidate"):
        select_samples({"a": {0: 1.0}}, strategy=strategy, keep_ratio=1, seed=0)


@pytest.mark.parametrize("ratio", [0, -0.1, 1.01, float("nan"), float("inf"), True])
def test_invalid_ratios_fail(ratio: float) -> None:
    with pytest.raises(AnalysisError, match="keep_ratio"):
        select_samples({"a": {0: 1.0}}, strategy=CANDIDATES[0], keep_ratio=ratio, seed=0)


@pytest.mark.parametrize(
    "refs",
    [
        {},
        {"a": {}},
        {"a": {0: 1.0}, "b": {1: 1.0}},
        {"a": {-1: 1.0}},
        {"a": {0: 0.5}},
        {"a": {0: True}},
    ],
)
def test_invalid_reference_tables_fail(refs: dict[str, dict[int, float]]) -> None:
    with pytest.raises(AnalysisError):
        select_samples(refs, strategy=CANDIDATES[0], keep_ratio=1, seed=0)


def test_ordering_reports_reversals_and_created_ties() -> None:
    full = {"a": 0.9, "b": 0.8, "c": 0.7}
    reversed_order = ordering_fidelity(full, {"a": 0.7, "b": 0.8, "c": 0.9})
    assert reversed_order.discordant == 3
    assert reversed_order.kendall_tau_b == -1
    assert reversed_order.pair_agreement == 0
    created_tie = ordering_fidelity(full, {"a": 0.9, "b": 0.7, "c": 0.7})
    assert created_tie.concordant == 2
    assert created_tie.subset_only_ties == 1
    assert created_tie.pair_agreement == pytest.approx(2 / 3)
    assert created_tie.kendall_tau_b == pytest.approx(math.sqrt(2 / 3))


def test_unsampled_tasks_keep_uncertainty_even_when_every_observed_grade_is_zero() -> None:
    scores = {
        "a": dict.fromkeys(range(100), 1.0),
        "b": dict.fromkeys(range(100), 0.0),
        "target": dict.fromkeys(range(100), 0.0),
    }
    run = next(
        run
        for run in evaluate_experiment(scores, keep_ratios=(0.5,), seeds=(0,))
        if run.held_out_model == "target" and run.strategy == "response_stratified"
    )
    interval = run.score_intervals["target"]
    assert interval is not None
    # Exact hypergeometric inversion: 5/100 still permits observing zero in 50
    # with probability >= .025, while 6/100 does not. A Wald interval collapses.
    assert (interval.lower, interval.upper, interval.confidence) == (0, 0.05, 0.95)


def test_pair_transfer_excludes_both_compared_models_before_selection() -> None:
    from benchmark_reference.transfer import evaluate_pair_transfer

    scores = {
        "reference": dict.fromkeys(range(8), 1.0),
        "a": dict.fromkeys(range(8), 1.0),
        "b": dict.fromkeys(range(8), 0.0),
    }
    first = evaluate_pair_transfer(scores, keep_ratios=(0.75,), seeds=(0,))
    scores["a"] = dict.fromkeys(range(8), 0.0)
    scores["b"] = dict.fromkeys(range(8), 1.0)
    second = evaluate_pair_transfer(scores, keep_ratios=(0.75,), seeds=(0,))
    for before, after in zip(first, second, strict=True):
        if before.models == ("a", "b"):
            assert before.selection == after.selection
            assert before.reference_models == ("reference",)
            assert before.estimated_difference == 1
            assert after.estimated_difference == -1
            if before.difference_interval is not None:
                assert before.difference_interval.lower > 0
                assert after.difference_interval is not None
                assert after.difference_interval.upper < 0


def test_pair_intervals_measure_discordance_rather_than_individual_score_spread() -> None:
    from benchmark_reference.transfer import evaluate_pair_transfer

    scores = {
        "reference": dict.fromkeys(range(100), 1.0),
        "a": {i: float(i % 2) for i in range(100)},
        "b": {i: float(i % 2) for i in range(100)},
    }
    run = next(
        run
        for run in evaluate_pair_transfer(scores, keep_ratios=(0.5,), seeds=(0,))
        if run.models == ("a", "b") and run.strategy == "response_stratified"
    )
    assert run.difference_interval is not None
    # No sampled discordances in either direction. Bonferroni allocates .025
    # failure to each directional population count: at most 6/100 apiece.
    assert (run.difference_interval.lower, run.difference_interval.upper) == (-0.06, 0.06)


def test_pairwise_failure_budget_does_not_round_to_zero_at_high_confidence() -> None:
    from benchmark_reference.transfer import evaluate_pair_transfer

    confidence = math.nextafter(1.0, 0.0)
    scores = {
        "reference": dict.fromkeys(range(8), 1.0),
        "a": dict.fromkeys(range(8), 1.0),
        "b": dict.fromkeys(range(8), 0.0),
    }
    run = next(
        run
        for run in evaluate_pair_transfer(
            scores,
            keep_ratios=(0.75,),
            seeds=(0,),
            confidence=confidence,
        )
        if run.models == ("a", "b") and run.strategy == "response_stratified"
    )
    assert run.difference_interval is not None
    assert run.difference_interval.confidence == confidence
    assert run.difference_interval.lower <= 1 <= run.difference_interval.upper


def test_census_pair_interval_recovers_the_exact_net_success_difference() -> None:
    from benchmark_reference.transfer import evaluate_pair_transfer

    scores = {
        "reference": dict.fromkeys(range(315), 1.0),
        "a": {i: float(i < 3) for i in range(315)},
        "b": {i: float(i == 3) for i in range(315)},
    }
    run = next(
        run
        for run in evaluate_pair_transfer(scores, keep_ratios=(1,), seeds=(0,))
        if run.models == ("a", "b") and run.strategy == "response_stratified"
    )
    assert run.difference_interval is not None
    assert run.difference_interval.lower == run.difference_interval.upper == run.full_difference


@pytest.mark.parametrize("stratified", [False, True])
def test_reported_intervals_cover_every_small_population_of_binary_grades(stratified: bool) -> None:
    # Exhaust all placements of K successful tasks. For a fixed symmetric sampling
    # design this is equivalent to exhausting possible draws from a fixed K/N pool.
    # The truth and coverage probabilities come from combinatorial enumeration,
    # rather than reimplementing the interval algorithm.
    for successes in range(7):
        covered = total = 0
        for success_ids in combinations(range(6), successes):
            scores = {
                "a": {i: float(i < 3) if stratified else 1.0 for i in range(6)},
                "b": dict.fromkeys(range(6), 0.0),
                "target": {i: float(i in success_ids) for i in range(6)},
            }
            run = next(
                run
                for run in evaluate_experiment(scores, keep_ratios=(2 / 3,), seeds=(0,))
                if run.held_out_model == "target" and run.strategy == "response_stratified"
            )
            interval = run.score_intervals["target"]
            assert interval is not None
            covered += interval.lower <= successes / 6 <= interval.upper
            total += 1
        assert covered / total >= 0.95
