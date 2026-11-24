"""Replay a frozen policy with the public models as the reference panel (#77).

The study asks what a larger reference panel and a larger benchmark change. It
takes every setting from the frozen policy, and it reads no file.

For each target, the references are the public models outside the developer group
of the target. The strata come from their pass rate on each question, so no grade
of the target or of its group can change a probe. A question passes under the
grade rule of the policy, for a reference and for a target.

There are two arms:

- The mapped questions of the unseen-model replay (#63), with the same probe size.
  The #63 result is for the same targets on the same questions.
- Every public question, with the full-panel probe size of the policy. The public
  file has no token count, so each question of this arm costs 1.
"""

from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from fractions import Fraction

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, validate_references
from benchmark_reference.threshold_cost import CostModel
from benchmark_reference.threshold_policy import LoadedPolicy, ThresholdPolicy
from benchmark_reference.threshold_replay import (
    CoverageResult,
    Grades,
    ReplayCell,
    ReplaySettings,
    RuleResults,
    apply_grade_rule,
    cover_strata,
    random_probes,
    replay_model,
    stratified_probes,
)
from benchmark_reference.threshold_replay_report import PRIMARY, SECONDARY
from benchmark_reference.threshold_tokens import QuestionCost

type DeveloperGroups = Mapping[str, Sequence[str]]


