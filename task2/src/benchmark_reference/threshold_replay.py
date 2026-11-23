"""Replay a frozen policy on real models: decisions, coverage, cost, and pass criteria.

The engine takes every setting from the frozen policy file. It reads no file.

A cell is one model, one probe kind, and one threshold. Each cell has one
decision for each selection seed. The probe of a seed and its interval do not
depend on the threshold, so the engine grades each probe one time and applies
every threshold to it. The decision is the decision of ``decide_two_stage``.

There are two probe kinds:

- ``stratified`` is the probe of the policy: the strata come from the reference
  panel, and the interval is the method of the policy section.
- ``random`` is the baseline: a uniform random probe of the same size with the
  baseline interval of the policy.

An escalated run grades the full set, so its final decision has no sampling
error. Only a GO or NO GO at stage 1 can be wrong.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import (
    ReferenceScores,
    SelectedSample,
    select_baseline,
    select_strata,
)
from benchmark_reference.public_lcb import MappedQuestion
from benchmark_reference.threshold_benchmarks import ReferencePanel
from benchmark_reference.threshold_cost import CostModel, Estimates, run_tokens
from benchmark_reference.threshold_error_rate import distance_to_decide
from benchmark_reference.threshold_intervals import interval_bounds, stratum_counts
from benchmark_reference.threshold_policy import LoadedPolicy, ThresholdPolicy, alpha_spending
from benchmark_reference.threshold_protocol import grid
from benchmark_reference.threshold_study import check_benchmark, score_labels
from benchmark_reference.two_stage import (
    FinalDecision,
    TwoStageDecision,
    classify_stage1,
    decide_two_stage,
    full_set_decision,
)

STRATIFIED = "stratified"
RANDOM = "random"
PROBE_KINDS = (STRATIFIED, RANDOM)
type Grades = Mapping[int, float]


@dataclass(frozen=True, slots=True)
class ReplaySettings:
    """The settings of the unseen-model replay. Thresholds are two-decimal labels."""

    thresholds: tuple[str, ...]
    primary_threshold: str
    seeds: tuple[int, ...]
    coverage_subsets: int
    baseline_method: str


def replay_settings(loaded: LoadedPolicy) -> ReplaySettings:
    """The replay settings of a frozen policy file."""
    if loaded.protocol is None:
        raise AnalysisError(f"Policy {loaded.key} has no replay protocol")
    replay = loaded.protocol["unseen_model_replay"]
    values = grid(replay["thresholds"], "protocol.unseen_model_replay.thresholds")
    section = loaded.benchmarks[replay["benchmark"]]
    seeds = replay["selection_seeds"]
    return ReplaySettings(
        thresholds=tuple(score_labels(values, name="replay thresholds")),
        primary_threshold=f"{section.threshold:.2f}",
        seeds=tuple(range(seeds["first"], seeds["last"] + 1)),
        coverage_subsets=replay["coverage_subsets"],
        baseline_method=replay["baseline"]["interval_method"],
    )


def public_targets(
    cells: Mapping[str, Mapping[str, float]], mapping: Sequence[MappedQuestion]
) -> dict[str, dict[int, float]]:
    """The raw ``pass@1`` values of the mapped questions, keyed by panel index."""
    targets: dict[str, dict[int, float]] = {}
    for model, values in cells.items():
        for item in mapping:
            if item.question_id not in values:
                raise AnalysisError(
                    f"Public model {model!r} has no grade for question {item.question_id}"
                )
        targets[model] = {item.index: values[item.question_id] for item in mapping}
    return targets


def apply_grade_rule(values: Grades, minimum: float) -> dict[int, float]:
    """1 when ``pass@1`` is at least ``minimum``, else 0."""
    return {index: float(value >= minimum) for index, value in values.items()}


@dataclass(frozen=True, slots=True)
class Probes:
    """The stage-1 probe of each seed, its interval method, and its tokens.

    ``tokens`` holds low, mean, and high tokens of each probe as integers of
    unit ``1 / denominator``, so that a sum over many decisions is exact and fast.
    """

    kind: str
    method: str
    selections: tuple[tuple[SelectedSample, ...], ...]
    denominator: int
    tokens: tuple[tuple[int, int, int], ...]


def _random_probe(
    references: ReferenceScores, population: int, size: int, seed: int
) -> tuple[SelectedSample, ...]:
    selection = select_baseline(
        references, strategy="uniform_random", keep_ratio=size / population, seed=seed
    )
    if len(selection) != size:
        raise AnalysisError(f"The random probe has {len(selection)} questions, not {size}")
    return selection


def build_probes(
    panel: ReferencePanel, policy: ThresholdPolicy, settings: ReplaySettings, costs: CostModel
) -> dict[str, Probes]:
    """Both probe kinds for each selection seed. No target grade is an input."""
    check_benchmark(panel, policy)
    population, size = len(panel.questions), policy.stage1_size
    groups = panel.strata(policy.stratifier)
    chosen = {
        STRATIFIED: (
            policy.interval_method,
            [select_strata(groups, budget=size, seed=seed) for seed in settings.seeds],
        ),
        RANDOM: (
            settings.baseline_method,
            [_random_probe(panel.references, population, size, seed) for seed in settings.seeds],
        ),
    }
    probes: dict[str, Probes] = {}
    for kind, (method, selections) in chosen.items():
        estimates = [costs.tokens(item.index for item in s) for s in selections]
        denominator = math.lcm(*(v.denominator for e in estimates for v in e.values))
        tokens = tuple(
            (int(e.low * denominator), int(e.mean * denominator), int(e.high * denominator))
            for e in estimates
        )
        probes[kind] = Probes(kind, method, tuple(selections), denominator, tokens)
    return probes


@dataclass(frozen=True, slots=True)
class ReplayCell:
    """Every decision of one model at one threshold with one probe kind.

    ``go``, ``no_go``, and ``escalated`` count the stage-1 outcomes.
    ``questions`` and ``tokens`` are the mean cost of a decision.
    """

    model: str
    probe: str
    threshold: str
    full_passes: int
    population: int
    truth: FinalDecision
    draws: int
    go: int
    no_go: int
    escalated: int
    questions: Fraction
    tokens: Estimates

    @property
    def score(self) -> Fraction:
        return Fraction(self.full_passes, self.population)

    @property
    def decided(self) -> int:
        return self.go + self.no_go

    @property
    def decided_share(self) -> Fraction:
        return Fraction(self.decided, self.draws)

    @property
    def wrong(self) -> int:
        return self.no_go if self.truth == "GO" else self.go

    @property
    def wrong_rate(self) -> Fraction:
        return Fraction(self.wrong, self.draws)

    @property
    def distance(self) -> Fraction:
        """The full-set score minus the threshold. It is negative for a NO GO truth."""
        return self.score - Fraction(self.threshold)


def replay_model(
    model: str,
    grades: Grades,
    probes: Probes,
    policy: ThresholdPolicy,
    settings: ReplaySettings,
    costs: CostModel,
) -> tuple[ReplayCell, ...]:
    """One cell for each threshold, in policy order."""
    if set(grades) != set(costs.questions):
        raise AnalysisError("Target grades must cover exactly the reference questions")
    alpha = Fraction(str(alpha_spending(policy)[0]))
    bounds = []
    for selection in probes.selections:
        counts = stratum_counts(selection, grades)
        if sum(count.population for count in counts) != len(grades):
            raise AnalysisError("Selector strata must partition exactly the reference questions")
        bounds.append(interval_bounds(probes.method, counts, alpha=alpha))
    population, passes = len(grades), int(sum(grades.values()))
    draws = len(bounds)
    cells: list[ReplayCell] = []
    for label in settings.thresholds:
        threshold = Fraction(label)
        outcomes = {"GO": 0, "NO GO": 0, "ESCALATE": 0}
        low = mean = high = questions = 0
        for (lower, upper), tokens, selection in zip(
            bounds, probes.tokens, probes.selections, strict=True
        ):
            result = classify_stage1(lower, upper, threshold)
            outcomes[result] += 1
            if result != "ESCALATE":
                low, mean, high = low + tokens[0], mean + tokens[1], high + tokens[2]
                questions += len(selection)
        escalated = outcomes["ESCALATE"]
        unit = Fraction(1, probes.denominator)
        total = Estimates(low * unit, mean * unit, high * unit) + costs.full.scale(escalated)
        cells.append(
            ReplayCell(
                model=model,
                probe=probes.kind,
                threshold=label,
                full_passes=passes,
                population=population,
                truth=full_set_decision(passes, population, threshold),
                draws=draws,
                go=outcomes["GO"],
                no_go=outcomes["NO GO"],
                escalated=escalated,
                questions=Fraction(questions + escalated * population, draws),
                tokens=total.scale(Fraction(1, draws)),
            )
        )
    return tuple(cells)


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """How often the stage-1 interval of one model holds its full-set score."""

    model: str
    subsets: int
    covered: int
    truth_below: int
    truth_above: int
    mean_width: float

    @property
    def coverage(self) -> Fraction:
        return Fraction(self.covered, self.subsets)


def _coverage_seed(simulation_seed: int, model: str, replicate: int) -> int:
    """New subsets for each model. The text differs from the text of every other study."""
    text = f"threshold-replay-coverage-v1:{simulation_seed}:{model}:{replicate}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def cover_model(
    model: str,
    grades: Grades,
    panel: ReferencePanel,
    policy: ThresholdPolicy,
    settings: ReplaySettings,
) -> CoverageResult:
    """Coverage over new stratified subsets at the policy stage-1 size."""
    groups = panel.strata(policy.stratifier)
    alpha = Fraction(str(policy.alpha))
    truth = Fraction(int(sum(grades.values())), len(grades))
    covered = below = above = 0
    width = Fraction(0)
    for replicate in range(settings.coverage_subsets):
        selection = select_strata(
            groups,
            budget=policy.stage1_size,
            seed=_coverage_seed(policy.simulation_seed, model, replicate),
        )
        lower, upper = interval_bounds(
            policy.interval_method, stratum_counts(selection, grades), alpha=alpha
        )
        width += upper - lower
        if truth < lower:
            below += 1
        elif truth > upper:
            above += 1
        else:
            covered += 1
    return CoverageResult(
        model,
        settings.coverage_subsets,
        covered,
        below,
        above,
        float(width / settings.coverage_subsets),
    )


@dataclass(frozen=True, slots=True)
class Mark:
    """One pass criterion: its worst or mean value, its limit, and the failing results."""

    passed: bool
    value: Fraction
    limit: Fraction
    checked: int
    failed: int


def _need(results: Sequence[object]) -> None:
    if not results:
        raise AnalysisError("A pass criterion has no result to check")


def wrong_rate_mark(cells: Sequence[ReplayCell], limit: Fraction) -> Mark:
    """Every cell has a wrong-decision rate of at most ``limit``."""
    _need(cells)
    rates = [c.wrong_rate for c in cells]
    failed = sum(rate > limit for rate in rates)
    return Mark(failed == 0, max(rates), limit, len(rates), failed)


def coverage_mark(results: Sequence[CoverageResult], limit: Fraction) -> Mark:
    """Every model has a coverage of at least ``limit``."""
    _need(results)
    rates = [r.coverage for r in results]
    failed = sum(rate < limit for rate in rates)
    return Mark(failed == 0, min(rates), limit, len(rates), failed)


def mean_cost_fraction(cells: Sequence[ReplayCell], costs: CostModel) -> Estimates:
    """Mean expected tokens of the cells as a share of a full run."""
    _need(cells)
    return Estimates.mean_of([c.tokens.ratio(costs.full) for c in cells])


def at_threshold(cells: Sequence[ReplayCell], label: str) -> list[ReplayCell]:
    return [c for c in cells if c.threshold == label]


def cost_mark(
    cells: Sequence[ReplayCell], primary_threshold: str, costs: CostModel, limit: Fraction
) -> Mark:
    """The mean expected token cost at the primary threshold is below ``limit``.

    The value is the mean token estimate. The mean cost in questions is below 1
    exactly when the mean cost in tokens is below 1: both are 1 only when every
    decision escalates.
    """
    members = at_threshold(cells, primary_threshold)
    value = mean_cost_fraction(members, costs).mean
    passed = value < limit
    return Mark(passed, value, limit, len(members), 0 if passed else 1)


def real_distances(cells: Sequence[ReplayCell]) -> dict[str, Fraction | None]:
    """d95 of the real models on each side of the threshold, and for both sides.

    The points are the cells, and each distance is the full-set score minus the
    threshold of the cell. Two models can share one distance. That distance then
    has the smallest decided share of its models, so a tie never hides a model
    that the probe does not decide.
    """
    shares: dict[Fraction, Fraction] = {}
    for cell in cells:
        shares[cell.distance] = min(shares.get(cell.distance, Fraction(1)), cell.decided_share)
    return distance_to_decide(list(shares.items()))


def wrong_outside_zone(cells: Sequence[ReplayCell], zone: Fraction) -> int:
    """Wrong decisions of the cells whose full-set score is ``zone`` or more from the threshold.

    With a zone of 0, every wrong decision counts.
    """
    return sum(c.wrong for c in cells if abs(c.distance) >= zone)


@dataclass(frozen=True, slots=True)
class HoldOutDecision:
    """One decision for a held-out reference model."""

    benchmark: str
    model: str
    seed: int
    full_passes: int
    population: int
    truth: FinalDecision
    result: TwoStageDecision
    tokens: Estimates

    @property
    def wrong(self) -> bool:
        return self.result.decision != self.truth


def hold_out_references(
    panel: ReferencePanel, policy: ThresholdPolicy, costs: CostModel
) -> tuple[HoldOutDecision, ...]:
    """Hold out each reference model in turn and decide it at the primary threshold.

    The strata come from the other reference models only. The seeds are the
    seeds of the policy section.
    """
    check_benchmark(panel, policy)
    rows: list[HoldOutDecision] = []
    for model in sorted(panel.references):
        target = panel.references[model]
        others = ReferencePanel(
            panel.benchmark,
            {m: grades for m, grades in panel.references.items() if m != model},
            panel.metadata,
        )
        groups = others.strata(policy.stratifier)

        def selector(
            references: ReferenceScores,
            *,
            stratifier: str,
            size: int,
            seed: int,
            groups: Mapping[str, list[int]] = groups,
        ) -> tuple[SelectedSample, ...]:
            return select_strata(groups, budget=size, seed=seed)

        passes, population = int(sum(target.values())), len(target)
        truth = full_set_decision(passes, population, Fraction(str(policy.threshold)))
        for seed in policy.seeds:
            result = decide_two_stage(
                others.references, target, policy=policy, seed=seed, selector=selector
            )
            rows.append(
                HoldOutDecision(
                    panel.benchmark,
                    model,
                    seed,
                    passes,
                    population,
                    truth,
                    result,
                    run_tokens(result, costs),
                )
            )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RuleResults:
    """Every result of the unseen-model replay under one grade rule."""

    name: str
    minimum: float
    cells: tuple[ReplayCell, ...]
    coverage: tuple[CoverageResult, ...]

    def of(self, probe: str) -> list[ReplayCell]:
        return [c for c in self.cells if c.probe == probe]


def replay_rule(
    name: str,
    minimum: float,
    targets: Mapping[str, Grades],
    panel: ReferencePanel,
    policy: ThresholdPolicy,
    settings: ReplaySettings,
    probes: Mapping[str, Probes],
    costs: CostModel,
) -> RuleResults:
    """Decisions of both probe kinds and the coverage of the stratified probe."""
    cells: list[ReplayCell] = []
    coverage: list[CoverageResult] = []
    for model in sorted(targets):
        grades = apply_grade_rule(targets[model], minimum)
        for kind in PROBE_KINDS:
            cells.extend(replay_model(model, grades, probes[kind], policy, settings, costs))
        coverage.append(cover_model(model, grades, panel, policy, settings))
    return RuleResults(name, minimum, tuple(cells), tuple(coverage))


def criteria_marks(
    results: RuleResults, protocol: Mapping[str, Any], settings: ReplaySettings, costs: CostModel
) -> dict[str, Mark]:
    """The three pass criteria of the policy, applied to the stratified probe."""
    criteria = protocol["unseen_model_replay"]["pass_criteria"]
    cells = results.of(STRATIFIED)
    return {
        "wrong_decision_rate": wrong_rate_mark(
            cells, Fraction(str(criteria["wrong_decision_rate"]["max"]))
        ),
        "coverage": coverage_mark(results.coverage, Fraction(str(criteria["coverage"]["min"]))),
        "mean_cost_at_primary_threshold": cost_mark(
            cells,
            settings.primary_threshold,
            costs,
            Fraction(str(criteria["mean_cost_at_primary_threshold"]["below"])),
        ),
    }
