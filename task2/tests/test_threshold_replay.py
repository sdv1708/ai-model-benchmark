"""The real-replay engine on synthetic grades. No test reads a public grade."""

import random
from dataclasses import replace
from fractions import Fraction

import pytest
from policy_fixtures import DRAFT

from benchmark_reference.long_context import TaskMetadata
from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import MappedQuestion
from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH, ReferencePanel
from benchmark_reference.threshold_cost import CostModel
from benchmark_reference.threshold_intervals import POOLED_EXACT
from benchmark_reference.threshold_policy import ThresholdPolicy, load_policy
from benchmark_reference.threshold_replay import (
    RANDOM,
    STRATIFIED,
    CoverageResult,
    ReplayCell,
    ReplaySettings,
    apply_grade_rule,
    build_probes,
    cost_mark,
    cover_model,
    coverage_mark,
    hold_out_references,
    public_targets,
    real_distances,
    replay_model,
    wrong_rate_mark,
)
from benchmark_reference.threshold_tokens import QuestionCost
from benchmark_reference.two_stage import decide_two_stage

N = 60
SECTION = load_policy(DRAFT).benchmarks[LIVE_CODE_BENCH]


def _references() -> dict[str, dict[int, float]]:
    rng = random.Random(1)
    return {
        m: {i: float(rng.random() < p) for i in range(N)}
        for m, p in (("a", 0.4), ("b", 0.6), ("c", 0.8))
    }


PANEL = ReferencePanel(LIVE_CODE_BENCH, _references())
COSTS = CostModel(
    {
        i: QuestionCost(
            low=100 + i,
            mean=Fraction(601 + 3 * i, 3),
            high=300 + i,
            input_mean=Fraction(100),
            output_mean=Fraction(100),
            models=3,
        )
        for i in range(N)
    }
)
SETTINGS = ReplaySettings(
    thresholds=("0.30", "0.50", "0.70", "0.90"),
    primary_threshold="0.70",
    seeds=tuple(range(12)),
    coverage_subsets=30,
    baseline_method=POOLED_EXACT,
)


def _policy(**changes: object) -> ThresholdPolicy:
    values: dict[str, object] = {"stage1_size": 15, "interval_method": "stratified_wilson"}
    return replace(SECTION, **(values | changes))  # type: ignore[arg-type]


def _target(p: float = 0.6, seed: int = 7) -> dict[int, float]:
    rng = random.Random(seed)
    return {i: float(rng.random() < p) for i in range(N)}


# Grades and the question mapping.


def test_grade_rule_passes_at_the_minimum_and_above() -> None:
    values = {0: 0.0, 1: 49.9, 2: 50.0, 3: 99.9, 4: 100.0}
    assert apply_grade_rule(values, 50) == {0: 0, 1: 0, 2: 1, 3: 1, 4: 1}
    assert apply_grade_rule(values, 100) == {0: 0, 1: 0, 2: 0, 3: 0, 4: 1}


def test_public_targets_use_panel_indexes_and_drop_unmapped_questions() -> None:
    mapping = (MappedQuestion(4, "f", "q4"), MappedQuestion(9, "g", "q9"))
    cells = {"m": {"q4": 100.0, "q9": 0.0, "other": 50.0}}
    assert public_targets(cells, mapping) == {"m": {4: 100.0, 9: 0.0}}


def test_public_targets_name_a_mapped_question_without_a_grade() -> None:
    with pytest.raises(AnalysisError, match="q9"):
        public_targets({"m": {"q4": 1.0}}, (MappedQuestion(9, "g", "q9"),))


# The decisions.


