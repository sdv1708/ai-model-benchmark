"""Decision policy at the agreed public analysis seam, using known synthetic grades."""

from dataclasses import replace

import pytest

from benchmark_reference.experiments import evaluate_experiment
from benchmark_reference.models import AnalysisError
from benchmark_reference.operating_points import FidelityPolicy, compare_operating_points
from benchmark_reference.transfer import evaluate_pair_transfer


def test_small_accurate_points_still_fall_back_when_intervals_cannot_decide() -> None:
    # All methods see a clear 100%, 0%, 50% ordering; four observations cannot
    # support precise intervals. A census has known exact scores and decisions.
    scores = {
        "a": dict.fromkeys(range(8), 1.0),
        "b": dict.fromkeys(range(8), 0.0),
        "c": {i: float(i % 2) for i in range(8)},
    }
    report = compare_operating_points(
        evaluate_experiment(scores, keep_ratios=(0.5, 1), seeds=(0, 1)),
        evaluate_pair_transfer(scores, keep_ratios=(0.5, 1), seeds=(0, 1)),
        thresholds=(0.75,),
    )
    assert report["selected"] is not None
    assert report["selected"]["selected_count"] == 8
    assert report["selected"]["status"] == "full_reference_fallback"
    assert report["selected"]["role"] == "candidate"
    candidate_half = next(
        p
        for p in report["points"]
        if p["strategy"] == "difficulty_stratified" and p["keep_ratio"] == 0.5
    )
    assert "max_mean_score_interval_width" in candidate_half["failed_gates"]
    census = next(
        p
        for p in report["points"]
        if p["strategy"] == "difficulty_stratified" and p["keep_ratio"] == 1
    )
    assert census["metrics"]["worst_fold_mae"] == 0
    assert census["metrics"]["min_threshold_decisive_fraction"] == 1
    assert census["failed_gates"] == []


def test_operating_point_rejects_pair_evidence_with_a_different_full_truth() -> None:
    scores = {
        "a": dict.fromkeys(range(8), 1.0),
        "b": dict.fromkeys(range(8), 0.0),
        "c": {i: float(i % 2) for i in range(8)},
    }
    runs = evaluate_experiment(scores, keep_ratios=(1,), seeds=(0, 1))
    pairs = evaluate_pair_transfer(scores, keep_ratios=(1,), seeds=(0, 1))
    corrupted = (replace(pairs[0], full_difference=0), *pairs[1:])
    with pytest.raises(AnalysisError, match="full difference"):
        compare_operating_points(runs, corrupted, thresholds=(0.75,))


def test_comparison_baseline_cannot_be_promoted_by_mislabeling_evidence() -> None:
    scores = {m: dict.fromkeys(range(8), 1.0) for m in ("a", "b", "c")}
    runs = evaluate_experiment(scores, keep_ratios=(1,), seeds=(0, 1))
    pairs = evaluate_pair_transfer(scores, keep_ratios=(1,), seeds=(0, 1))
    runs = tuple(
        replace(r, role="candidate") if r.strategy == "uniform_random" else r for r in runs
    )
    pairs = tuple(
        replace(r, role="candidate") if r.strategy == "uniform_random" else r for r in pairs
    )
    with pytest.raises(AnalysisError, match="baseline"):
        compare_operating_points(runs, pairs, thresholds=(0.75,))


def test_smaller_point_is_selected_for_an_explicitly_relaxed_exploratory_policy() -> None:
    scores = {m: dict.fromkeys(range(8), 1.0) for m in ("a", "b", "c")}
    report = compare_operating_points(
        evaluate_experiment(scores, keep_ratios=(0.5, 1), seeds=(0, 1)),
        evaluate_pair_transfer(scores, keep_ratios=(0.5, 1), seeds=(0, 1)),
        thresholds=(0.25,),
        policy=replace(
            FidelityPolicy(), max_mean_score_interval_width=1, min_pair_decisive_fraction=0
        ),
    )
    assert report["selected"] is not None
    assert report["selected"]["selected_count"] == 4
    assert report["selected"]["status"] == "provisional_recorded_grade_point"


def test_incomplete_pair_panel_cannot_hide_a_difficult_model_pair() -> None:
    scores = {m: dict.fromkeys(range(8), 1.0) for m in ("a", "b", "c")}
    runs = evaluate_experiment(scores, keep_ratios=(1,), seeds=(0, 1))
    pairs = evaluate_pair_transfer(scores, keep_ratios=(1,), seeds=(0, 1))
    with pytest.raises(AnalysisError, match="complete score panel"):
        compare_operating_points(runs, pairs[1:], thresholds=(0.75,))


def test_no_supported_point_is_distinct_from_selecting_a_comparison_baseline() -> None:
    scores = {
        "a": dict.fromkeys(range(8), 1.0),
        "b": dict.fromkeys(range(8), 0.0),
        "c": {i: float(i % 2) for i in range(8)},
    }
    report = compare_operating_points(
        evaluate_experiment(scores, keep_ratios=(0.5,), seeds=(0, 1)),
        evaluate_pair_transfer(scores, keep_ratios=(0.5,), seeds=(0, 1)),
        thresholds=(0.75,),
    )
    assert report["selected"] is None


@pytest.mark.parametrize("missing", ["score", "pair"])
def test_partial_missing_uncertainty_fails_instead_of_excluding_the_missing_run(
    missing: str,
) -> None:
    scores = {m: dict.fromkeys(range(8), 1.0) for m in ("a", "b", "c")}
    runs = evaluate_experiment(scores, keep_ratios=(1,), seeds=tuple(range(20)))
    pairs = evaluate_pair_transfer(scores, keep_ratios=(1,), seeds=tuple(range(20)))
    if missing == "score":
        runs = (replace(runs[0], score_intervals={**runs[0].score_intervals, "a": None}), *runs[1:])
        required_failure = "min_score_interval_coverage"
    else:
        pairs = (replace(pairs[0], difference_interval=None, conclusion="inconclusive"), *pairs[1:])
        required_failure = "min_pair_interval_coverage"
    report = compare_operating_points(runs, pairs, thresholds=(0.75,))
    broken = next(p for p in report["points"] if p["strategy"] == "difficulty_stratified")
    assert required_failure in broken["failed_gates"]
    assert report["selected"] is not None
    assert report["selected"]["strategy"] == "response_stratified"
