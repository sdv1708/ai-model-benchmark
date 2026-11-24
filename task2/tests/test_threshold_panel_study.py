"""The reference-panel study engine on synthetic grades. No test reads a public grade."""

import random
from collections.abc import Iterator, Mapping
from dataclasses import replace
from fractions import Fraction

import pytest
from policy_fixtures import DRAFT

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import select_strata
from benchmark_reference.threshold_benchmarks import LIVE_CODE_BENCH
from benchmark_reference.threshold_intervals import POOLED_EXACT
from benchmark_reference.threshold_panel_study import (
    Arm,
    StrataRow,
    Variant,
    full_panel_targets,
    outside_grades,
    pass_rate_strata,
    run_random,
    run_variant,
    unit_costs,
)
from benchmark_reference.threshold_policy import load_policy
from benchmark_reference.threshold_replay import (
    RANDOM,
    STRATIFIED,
    ReplaySettings,
    apply_grade_rule,
)
from benchmark_reference.two_stage import decide_two_stage

N = 60
GROUPS = {"x": ["x1", "x2"], "y": ["y1"], "z": ["z1", "z2", "z3"]}
MODELS = [m for models in GROUPS.values() for m in models]
SETTINGS = ReplaySettings(
    thresholds=("0.30", "0.50", "0.70"),
    primary_threshold="0.70",
    seeds=tuple(range(12)),
    coverage_subsets=30,
    baseline_method=POOLED_EXACT,
)
POLICY = replace(
    load_policy(DRAFT).benchmarks[LIVE_CODE_BENCH],
    stage1_size=15,
    interval_method="stratified_wilson",
)
VARIANT = Variant("primary", 50, 4)


def _grades(seed: int = 1) -> dict[str, dict[int, float]]:
    """Raw pass@1 values, 0 to 100."""
    rng = random.Random(seed)
    values = (0.0, 10.0, 50.0, 90.0, 100.0)
    return {m: {i: rng.choice(values) for i in range(N)} for m in MODELS}


def _flipped(
    raw: Mapping[str, Mapping[int, float]], models: list[str]
) -> dict[str, Mapping[int, float]]:
    """The grades with the values of ``models`` turned around."""
    return {m: {i: 100.0 - v for i, v in g.items()} if m in models else g for m, g in raw.items()}


def _arm(raw: Mapping[str, Mapping[int, float]]) -> Arm:
    return Arm("synthetic", POLICY, raw, unit_costs(range(N)), token_costs=False)


class Locked(Mapping[int, float]):
    """Grades that no code can read."""

    def __getitem__(self, key: int) -> float:
        raise AssertionError("a grade inside the developer group was read")

    def __iter__(self) -> Iterator[int]:
        raise AssertionError("a grade inside the developer group was read")

    def __len__(self) -> int:
        raise AssertionError("a grade inside the developer group was read")


# The strata.


def test_the_strata_cut_the_reference_pass_rate_from_hard_to_easy() -> None:
    references = {
        "a": {0: 1.0, 1: 0.0, 2: 1.0, 3: 0.0, 4: 1.0, 5: 0.0, 6: 1.0, 7: 0.0},
        "b": {0: 1.0, 1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0, 5: 1.0, 6: 0.0, 7: 0.0},
        "c": {0: 1.0, 1: 0.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 0.0, 7: 0.0},
    }
    # Passes: 1 and 7 have 0, 3 and 6 have 1, 4 and 5 have 2, 0 and 2 have 3.
    assert pass_rate_strata(references, groups=4) == {
        "group:1/4": [1, 7],
        "group:2/4": [3, 6],
        "group:3/4": [4, 5],
        "group:4/4": [0, 2],
    }


def test_equal_pass_rates_split_by_question_index() -> None:
    references = {"a": dict.fromkeys(range(6), 1.0)}
    assert pass_rate_strata(references, groups=2) == {
        "group:1/2": [0, 1, 2],
        "group:2/2": [3, 4, 5],
    }


