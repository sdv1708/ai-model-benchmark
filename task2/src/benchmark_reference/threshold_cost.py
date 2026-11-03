"""Expected token cost of the two-stage rule for each operating point.

An operating point is one stage-1 size under the policy. A run decided at
stage 1 uses the tokens of its probe. A run that escalates uses the tokens of
the full set: the probe plus the remaining questions.

For one probe with stage-1 tokens ``T1``, full-set tokens ``T``, and escalation
probability ``p``, the expected cost is ``T1 + p * (T - T1)``. The expected cost
for a true score is the mean over its probes, weighted by the runs of each
probe. That is equal to the mean tokens of the runs. The cost fraction is the
expected cost divided by ``T``: the share of a full run.

Every amount has a low, a mean, and a high estimate (see ``threshold_tokens``).
Each cost fraction divides by the full-set total of the same estimate. All
amounts are exact fractions, so the result does not depend on the summation order.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import repeat

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import ReferencePanel
from benchmark_reference.threshold_policy import ThresholdPolicy, in_band
from benchmark_reference.threshold_study import (
    SimulatedDecision,
    run_simulated_study,
    true_score_labels,
)
from benchmark_reference.threshold_tokens import QuestionCost, TokenTable
from benchmark_reference.two_stage import TwoStageDecision


@dataclass(frozen=True, slots=True)
class Estimates:
    """The low, mean, and high estimates of one amount.

    The amount is a token count or a cost fraction. The field name that holds
    an ``Estimates`` value says which.
    """

    low: Fraction
    mean: Fraction
    high: Fraction

    @classmethod
    def zero(cls) -> "Estimates":
        return cls(Fraction(0), Fraction(0), Fraction(0))

    @classmethod
    def mean_of(cls, items: Sequence["Estimates"]) -> "Estimates":
        """The mean of each estimate, each item with equal weight."""
        return sum(items, cls.zero()).scale(Fraction(1, len(items)))

    @property
    def values(self) -> tuple[Fraction, Fraction, Fraction]:
        return (self.low, self.mean, self.high)

    def __add__(self, other: "Estimates") -> "Estimates":
        return Estimates(self.low + other.low, self.mean + other.mean, self.high + other.high)

    def __sub__(self, other: "Estimates") -> "Estimates":
        return Estimates(self.low - other.low, self.mean - other.mean, self.high - other.high)

    def scale(self, factor: int | Fraction) -> "Estimates":
        return Estimates(self.low * factor, self.mean * factor, self.high * factor)

    def ratio(self, whole: "Estimates") -> "Estimates":
        """Each estimate divided by the same estimate of ``whole``."""
        return Estimates(self.low / whole.low, self.mean / whole.mean, self.high / whole.high)

    def rounded(self, digits: int) -> dict[str, float]:
        """The estimates as floats for JSON, rounded so that the bytes are short and stable."""
        return {
            "low": round(float(self.low), digits),
            "mean": round(float(self.mean), digits),
            "high": round(float(self.high), digits),
        }


class CostModel:
    """The estimated tokens of each question, as integers for fast exact sums.

    The mean estimates share one denominator, so a sum over questions is an
    integer sum. Worker processes receive the model by pickle.
    """

    def __init__(self, costs: Mapping[int, QuestionCost]) -> None:
        if not costs:
            raise AnalysisError("A cost model needs at least one question")
        self.questions = tuple(sorted(costs))
        self._denominator = math.lcm(*(c.mean.denominator for c in costs.values()))
        self._low = {i: c.low for i, c in costs.items()}
        self._mean = {i: int(c.mean * self._denominator) for i, c in costs.items()}
        self._high = {i: c.high for i, c in costs.items()}
        self.full = self.tokens(self.questions)
        self.full_input_mean = sum((c.input_mean for c in costs.values()), Fraction(0))
        self.full_output_mean = sum((c.output_mean for c in costs.values()), Fraction(0))

    def tokens(self, questions: Iterable[int]) -> Estimates:
        """Tokens of one set of questions."""
        low = mean = high = 0
        try:
            for index in questions:
                low += self._low[index]
                mean += self._mean[index]
                high += self._high[index]
        except KeyError as exc:
            raise AnalysisError(f"The cost model has no question {exc.args[0]}") from exc
        return Estimates(Fraction(low), Fraction(mean, self._denominator), Fraction(high))


def run_tokens(result: TwoStageDecision, model: CostModel) -> Estimates:
    """Tokens that one run uses: its probe, or the full set after ESCALATE."""
    if result.decided_stage == 2:
        return model.full
    return model.tokens(result.stage1_questions)


@dataclass(frozen=True, slots=True)
class CostCell:
    """Expected cost at one stage-1 size and one true score.

    ``draws`` is the number of simulated runs. ``stage1`` is the mean probe
    tokens over the runs. ``expected`` is the mean tokens that a run uses.
    ``full`` is the full-set tokens.
    """

    stage_size: int
    true_score: str
    draws: int
    escalated: int
    stage1: Estimates
    expected: Estimates
    full: Estimates

    @property
    def escalation_rate(self) -> Fraction:
        return Fraction(self.escalated, self.draws)

    @property
    def fraction(self) -> Estimates:
        """Expected cost as a share of one full run, for each estimate."""
        return self.expected.ratio(self.full)


def expected_cost(rows: Sequence[SimulatedDecision], model: CostModel) -> CostCell:
    """Expected cost of the runs of one true score at one stage-1 size."""
    if not rows:
        raise AnalysisError("Expected cost needs at least one run; there are no runs")
    if len({(row.true_score, row.result.stage1_size) for row in rows}) != 1:
        raise AnalysisError("Expected cost needs runs of one true score and one stage size")
    probes: dict[tuple[int, ...], list[int]] = {}
    for row in rows:
        runs = probes.setdefault(tuple(sorted(row.result.stage1_questions)), [0, 0])
        runs[0] += 1
        runs[1] += row.result.decided_stage == 2
    full = model.full
    stage1_sum = expected_sum = Estimates.zero()
    for probe, (count, escalated) in probes.items():
        first = model.tokens(probe)
        stage1_sum += first.scale(count)
        # count * (T1 + p * (T - T1)), with p = escalated / count.
        expected_sum += first.scale(count) + (full - first).scale(escalated)
    per_run = Fraction(1, len(rows))
    return CostCell(
        stage_size=rows[0].result.stage1_size,
        true_score=rows[0].true_score,
        draws=len(rows),
        escalated=sum(escalated for _, escalated in probes.values()),
        stage1=stage1_sum.scale(per_run),
        expected=expected_sum.scale(per_run),
        full=full,
    )


def cost_by_true_score(rows: Sequence[SimulatedDecision], model: CostModel) -> list[CostCell]:
    """One cell for each true score of one decision study, in row order."""
    groups: dict[str, list[SimulatedDecision]] = {}
    for row in rows:
        groups.setdefault(row.true_score, []).append(row)
    return [expected_cost(members, model) for members in groups.values()]


def _cells_for_size(
    panel: ReferencePanel, policy: ThresholdPolicy, model: CostModel, size: int
) -> list[CostCell]:
    rows = run_simulated_study(panel, replace(policy, stage1_size=size))
    return cost_by_true_score(rows, model)


def run_cost_study(
    panel: ReferencePanel,
    policy: ThresholdPolicy,
    model: CostModel,
    *,
    base_rows: Sequence[SimulatedDecision],
    workers: int = 1,
) -> tuple[CostCell, ...]:
    """Expected cost for each cost stage size and true score, in policy order.

    Each stage size runs the decision study of the policy with that stage-1
    size. ``base_rows`` is the decision study at the policy stage-1 size, so
    that size is not run again.
    """
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise AnalysisError("Cost workers must be an integer of at least 1")
    population = len(panel.questions)
    if policy.cost_stage_sizes[-1] > population:
        raise AnalysisError(
            f"Cost stage size {policy.cost_stage_sizes[-1]} exceeds the {population} questions"
        )
    if any(row.result.stage1_size != policy.stage1_size for row in base_rows):
        raise AnalysisError("The base decision rows must use the policy stage1_size")
    sizes = [n for n in policy.cost_stage_sizes if n != policy.stage1_size]
    if workers == 1 or len(sizes) < 2:
        computed = [_cells_for_size(panel, policy, model, n) for n in sizes]
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(sizes))) as pool:
            computed = list(
                pool.map(_cells_for_size, repeat(panel), repeat(policy), repeat(model), sizes)
            )
    by_size = dict(zip(sizes, computed, strict=True))
    if policy.stage1_size in policy.cost_stage_sizes:
        by_size[policy.stage1_size] = cost_by_true_score(base_rows, model)
    return tuple(cell for n in policy.cost_stage_sizes for cell in by_size[n])


def _edge(value: float) -> str:
    """A band edge with two decimals, or with more when two would round it."""
    text = f"{value:.2f}"
    return text if float(text) == value else repr(value)


@dataclass(frozen=True, slots=True)
class BandCost:
    """Mean cost over the true scores of one band, at one stage-1 size."""

    low: float
    high: float
    stage_size: int
    true_scores: tuple[str, ...]
    escalation_rate: Fraction
    expected: Estimates
    fraction: Estimates

    @property
    def label(self) -> str:
        """The band as text, for example ``0.30 to 0.50`` or ``0.701``."""
        if self.low == self.high:
            return _edge(self.low)
        return f"{_edge(self.low)} to {_edge(self.high)}"


def band_costs(cells: Sequence[CostCell], policy: ThresholdPolicy) -> tuple[BandCost, ...]:
    """Each policy band at each stage size, ordered by band and then by stage size.

    Each true score in the band has equal weight. Membership uses the exact
    policy score, as the policy check does. A cell label has two decimals, so
    the label of 0.701 is "0.70", which is outside the band [0.701, 0.701].
    """
    exact = dict(zip(true_score_labels(policy), policy.true_scores, strict=True))
    unknown = sorted({c.true_score for c in cells} - set(exact))
    if unknown:
        raise AnalysisError(f"Cost cells have true scores that the policy does not: {unknown}")
    sizes = sorted({cell.stage_size for cell in cells})
    result: list[BandCost] = []
    for band in policy.cost_bands:
        for size in sizes:
            members = [
                c for c in cells if c.stage_size == size and in_band(exact[c.true_score], band)
            ]
            if not members:
                raise AnalysisError(f"Cost band {list(band)} has no cell at stage size {size}")
            result.append(
                BandCost(
                    low=band[0],
                    high=band[1],
                    stage_size=size,
                    true_scores=tuple(c.true_score for c in members),
                    escalation_rate=sum((c.escalation_rate for c in members), Fraction(0))
                    / len(members),
                    expected=Estimates.mean_of([c.expected for c in members]),
                    fraction=Estimates.mean_of([c.fraction for c in members]),
                )
            )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CostEvidence:
    """Everything the report needs about token cost.

    ``point`` holds one cell for each true score at the policy stage-1 size.
    ``cells`` holds one cell for each cost stage size and true score.
    """

    tokens: TokenTable
    questions: Mapping[int, QuestionCost]
    model: CostModel
    point: tuple[CostCell, ...]
    cells: tuple[CostCell, ...]
    bands: tuple[BandCost, ...]
