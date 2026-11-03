"""AA-LCR in the simulated decision study and the coverage study."""

from dataclasses import replace
from pathlib import Path

import pytest

from benchmark_reference.long_context import TaskMetadata
from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import (
    AA_LCR,
    LIVE_CODE_BENCH,
    ReferencePanel,
    load_reference_panel,
)
from benchmark_reference.threshold_coverage import run_coverage_study, summarize_coverage
from benchmark_reference.threshold_policy import ThresholdPolicy, load_policy
from benchmark_reference.threshold_study import run_simulated_study

TASK2 = Path(__file__).parents[1]
POLICY = load_policy(TASK2 / "policies" / "threshold-draft.json")
DRAFT = POLICY.benchmarks[AA_LCR]
PANEL = load_reference_panel(TASK2 / "data" / "aa-lcr-reference-panel.json", benchmark=AA_LCR)
STRATIFIERS = ("metadata_stratified", "length_difficulty_stratified")


def _policy(**changes: object) -> ThresholdPolicy:
    return replace(DRAFT, **changes)  # type: ignore[arg-type]


SMALL = _policy(
    seeds=(0, 1),
    true_scores=(0.4, 0.6, 0.8),
    models_per_seed=3,
    coverage_subsets=20,
    coverage_stage_sizes=(12, 20),
)


def test_simulated_aa_lcr_models_answer_the_aa_lcr_questions_in_every_stratum() -> None:
    rows = run_simulated_study(PANEL, SMALL)
    # 3 true scores x 2 seeds x 3 simulated models.
    assert len(rows) == 18
    stratum = {i: key for key, members in PANEL.strata(DRAFT.stratifier).items() for i in members}
    assert len(set(stratum.values())) == 12
    for row in rows:
        probe = row.result.stage1_questions
        assert len(probe) == 20
        # The 20-question probe covers all 12 length x difficulty strata.
        assert {stratum[i] for i in probe} == set(stratum.values())
        expected_graded = 100 if row.result.decided_stage == 2 else 20
        assert row.result.questions_graded == expected_graded
    # 60 of 100 is exactly the threshold 0.60, so its full-set decision is GO.
    at_threshold = {(r.full_passes, r.truth) for r in rows if r.true_score == "0.60"}
    assert at_threshold == {(60, "GO")}


def test_a_policy_section_of_another_benchmark_is_refused() -> None:
    lcb = POLICY.benchmarks[LIVE_CODE_BENCH]
    with pytest.raises(AnalysisError, match="benchmark"):
        run_simulated_study(PANEL, lcb)
    with pytest.raises(AnalysisError, match="benchmark"):
        run_coverage_study(PANEL, lcb)


def test_aa_lcr_coverage_runs_both_aa_lcr_stratifiers() -> None:
    cells = run_coverage_study(PANEL, SMALL)
    # 2 stratifiers x 2 stage sizes x 3 true scores x 4 methods.
    assert len(cells) == 48
    assert tuple(dict.fromkeys(c.stratifier for c in cells)) == STRATIFIERS
    for cell in cells:
        assert cell.covered + cell.truth_below + cell.truth_above == 20
    summary = summarize_coverage(cells, subsets=20, alpha=0.05)
    assert tuple(dict.fromkeys(g["stratifier"] for g in summary["groups"])) == STRATIFIERS


def _one_question_stratum_panel() -> ReferencePanel:
    """Twelve questions: eleven short ones and one long one in a stratum of its own.

    Every reference model passes every question, so both AA-LCR stratifiers give
    the same two strata: eleven questions and one question.
    """
    references = {m: dict.fromkeys(range(12), 1.0) for m in ("a", "b", "c")}
    metadata = {i: TaskMetadata(900 if i == 11 else 100, ("doc",)) for i in range(12)}
    return ReferencePanel(AA_LCR, references, metadata)


def test_a_stratum_of_one_question_is_always_in_the_probe() -> None:
    panel = _one_question_stratum_panel()
    for stratifier in STRATIFIERS:
        assert sorted(len(m) for m in panel.strata(stratifier).values()) == [1, 11]
    policy = _policy(seeds=(0, 1, 2), true_scores=(0.5, 0.9), models_per_seed=4, stage1_size=2)
    for row in run_simulated_study(panel, policy):
        assert 11 in row.result.stage1_questions
        assert 0 <= row.result.stage1_lower <= row.result.stage1_upper <= 1


def test_coverage_with_one_sampled_question_in_every_stratum() -> None:
    policy = _policy(
        true_scores=(0.5, 0.9), coverage_subsets=200, coverage_stage_sizes=(2,), seeds=(0,)
    )
    cells = run_coverage_study(_one_question_stratum_panel(), policy)
    assert len(cells) == 2 * 2 * 4
    for cell in cells:
        assert cell.covered + cell.truth_below + cell.truth_above == 200
        if cell.method == "stratified_bonferroni_hypergeometric":
            assert cell.coverage >= 0.95
        if cell.method == "stratified_bootstrap_percentile":
            # One sampled question per stratum: the bootstrap has no variance to resample.
            assert cell.mean_width == 0