@pytest.mark.parametrize(("questions", "groups"), [(315, 4), (315, 8), (1055, 4), (1055, 8)])
def test_the_strata_partition_the_questions_into_near_equal_groups(
    questions: int, groups: int
) -> None:
    rng = random.Random(3)
    references = {m: {i: float(rng.random() < 0.6) for i in range(questions)} for m in "abc"}
    strata = pass_rate_strata(references, groups=groups)
    sizes = [len(members) for members in strata.values()]
    assert len(sizes) == groups
    assert max(sizes) - min(sizes) <= 1
    assert sorted(i for members in strata.values() for i in members) == list(range(questions))


def test_more_groups_than_questions_is_an_error() -> None:
    with pytest.raises(AnalysisError, match="cannot make 3 groups"):
        pass_rate_strata({"a": {0: 1.0, 1: 0.0}}, groups=3)


# The developer group of the target is closed.


def test_the_references_of_a_target_are_the_models_outside_its_developer_group() -> None:
    raw = _grades()
    for model, expected in (
        ("x1", {"y1", "z1", "z2", "z3"}),
        ("y1", {"x1", "x2", "z1", "z2", "z3"}),
        ("z2", {"x1", "x2", "y1"}),
    ):
        outside = outside_grades(raw, GROUPS, model, minimum=50)
        assert set(outside) == expected
        for name, grades in outside.items():
            assert grades == {i: float(v >= 50) for i, v in raw[name].items()}


def test_no_grade_inside_the_developer_group_is_read() -> None:
    raw: dict[str, Mapping[int, float]] = dict(_grades())
    raw |= {"z1": Locked(), "z2": Locked(), "z3": Locked()}
    outside = outside_grades(raw, GROUPS, "z1", minimum=50)
    assert pass_rate_strata(outside, groups=4)


def test_a_grade_change_inside_the_group_changes_no_selection() -> None:
    raw = _grades()

    def selections(grades: Mapping[str, Mapping[int, float]], model: str) -> list[object]:
        strata = pass_rate_strata(outside_grades(grades, GROUPS, model, minimum=50), groups=4)
        return [select_strata(strata, budget=15, seed=seed) for seed in range(50)]

    for group, inside in GROUPS.items():
        changed = _flipped(raw, inside)
        for model in MODELS:
            same = selections(changed, model) == selections(raw, model)
            # A target in another group uses these grades, so its selections do change.
            assert same == (model in inside), (group, model)


def test_a_grade_change_inside_the_group_changes_no_result_of_another_member() -> None:
    raw = _grades()
    before, before_strata = run_variant(_arm(raw), VARIANT, GROUPS, SETTINGS)
    after, after_strata = run_variant(_arm(_flipped(raw, ["z1", "z2"])), VARIANT, GROUPS, SETTINGS)
    assert [c for c in before.cells if c.model == "z3"] == [
        c for c in after.cells if c.model == "z3"
    ]
    assert [r for r in before.coverage if r.model == "z3"] == [
        r for r in after.coverage if r.model == "z3"
    ]
    assert [r for r in before_strata if r.developer == "z"] == [
        r for r in after_strata if r.developer == "z"
    ]


def test_a_model_in_no_developer_group_is_an_error() -> None:
    with pytest.raises(AnalysisError, match="'q' has no developer group"):
        outside_grades(_grades(), GROUPS, "q", minimum=50)


def test_a_target_with_no_model_outside_its_group_is_an_error() -> None:
    raw = {m: g for m, g in _grades().items() if m.startswith("z")}
    with pytest.raises(AnalysisError, match="no reference model"):
        outside_grades(raw, {"z": GROUPS["z"]}, "z1", minimum=50)


# The decisions.


