"""Expected token cost of the two-stage rule, checked against hand-computed fixtures."""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_cost import (
    CostModel,
    Estimates,
    band_costs,
    expected_cost,
    run_cost_study,
    run_tokens,
)
from benchmark_reference.threshold_coverage import run_coverage_study
from benchmark_reference.threshold_policy import load_policy
from benchmark_reference.threshold_study import SimulatedDecision, run_simulated_study
from benchmark_reference.threshold_tokens import QuestionCost
from benchmark_reference.two_stage import TwoStageDecision

DRAFT = load_policy(Path(__file__).parents[1] / "policies" / "lcb-threshold-draft.json").policy
REFERENCES = {
    m: {i: float((i * (j + 2)) % 7 < 3 + j) for i in range(60)} for j, m in enumerate("abc")
}


def _flat(*totals: int) -> dict[int, QuestionCost]:
    """Questions whose reference models all use the same number of tokens."""
    return {
        i: QuestionCost(t, Fraction(t), t, Fraction(0), Fraction(t), 3)
        for i, t in enumerate(totals)
    }


def _row(
    probe: tuple[int, ...], seed: int, *, escalated: bool, population: int = 4
) -> SimulatedDecision:
    result = TwoStageDecision(
        stage1_size=len(probe),
        stage1_successes=0,
        stage1_lower=Fraction(0),
        stage1_upper=Fraction(1),
        stage1_result="ESCALATE" if escalated else "NO GO",
        decision="NO GO",
        decided_stage=2 if escalated else 1,
        final_lower=Fraction(0),
        final_upper=Fraction(1),
        questions_graded=population if escalated else len(probe),
        stage1_questions=probe,
    )
    return SimulatedDecision("0.50", 2, "NO GO", seed, 0, 0, result)


def test_tokens_of_a_question_set_are_the_sums_of_the_low_mean_and_high_estimates() -> None:
    costs = {
        0: QuestionCost(41, Fraction(453, 3), 312, Fraction(11), Fraction(420, 3), 3),
        1: QuestionCost(25, Fraction(25), 25, Fraction(20), Fraction(5), 3),
        2: QuestionCost(4, Fraction(9, 2), 5, Fraction(1), Fraction(7, 2), 2),
    }
    model = CostModel(costs)
    assert model.tokens((0, 2)) == Estimates(
        Fraction(45), Fraction(453, 3) + Fraction(9, 2), Fraction(317)
    )
    assert model.full == Estimates(Fraction(70), Fraction(1083, 6), Fraction(342))
    assert model.full_input_mean == Fraction(32)
    assert model.full_output_mean == Fraction(297, 2)


def test_a_run_uses_its_probe_tokens_or_the_full_set_after_escalation() -> None:
    model = CostModel(_flat(10, 20, 30, 40))
    decided = _row((0, 1), 0, escalated=False)
    escalated = _row((0, 1), 0, escalated=True)
    assert run_tokens(decided.result, model) == Estimates(Fraction(30), Fraction(30), Fraction(30))
    assert run_tokens(escalated.result, model) == model.full == Estimates(*(Fraction(100),) * 3)


def test_expected_cost_is_stage1_plus_escalation_probability_times_remaining() -> None:
    model = CostModel(_flat(10, 20, 30, 40))
    # Seed 0 probes questions 0 and 1 (30 tokens); 1 of 4 runs escalates.
    # Seed 1 probes questions 2 and 3 (70 tokens); 2 of 4 runs escalate.
    rows = [_row((0, 1), 0, escalated=i < 1) for i in range(4)]
    rows += [_row((2, 3), 1, escalated=i < 2) for i in range(4)]
    cell = expected_cost(rows, model)
    # Seed 0: 30 + 0.25 * 70 = 47.5. Seed 1: 70 + 0.5 * 30 = 85. Mean: 66.25.
    assert cell.expected.mean == Fraction(6625, 100)
    assert cell.fraction.mean == Fraction(6625, 10000)
    assert (cell.draws, cell.escalated) == (8, 3)
    assert cell.stage1.mean == Fraction(50)
    assert cell.full.mean == Fraction(100)


def test_low_and_high_cost_fractions_use_their_own_full_set_totals() -> None:
    model = CostModel(
        {
            0: QuestionCost(5, Fraction(10), 20, Fraction(0), Fraction(10), 3),
            1: QuestionCost(15, Fraction(30), 60, Fraction(0), Fraction(30), 3),
        }
    )
    # Probe {0}; one of two runs escalates.
    rows = [
        _row((0,), 0, escalated=False, population=2),
        _row((0,), 0, escalated=True, population=2),
    ]
    cell = expected_cost(rows, model)
    # Low: (5 + 0.5 * 15) / 20 = 0.625. Mean: (10 + 0.5 * 30) / 40 = 0.625.
    # High: (20 + 0.5 * 60) / 80 = 0.625.
    assert cell.expected == Estimates(Fraction(25, 2), Fraction(25), Fraction(50))
    assert cell.fraction == Estimates(Fraction(5, 8), Fraction(5, 8), Fraction(5, 8))