@pytest.mark.parametrize("kind", [STRATIFIED, RANDOM])
def test_cells_equal_the_two_stage_decision_for_each_seed_and_threshold(kind: str) -> None:
    policy = _policy()
    probes = build_probes(PANEL, policy, SETTINGS, COSTS)[kind]
    target = _target()
    cells = replay_model("m", target, probes, policy, SETTINGS, COSTS)
    assert [c.threshold for c in cells] == list(SETTINGS.thresholds)
    by_seed = dict(zip(SETTINGS.seeds, probes.selections, strict=True))
    for cell in cells:
        run_policy = replace(policy, threshold=float(cell.threshold), interval_method=probes.method)
        rows = [
            decide_two_stage(
                PANEL.references,
                target,
                policy=run_policy,
                seed=seed,
                selector=lambda references, *, stratifier, size, seed: by_seed[seed],
            )
            for seed in SETTINGS.seeds
        ]
        results: list[str] = [r.stage1_result for r in rows]
        counts = [results.count(name) for name in ("GO", "NO GO", "ESCALATE")]
        assert [cell.go, cell.no_go, cell.escalated] == counts
        score = Fraction(int(sum(target.values())), N)
        truth = "GO" if score >= Fraction(cell.threshold) else "NO GO"
        assert cell.truth == truth
        assert cell.wrong == sum(r.decision != truth for r in rows)
        assert cell.questions == Fraction(sum(r.questions_graded for r in rows), len(rows))
        tokens = [
            COSTS.full if r.decided_stage == 2 else COSTS.tokens(r.stage1_questions) for r in rows
        ]
        assert cell.tokens.mean == sum(t.mean for t in tokens) / len(rows)
        assert cell.tokens.low == sum(t.low for t in tokens) / len(rows)
        assert cell.tokens.high == sum(t.high for t in tokens) / len(rows)


def test_the_stratified_probe_is_the_selection_of_the_decision_code() -> None:
    policy = _policy()
    probes = build_probes(PANEL, policy, SETTINGS, COSTS)[STRATIFIED]
    for seed, selection in zip(SETTINGS.seeds, probes.selections, strict=True):
        expected = decide_two_stage(PANEL.references, _target(), policy=policy, seed=seed)
        assert tuple(s.index for s in selection) == expected.stage1_questions


def test_the_random_probe_has_the_same_size_one_stratum_and_the_baseline_method() -> None:
    probes = build_probes(PANEL, _policy(), SETTINGS, COSTS)[RANDOM]
    assert probes.method == POOLED_EXACT
    for selection in probes.selections:
        assert len(selection) == 15
        assert {(s.stratum, s.population_count) for s in selection} == {("comparison_only", N)}


def test_a_clear_pass_is_never_wrong_and_costs_the_probe() -> None:
    policy = _policy()
    probes = build_probes(PANEL, policy, SETTINGS, COSTS)[STRATIFIED]
    cell = replay_model("m", dict.fromkeys(range(N), 1.0), probes, policy, SETTINGS, COSTS)[0]
    assert (cell.go, cell.no_go, cell.escalated, cell.wrong) == (12, 0, 0, 0)
    assert cell.questions == 15


def test_target_grades_must_cover_the_reference_questions() -> None:
    policy = _policy()
    probes = build_probes(PANEL, policy, SETTINGS, COSTS)[STRATIFIED]
    with pytest.raises(AnalysisError, match="cover exactly"):
        replay_model("m", {0: 1.0}, probes, policy, SETTINGS, COSTS)


# Coverage.


def test_coverage_of_a_census_is_complete_and_its_width_is_zero() -> None:
    result = cover_model("m", _target(), PANEL, _policy(stage1_size=N), SETTINGS)
    assert (result.covered, result.subsets, result.mean_width) == (30, 30, 0)


def test_coverage_counts_each_side_and_draws_new_subsets_for_each_model() -> None:
    policy = _policy(stage1_size=5)
    result = cover_model("m", _target(0.5), PANEL, policy, SETTINGS)
    assert result.covered + result.truth_below + result.truth_above == result.subsets
    assert cover_model("m", _target(0.5), PANEL, policy, SETTINGS) == result
    other = cover_model("n", _target(0.5), PANEL, policy, SETTINGS)
    assert replace(other, model="m") != result


# The pass criteria, at their exact limits.


def _cell(wrong: int, draws: int = 1000, **changes: object) -> ReplayCell:
    cell = ReplayCell(
        model="m",
        probe=STRATIFIED,
        threshold="0.70",
        full_passes=30,
        population=N,
        truth="NO GO",
        draws=draws,
        go=wrong,
        no_go=draws - wrong,
        escalated=0,
        questions=Fraction(15),
        tokens=COSTS.full,
    )
    return replace(cell, **changes)  # type: ignore[arg-type]


