"""The interval coverage study on simulated models."""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import CANDIDATES
from benchmark_reference.threshold_coverage import (
    coverage_pass_line,
    run_coverage_study,
    summarize_coverage,
)
from benchmark_reference.threshold_intervals import INTERVAL_METHODS
from benchmark_reference.threshold_policy import ThresholdPolicy, load_policy

DRAFT = load_policy(Path(__file__).parents[1] / "policies" / "lcb-threshold-draft.json").policy
REFERENCES = {
    m: {i: float((i * (j + 2)) % 7 < 3 + j) for i in range(60)} for j, m in enumerate("abc")
}


def _policy(**changes: object) -> ThresholdPolicy:
    return replace(DRAFT, **changes)  # type: ignore[arg-type]


SMALL = _policy(true_scores=(0.3, 0.6, 0.9), coverage_subsets=40, coverage_stage_sizes=(12, 30))


def test_pass_line_is_nominal_coverage_minus_three_standard_errors() -> None:
    # 0.95 - 3 * sqrt(0.95 * 0.05 / 2000) = 0.93538, stated as 0.935.
    assert coverage_pass_line(2000, alpha=0.05) == Fraction(935, 1000)
    # 0.95 - 3 * sqrt(0.95 * 0.05 / 100) = 0.88462.
    assert coverage_pass_line(100, alpha=0.05) == Fraction(885, 1000)


def test_study_draws_the_policy_subsets_for_every_cell_and_method() -> None:
    cells = run_coverage_study(REFERENCES, SMALL)
    keys = {(c.stratifier, c.stage_size, c.true_score, c.method) for c in cells}
    assert len(keys) == len(cells) == len(CANDIDATES) * 2 * 3 * len(INTERVAL_METHODS)
    assert {c.stratifier for c in cells} == set(CANDIDATES)
    assert {c.true_score for c in cells} == {"0.30", "0.60", "0.90"}
    for cell in cells:
        assert cell.subsets == 40
        assert cell.covered + cell.truth_below + cell.truth_above == 40
        assert 0 <= cell.mean_width <= 1
    # 54 of 60 is the smallest full-set count at or above 0.90.
    assert {c.full_passes for c in cells if c.true_score == "0.90"} == {54}


def test_methods_in_one_cell_see_the_same_subsets() -> None:
    cells = run_coverage_study(REFERENCES, SMALL)
    widths = {(c.stratifier, c.stage_size, c.true_score, c.method): c.mean_width for c in cells}
    for stratifier in CANDIDATES:
        for size in (12, 30):
            for score in ("0.30", "0.60", "0.90"):
                # Bonferroni adds the worst case of every stratum, so with the same
                # subsets it is never narrower than the pooled exact interval.
                pooled = widths[(stratifier, size, score, "pooled_exact_hypergeometric")]
                bonferroni = widths[
                    (stratifier, size, score, "stratified_bonferroni_hypergeometric")
                ]
                assert bonferroni >= pooled


def test_study_is_repeatable() -> None:
    assert run_coverage_study(REFERENCES, SMALL) == run_coverage_study(REFERENCES, SMALL)


def test_exact_methods_keep_coverage_and_the_summary_applies_the_pass_line() -> None:
    policy = _policy(true_scores=(0.4, 0.7), coverage_subsets=200, coverage_stage_sizes=(20,))
    cells = run_coverage_study(REFERENCES, policy)
    summary = summarize_coverage(cells, subsets=200, alpha=0.05)
    # 0.95 - 3 * sqrt(0.95 * 0.05 / 200) = 0.90377.
    assert summary["pass_line"] == 0.904
    for cell in cells:
        # The conservative reference holds its nominal coverage in every cell.
        if cell.method == "stratified_bonferroni_hypergeometric":
            assert cell.covered / cell.subsets >= 0.95
    for group in summary["groups"]:
        expected = all(
            c.covered / c.subsets >= summary["pass_line"]
            for c in cells
            if (c.method, c.stratifier, c.stage_size)
            == (group["method"], group["stratifier"], group["stage_size"])
        )
        assert group["passes"] is expected
    for method in summary["methods"]:
        assert method["passes_every_cell"] is all(
            g["passes"] for g in summary["groups"] if g["method"] == method["method"]
        )


def test_a_stage_size_larger_than_the_population_is_rejected() -> None:
    with pytest.raises(AnalysisError, match="stage size"):
        run_coverage_study(REFERENCES, _policy(coverage_stage_sizes=(61,)))


def test_worker_processes_give_the_same_cells() -> None:
    assert run_coverage_study(REFERENCES, SMALL, workers=3) == run_coverage_study(REFERENCES, SMALL)