def test_expected_cost_equals_the_mean_of_the_tokens_of_each_run() -> None:
    policy = replace(DRAFT, true_scores=(0.4, 0.6, 0.8), seeds=(0, 1, 2), models_per_seed=7)
    policy = replace(policy, stage1_size=15)
    model = CostModel(_flat(*[(7 * i) % 11 + 1 for i in range(60)]))
    rows = run_simulated_study(REFERENCES, policy)
    for score in ("0.40", "0.60", "0.80"):
        mine = [r for r in rows if r.true_score == score]
        uses = [run_tokens(r.result, model) for r in mine]
        cell = expected_cost(mine, model)
        assert cell.expected.mean == sum(u.mean for u in uses) / len(uses)
        assert cell.escalated == sum(r.result.decided_stage == 2 for r in mine)


def test_a_census_probe_costs_one_full_run() -> None:
    policy = replace(DRAFT, true_scores=(0.4, 0.8), seeds=(0,), models_per_seed=3, stage1_size=60)
    model = CostModel(_flat(*range(1, 61)))
    for score in ("0.40", "0.80"):
        rows = [r for r in run_simulated_study(REFERENCES, policy) if r.true_score == score]
        cell = expected_cost(rows, model)
        assert cell.escalated == 0
        assert cell.fraction == Estimates(Fraction(1), Fraction(1), Fraction(1))


def test_expected_cost_rejects_rows_from_two_true_scores_or_stage_sizes() -> None:
    model = CostModel(_flat(10, 20, 30, 40))
    first = _row((0, 1), 0, escalated=False)
    other = replace(first, true_score="0.60")
    with pytest.raises(AnalysisError, match="one true score"):
        expected_cost([first, other], model)
    with pytest.raises(AnalysisError, match="one true score"):
        expected_cost([first, _row((0, 1, 2), 0, escalated=False)], model)
    with pytest.raises(AnalysisError, match="no runs"):
        expected_cost([], model)


def test_cost_study_has_one_cell_for_each_stage_size_and_true_score() -> None:
    policy = replace(
        DRAFT,
        true_scores=(0.4, 0.6, 0.8),
        seeds=(0, 1),
        models_per_seed=4,
        stage1_size=15,
        cost_stage_sizes=(6, 15, 30),
        cost_bands=((0.4, 0.6), (0.8, 0.8)),
    )
    model = CostModel(_flat(*[i % 5 + 1 for i in range(60)]))
    base = run_simulated_study(REFERENCES, policy)
    cells = run_cost_study(REFERENCES, policy, model, base_rows=base)
    assert [(c.stage_size, c.true_score) for c in cells] == [
        (n, s) for n in (6, 15, 30) for s in ("0.40", "0.60", "0.80")
    ]
    # The cell at the policy stage size comes from the decision study rows.
    for cell in cells:
        if cell.stage_size == 15:
            mine = [r for r in base if r.true_score == cell.true_score]
            assert cell == expected_cost(mine, model)
        assert cell.draws == 8
        assert 0 < cell.fraction.low <= 1 and 0 < cell.fraction.high <= 1


def test_cost_study_gives_the_same_cells_for_every_worker_count() -> None:
    policy = replace(
        DRAFT,
        true_scores=(0.4, 0.8),
        seeds=(0, 1),
        models_per_seed=3,
        stage1_size=15,
        cost_stage_sizes=(6, 15, 24, 30),
        cost_bands=((0.4, 0.8),),
    )
    model = CostModel(_flat(*[i % 3 + 1 for i in range(60)]))
    base = run_simulated_study(REFERENCES, policy)
    # Three sizes other than the policy size, so the worker pool runs.
    serial = run_cost_study(REFERENCES, policy, model, base_rows=base, workers=1)
    assert run_cost_study(REFERENCES, policy, model, base_rows=base, workers=3) == serial


def test_band_cost_is_the_mean_fraction_of_its_true_scores() -> None:
    model = CostModel(_flat(10, 20, 30, 40))
    low = expected_cost([_row((0, 1), 0, escalated=False)], model)  # 30 / 100
    high = expected_cost([_row((2, 3), 0, escalated=False)], model)  # 70 / 100
    cells = [
        replace(low, true_score="0.40"),
        replace(high, true_score="0.50"),
        replace(low, true_score="0.90"),
    ]
    bands = band_costs(cells, ((0.4, 0.5), (0.85, 0.9)))
    assert [(b.low, b.high, b.stage_size, b.true_scores) for b in bands] == [
        (0.4, 0.5, 2, ("0.40", "0.50")),
        (0.85, 0.9, 2, ("0.90",)),
    ]
    # (0.3 + 0.7) / 2 = 0.5 for the first band; 0.3 for the second.
    assert bands[0].fraction.mean == Fraction(1, 2)
    assert bands[1].fraction.mean == Fraction(3, 10)
    assert bands[0].escalation_rate == 0


def test_coverage_cells_give_the_expected_cost_for_every_interval_method() -> None:
    policy = replace(
        DRAFT, true_scores=(0.4, 0.7), coverage_subsets=30, coverage_stage_sizes=(12, 30)
    )
    # Every question costs one token, so a draw costs its stage size or 60 questions.
    model = CostModel(_flat(*[1] * 60))
    for cell in run_coverage_study(REFERENCES, policy, costs=model):
        assert cell.expected is not None
        decisive = cell.subsets - cell.escalated
        tokens = Fraction(decisive * cell.stage_size + cell.escalated * 60, cell.subsets)
        assert cell.expected == Estimates(tokens, tokens, tokens)
    without = run_coverage_study(REFERENCES, policy)
    assert all(cell.expected is None for cell in without)