def pass_rate_strata(references: ReferenceScores, *, groups: int) -> dict[str, list[int]]:
    """Questions in ``groups`` parts of near-equal size, from the lowest reference pass rate.

    The sort key is the pass rate, then the question index. Many questions share
    one pass rate. The index therefore decides which of them go to which part.
    """
    ids = validate_references(references)
    if not 1 <= groups <= len(ids):
        raise AnalysisError(f"{len(ids)} questions cannot make {groups} groups")
    passes = reference_passes(references)
    ordered = sorted(ids, key=lambda index: (passes[index], index))
    edges = [k * len(ids) // groups for k in range(groups + 1)]
    return {
        f"group:{k + 1:0{len(str(groups))}}/{groups}": sorted(ordered[edges[k] : edges[k + 1]])
        for k in range(groups)
    }


def reference_passes(references: ReferenceScores) -> dict[int, int]:
    """The number of reference models that pass each question."""
    return {
        index: sum(int(grades[index]) for grades in references.values())
        for index in validate_references(references)
    }


def outside_grades(
    raw: Mapping[str, Grades], developer_groups: DeveloperGroups, model: str, *, minimum: float
) -> dict[str, dict[int, float]]:
    """Binary grades of every model outside the developer group of ``model``.

    The function does not read a grade of a model inside the group.
    """
    inside = next((models for models in developer_groups.values() if model in models), None)
    if inside is None:
        raise AnalysisError(f"Public model {model!r} has no developer group")
    outside = {
        name: apply_grade_rule(raw[name], minimum) for name in sorted(raw) if name not in inside
    }
    if not outside:
        raise AnalysisError(f"Public model {model!r} has no reference model outside its group")
    return outside


def unit_costs(questions: Iterable[int]) -> CostModel:
    """A cost of 1 for each question. An amount is then a question count, not a token count."""
    one = QuestionCost(1, Fraction(1), 1, Fraction(0), Fraction(0), models=0)
    return CostModel(dict.fromkeys(questions, one))


def full_panel_targets(
    grades: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[int, float]]:
    """The raw ``pass@1`` values of every public question, numbered in identifier order."""
    return {
        model: {index: values[question] for index, question in enumerate(sorted(values))}
        for model, values in grades.items()
    }


@dataclass(frozen=True, slots=True)
class Arm:
    """One question set: its policy with the probe size of the arm, its grades, and its costs.

    ``raw`` holds the raw ``pass@1`` values of each public model. ``token_costs`` is
    false when the arm has no token count. ``costs`` then holds unit costs.
    """

    name: str
    policy: ThresholdPolicy
    raw: Mapping[str, Grades]
    costs: CostModel
    token_costs: bool

    @property
    def questions(self) -> int:
        return len(self.costs.questions)


@dataclass(frozen=True, slots=True)
class Variant:
    """One way to make the strata: the grade rule and the number of groups."""

    rule: str
    minimum: float
    groups: int


def study_variants(loaded: LoadedPolicy) -> tuple[Variant, ...]:
    """The result of the policy first, then each secondary result.

    Each secondary variant changes one value: the group count or the grade rule.
    """
    assert loaded.protocol is not None
    study, rule = loaded.protocol["reference_panel_study"], loaded.protocol["grade_rule"]
    primary, secondary = rule["primary_min_pass_at_1"], rule["secondary_min_pass_at_1"]
    return (
        Variant(PRIMARY, primary, study["groups"]),
        Variant(PRIMARY, primary, study["secondary_groups"]),
        Variant(SECONDARY, secondary, study["groups"]),
    )


def full_panel_policy(loaded: LoadedPolicy) -> ThresholdPolicy:
    """The policy section with the probe size of every public question."""
    assert loaded.protocol is not None
    section = loaded.benchmarks[loaded.protocol["unseen_model_replay"]["benchmark"]]
    study = loaded.protocol["reference_panel_study"]
    return replace(section, stage1_size=study["full_panel_stage1_size"])


@dataclass(frozen=True, slots=True)
class StrataRow:
    """One stratum of the targets of one developer.

    ``fewest`` and ``most`` are the fewest and the most reference passes of its questions.
    """

    developer: str
    stratum: str
    questions: int
    references: int
    fewest: int
    most: int


@dataclass(frozen=True, slots=True)
class _Job:
    """One target. It holds no grade of another model of the same developer group."""

    model: str
    references: ReferenceScores
    target: Grades
    groups: int
    policy: ThresholdPolicy
    settings: ReplaySettings
    costs: CostModel


def _replay_target(job: _Job) -> tuple[tuple[ReplayCell, ...], CoverageResult]:
    strata = pass_rate_strata(job.references, groups=job.groups)
    probes = stratified_probes(strata, job.policy, job.settings, job.costs)
    return (
        replay_model(job.model, job.target, probes, job.policy, job.settings, job.costs),
        cover_strata(job.model, job.target, strata, job.policy, job.settings),
    )


def _strata_rows(developer: str, references: ReferenceScores, groups: int) -> list[StrataRow]:
    passes = reference_passes(references)
    return [
        StrataRow(
            developer,
            stratum,
            len(members),
            len(references),
            min(passes[i] for i in members),
            max(passes[i] for i in members),
        )
        for stratum, members in pass_rate_strata(references, groups=groups).items()
    ]


def run_variant(
    arm: Arm,
    variant: Variant,
    developer_groups: DeveloperGroups,
    settings: ReplaySettings,
    *,
    workers: int = 1,
) -> tuple[RuleResults, tuple[StrataRow, ...]]:
    """Every decision and the coverage of each public model, and the strata of each developer.

    The result does not change with ``workers``.
    """
    jobs: list[_Job] = []
    strata: dict[str, list[StrataRow]] = {}
    developers = {m: group for group, models in developer_groups.items() for m in models}
    for model in sorted(arm.raw):
        references = outside_grades(arm.raw, developer_groups, model, minimum=variant.minimum)
        target = apply_grade_rule(arm.raw[model], variant.minimum)
        jobs.append(
            _Job(model, references, target, variant.groups, arm.policy, settings, arm.costs)
        )
        developer = developers[model]
        if developer not in strata:
            strata[developer] = _strata_rows(developer, references, variant.groups)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            done = list(pool.map(_replay_target, jobs))
    else:
        done = [_replay_target(job) for job in jobs]
    results = RuleResults(
        variant.rule,
        variant.minimum,
        tuple(cell for cells, _ in done for cell in cells),
        tuple(coverage for _, coverage in done),
    )
    return results, tuple(row for name in sorted(strata) for row in strata[name])


def run_random(arm: Arm, minimum: float, settings: ReplaySettings) -> tuple[ReplayCell, ...]:
    """Every decision of the random probe. The probes use no grade."""
    questions = {"questions": dict.fromkeys(arm.costs.questions, 0.0)}
    probes = random_probes(questions, arm.policy, settings, arm.costs)
    cells: list[ReplayCell] = []
    for model in sorted(arm.raw):
        target = apply_grade_rule(arm.raw[model], minimum)
        cells.extend(replay_model(model, target, probes, arm.policy, settings, arm.costs))
    return tuple(cells)