def test_wrong_rate_criterion_passes_at_the_limit_and_fails_above_it() -> None:
    at = wrong_rate_mark([_cell(71), _cell(0)], Fraction("0.071"))
    assert (at.passed, at.value, at.failed, at.checked) == (True, Fraction("0.071"), 0, 2)
    above = wrong_rate_mark([_cell(71), _cell(72)], Fraction("0.071"))
    assert (above.passed, above.value, above.failed) == (False, Fraction("0.072"), 1)


def test_coverage_criterion_passes_at_the_limit_and_fails_below_it() -> None:
    def result(covered: int) -> CoverageResult:
        return CoverageResult("m", 2000, covered, 0, 2000 - covered, 0.1)

    assert coverage_mark([result(1870)], Fraction("0.935")).passed
    below = coverage_mark([result(1870), result(1869)], Fraction("0.935"))
    assert (below.passed, below.failed, below.value) == (False, 1, Fraction(1869, 2000))


def test_cost_criterion_is_the_mean_at_the_primary_threshold_and_strictly_below() -> None:
    cells = [
        _cell(0, tokens=COSTS.full.scale(Fraction(1, 2))),
        _cell(0),
        _cell(0, threshold="0.30", tokens=COSTS.full.scale(0)),
    ]
    mark = cost_mark(cells, "0.70", COSTS, Fraction(1))
    assert (mark.passed, mark.value) == (True, Fraction(3, 4))
    full = cost_mark([_cell(0)], "0.70", COSTS, Fraction(1))
    assert (full.passed, full.value) == (False, Fraction(1))


@pytest.mark.parametrize("mark", [wrong_rate_mark, coverage_mark])
def test_a_criterion_with_no_result_is_an_error(mark: object) -> None:
    with pytest.raises(AnalysisError, match="no result"):
        mark([], Fraction(1))  # type: ignore[operator]


# The distance to decide.


def test_real_d95_takes_the_worst_cell_at_a_tied_distance() -> None:
    # Full-set score 30/60 = 0.5 against 0.70: two models at one distance, one undecided.
    far = _cell(0, full_passes=6)
    decided = _cell(0)
    undecided = _cell(0, no_go=900, escalated=100)
    assert real_distances([far, decided])["below"] == Fraction("0.2")
    assert real_distances([far, decided, undecided])["below"] == Fraction("0.6")
    # The order of the cells has no effect.
    assert real_distances([far, undecided, decided])["below"] == Fraction("0.6")


def test_real_d95_has_no_value_for_a_side_without_a_model() -> None:
    distances = real_distances([_cell(0)])
    assert distances["above"] is None
    assert distances["both"] is None


# The reference hold-out.


def test_hold_out_never_uses_the_target_as_a_reference() -> None:
    policy = _policy(seeds=(0, 1, 2))
    rows = hold_out_references(PANEL, policy, COSTS)
    assert [(r.model, r.seed) for r in rows] == [(m, s) for m in "abc" for s in (0, 1, 2)]
    for row in rows:
        others = {m: g for m, g in PANEL.references.items() if m != row.model}
        expected = decide_two_stage(
            others, PANEL.references[row.model], policy=policy, seed=row.seed
        )
        assert row.result == expected


def test_hold_out_uses_the_metadata_strata_of_aa_lcr() -> None:
    metadata = {i: TaskMetadata(1000 + i, ("u",)) for i in range(N)}
    panel = ReferencePanel(AA_LCR, _references(), metadata)
    policy = replace(
        load_policy(DRAFT).benchmarks[AA_LCR],
        stage1_size=15,
        stratifier="metadata_stratified",
        seeds=(0,),
    )
    rows = hold_out_references(panel, policy, COSTS)
    assert [r.result.stage1_size for r in rows] == [15, 15, 15]


def test_hold_out_wrong_means_a_decision_that_differs_from_the_full_set() -> None:
    rows = hold_out_references(PANEL, _policy(seeds=(0, 1)), COSTS)
    for row in rows:
        score = Fraction(int(sum(PANEL.references[row.model].values())), N)
        truth = "GO" if score >= Fraction("0.7") else "NO GO"
        assert row.wrong == (row.result.decision != truth)
