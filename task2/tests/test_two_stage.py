"""Two-stage threshold decisions at the public decision seam."""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, SelectedSample
from benchmark_reference.threshold_policy import ThresholdPolicy, load_policy
from benchmark_reference.threshold_simulation import SimulationGenerator
from benchmark_reference.two_stage import decide_two_stage, select_stage1

DRAFT = load_policy(Path(__file__).parents[1] / "policies" / "lcb-threshold-draft.json").policy
# Ten questions in one reference stratum: every reference model passes all of them.
ONE_STRATUM = {m: dict.fromkeys(range(10), 1.0) for m in ("a", "b")}


def _policy(**changes: object) -> ThresholdPolicy:
    return replace(DRAFT, **changes)  # type: ignore[arg-type]


class ReadLog(Mapping[int, float]):
    """Target grades that record every question the decision reads."""

    def __init__(self, grades: Mapping[int, float]) -> None:
        self._grades = dict(grades)
        self.read: list[int] = []

    def __getitem__(self, index: int) -> float:
        self.read.append(index)
        return self._grades[index]

    def __iter__(self) -> Iterator[int]:
        return iter(self._grades)

    def __len__(self) -> int:
        return len(self._grades)


def test_all_pass_probe_decides_go_at_stage_one_on_a_worked_example() -> None:
    # Pooled exact bound for 5 of 5 passes from N = 10 at alpha 0.05: the smallest
    # population count K with P(X = 5 | K) >= 0.025. C(6,5)/C(10,5) = 6/252 fails,
    # C(7,5)/C(10,5) = 21/252 passes, so the lower bound is 7/10.
    result = decide_two_stage(
        ONE_STRATUM,
        dict.fromkeys(range(10), 1.0),
        policy=_policy(threshold=0.7, stage1_size=5),
        seed=0,
    )
    assert (result.stage1_result, result.decision, result.decided_stage) == ("GO", "GO", 1)
    assert (result.stage1_lower, result.stage1_upper) == (Fraction(7, 10), Fraction(1))
    assert result.questions_graded == 5


def test_the_policy_alpha_sets_the_stage_one_interval() -> None:
    # Alpha 0.5 puts 0.25 in each tail. C(8,5)/C(10,5) = 56/252 < 0.25 and
    # C(9,5)/C(10,5) = 126/252 >= 0.25, so the lower bound narrows to 9/10.
    result = decide_two_stage(
        ONE_STRATUM,
        dict.fromkeys(range(10), 1.0),
        policy=_policy(threshold=0.9, stage1_size=5, alpha=0.5),
        seed=0,
    )
    assert result.stage1_lower == Fraction(9, 10)
    assert (result.stage1_result, result.decided_stage) == ("GO", 1)


def test_all_fail_probe_decides_no_go_at_stage_one_on_a_worked_example() -> None:
    # By symmetry the upper bound for 0 of 5 passes is 3/10.
    result = decide_two_stage(
        ONE_STRATUM,
        dict.fromkeys(range(10), 0.0),
        policy=_policy(threshold=0.31, stage1_size=5),
        seed=0,
    )
    assert (result.stage1_result, result.decision, result.decided_stage) == ("NO GO", "NO GO", 1)
    assert result.stage1_upper == Fraction(3, 10)


@pytest.mark.parametrize(
    ("grade", "threshold", "decision"), [(1.0, 0.71, "GO"), (0.0, 0.3, "NO GO")]
)
def test_undecided_probe_escalates_and_the_census_decides(
    grade: float, threshold: float, decision: str
) -> None:
    result = decide_two_stage(
        ONE_STRATUM,
        dict.fromkeys(range(10), grade),
        policy=_policy(threshold=threshold, stage1_size=5),
        seed=0,
    )
    assert (result.stage1_result, result.decision, result.decided_stage) == (
        "ESCALATE",
        decision,
        2,
    )
    assert result.questions_graded == 10
    assert result.final_lower == result.final_upper == Fraction(int(grade))


def test_a_census_gives_width_zero() -> None:
    grades = {i: float(i % 3 == 0) for i in range(10)}
    result = decide_two_stage(
        ONE_STRATUM, grades, policy=_policy(threshold=0.5, stage1_size=10), seed=3
    )
    assert result.stage1_lower == result.stage1_upper == Fraction(4, 10)
    assert (result.stage1_result, result.decision, result.decided_stage) == ("NO GO", "NO GO", 1)


def test_escalate_always_resolves_at_the_census_with_the_true_decision() -> None:
    references = {
        m: {i: float((i * (j + 2)) % 5 < 3) for i in range(40)} for j, m in enumerate("abc")
    }
    generator = SimulationGenerator(references)
    escalations = 0
    for true_score in (0.4, 0.5, 0.55, 0.6, 0.7):
        for threshold in (0.45, 0.5, 0.55, 0.6, 0.65):
            policy = _policy(threshold=threshold, stage1_size=12)
            for seed in range(20):
                grades = generator.draw(true_score, seed=seed)
                result = decide_two_stage(references, grades, policy=policy, seed=seed)
                full = Fraction(int(sum(grades.values())), 40)
                truth = "GO" if full >= Fraction(str(threshold)) else "NO GO"
                if result.stage1_result == "ESCALATE":
                    escalations += 1
                    assert result.decided_stage == 2
                    assert result.final_lower == result.final_upper
                    assert result.decision == truth
                else:
                    assert result.decided_stage == 1
                    assert result.decision == result.stage1_result
    assert escalations > 0


def test_target_grades_never_reach_a_selector() -> None:
    references = {m: {i: float((i + j) % 4 == 0) for i in range(40)} for j, m in enumerate("abc")}
    target = ReadLog({i: float(i % 2) for i in range(40)})
    calls: list[ReferenceScores] = []

    def spy(
        references: ReferenceScores, *, stratifier: str, size: int, seed: int
    ) -> tuple[SelectedSample, ...]:
        # No target grade is read before the selection exists.
        assert target.read == []
        calls.append(references)
        return select_stage1(references, stratifier=stratifier, size=size, seed=seed)

    result = decide_two_stage(
        references, target, policy=_policy(threshold=0.5, stage1_size=12), seed=1, selector=spy
    )
    assert len(calls) == 1
    assert calls[0] == references
    assert all(given is not target for given in calls[0].values())
    selected = set(select_stage1(references, stratifier=DRAFT.stratifier, size=12, seed=1))
    stage1_reads = target.read[:12]
    assert set(stage1_reads) == {item.index for item in selected}
    assert len(target.read) == result.questions_graded


def test_selection_covers_every_reference_stratum_with_the_policy_size() -> None:
    references = {m: {i: float((i + j) % 4 == 0) for i in range(40)} for j, m in enumerate("abc")}
    selection = select_stage1(references, stratifier="difficulty_stratified", size=12, seed=0)
    assert len(selection) == 12
    assert {item.stratum for item in selection} == {"passes:0/3", "passes:1/3"}


def test_target_on_other_questions_than_the_references_is_rejected() -> None:
    with pytest.raises(AnalysisError, match="questions"):
        decide_two_stage(
            ONE_STRATUM, dict.fromkeys(range(9), 1.0), policy=_policy(stage1_size=5), seed=0
        )


def test_stage_one_larger_than_the_population_is_rejected() -> None:
    with pytest.raises(AnalysisError, match="stage1_size"):
        decide_two_stage(
            ONE_STRATUM, dict.fromkeys(range(10), 1.0), policy=_policy(stage1_size=11), seed=0
        )