def test_each_cell_is_the_two_stage_decision_with_the_outside_strata() -> None:
    raw = _grades()
    results, _ = run_variant(_arm(raw), VARIANT, GROUPS, SETTINGS)
    assert {c.probe for c in results.cells} == {STRATIFIED}
    cells = {(c.model, c.threshold): c for c in results.cells}
    assert set(cells) == {(m, t) for m in MODELS for t in SETTINGS.thresholds}
    for (model, threshold), cell in cells.items():
        outside = outside_grades(raw, GROUPS, model, minimum=50)
        strata = pass_rate_strata(outside, groups=4)
        target = apply_grade_rule(raw[model], 50)
        rows = [
            decide_two_stage(
                outside,
                target,
                policy=replace(POLICY, threshold=float(threshold)),
                seed=seed,
                selector=lambda references, *, stratifier, size, seed, strata=strata: select_strata(
                    strata, budget=size, seed=seed
                ),
            )
            for seed in SETTINGS.seeds
        ]
        outcomes: list[str] = [r.stage1_result for r in rows]
        counts = [outcomes.count(name) for name in ("GO", "NO GO", "ESCALATE")]
        assert [cell.go, cell.no_go, cell.escalated] == counts
        assert cell.questions == Fraction(sum(r.questions_graded for r in rows), len(rows))
        truth = "GO" if Fraction(int(sum(target.values())), N) >= Fraction(threshold) else "NO GO"
        assert cell.wrong == sum(r.decision != truth for r in rows)


def test_each_model_has_one_coverage_result_of_the_policy_subsets() -> None:
    results, _ = run_variant(_arm(_grades()), VARIANT, GROUPS, SETTINGS)
    assert [r.model for r in results.coverage] == sorted(MODELS)
    assert {r.subsets for r in results.coverage} == {SETTINGS.coverage_subsets}


def test_the_grade_rule_applies_to_the_references_and_to_the_target() -> None:
    raw = _grades()
    results, strata = run_variant(_arm(raw), Variant("secondary", 100, 4), GROUPS, SETTINGS)
    cell = next(c for c in results.cells if c.model == "y1")
    assert cell.full_passes == sum(v == 100 for v in raw["y1"].values())
    first = next(r for r in strata if r.developer == "y")
    others = [m for m in MODELS if m != "y1"]
    passes = sorted(sum(raw[m][i] == 100 for m in others) for i in range(N))
    # The first of 4 strata holds the 15 hardest of 60 questions.
    assert first == StrataRow("y", "group:1/4", 15, 5, passes[0], passes[14])


def test_the_workers_do_not_change_the_result() -> None:
    arm = _arm(_grades())
    assert run_variant(arm, VARIANT, GROUPS, SETTINGS, workers=2) == run_variant(
        arm, VARIANT, GROUPS, SETTINGS
    )


# The arms.


def test_the_full_panel_numbers_its_questions_in_identifier_order() -> None:
    raw = {"m": {"b": 50.0, "a": 0.0, "c": 100.0}, "n": {"c": 1.0, "a": 2.0, "b": 3.0}}
    assert full_panel_targets(raw) == {
        "m": {0: 0.0, 1: 50.0, 2: 100.0},
        "n": {0: 2.0, 1: 3.0, 2: 1.0},
    }


def test_unit_costs_make_the_cost_the_count_of_questions() -> None:
    results, _ = run_variant(_arm(_grades()), VARIANT, GROUPS, SETTINGS)
    for cell in results.cells:
        assert cell.tokens.values == (cell.questions,) * 3


def test_the_random_probe_of_the_full_panel_has_the_policy_size() -> None:
    raw = {"x1": {i: 100.0 * (i % 2) for i in range(1055)}}
    policy = replace(POLICY, stage1_size=211)
    arm = Arm("full", policy, raw, unit_costs(range(1055)), token_costs=False)
    cells = run_random(arm, 50, SETTINGS)
    assert {(c.model, c.probe, c.population) for c in cells} == {("x1", RANDOM, 1055)}
    # A score of 527 of 1,055 is far from 0.30, so each probe decides and costs 211 questions.
    at = next(c for c in cells if c.threshold == "0.30")
    assert at.go == len(SETTINGS.seeds)
    assert at.questions == 211
