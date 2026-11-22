"""Fixed rules that choose the tuned values of a frozen policy from simulated results.

The rules read simulated results only. They never read a real grade.

1. Interval method. Among the methods that pass every cell of the coverage
   study, choose the method with the smallest mean width. A tie goes to the
   earlier method in ``INTERVAL_METHODS``.
2. Stratifier and stage-1 size. Take the error-rate settings of the chosen
   method that pass for both generators. Choose the setting with the lowest
   expected token cost under a uniform prior on the true scores from 0.30 to
   0.90. The cost of a setting is the mean, over the true scores of the
   error-rate grid, of the mean-estimate cost fraction. Each generator has equal
   weight. A tie goes to the smaller stage size, then to the stratifier name in
   alphabetical order.

The candidates are the stratifiers and stage sizes of the error-rate study only.

This module imports no other policy module, so the policy loader can re-apply
the rules to the evidence that a frozen policy records.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_intervals import INTERVAL_METHODS

# The generators of the error-rate study (#60). A test checks that they agree.
REQUIRED_GENERATORS = ("rasch", "reference_flip")
# The uniform prior of the cost rule: the true scores from 0.30 to 0.90.
COST_PRIOR = (Fraction(30, 100), Fraction(90, 100))
INTERVAL_RULE = (
    "A method passes the coverage study when it passes every cell: each stratifier, "
    "stage size, and true score. Choose the passing method with the smallest mean width. "
    "A tie goes to the earlier method in the fixed method order."
)
PROBE_RULE = (
    "Take the error-rate settings of the chosen interval method. Keep the settings that "
    "pass for both generators. Choose the stratifier and stage-1 size with the lowest "
    "expected token cost. The cost is the mean-estimate cost fraction under a uniform "
    "prior on the true scores from 0.30 to 0.90. Each true score of the error-rate grid "
    "has equal weight. Each generator has equal weight. A tie goes to the smaller stage "
    "size, then to the stratifier name in alphabetical order."
)


@dataclass(frozen=True, slots=True)
class MethodCandidate:
    """The coverage result of one interval method across every cell."""

    method: str
    cells: int
    cells_failed: int
    mean_width: float

    @property
    def passes(self) -> bool:
        return self.cells > 0 and self.cells_failed == 0


@dataclass(frozen=True, slots=True)
class ProbeCandidate:
    """The error-rate result of one stratifier and stage size for the chosen method.

    ``cost_by_generator`` holds, for each generator, the mean expected cost as a
    share of a full run, with each true score of the grid at equal weight.
    """

    stratifier: str
    stage_size: int
    passes_both_generators: bool
    cost_by_generator: Mapping[str, float | None]

    def generator_cost(self, generator: str) -> Fraction:
        """The cost of one generator as an exact decimal fraction."""
        return Fraction(str(self.cost_by_generator[generator]))

    @property
    def cost(self) -> Fraction:
        """The mean cost of both generators, each with equal weight. Exact."""
        _check_costs(self)
        total = sum((self.generator_cost(g) for g in REQUIRED_GENERATORS), Fraction(0))
        return total / len(REQUIRED_GENERATORS)


@dataclass(frozen=True, slots=True)
class Choice:
    """The chosen values of one benchmark and the candidates that the rules compared."""

    method: MethodCandidate
    probe: ProbeCandidate
    methods: tuple[MethodCandidate, ...]
    probes: tuple[ProbeCandidate, ...]

    @property
    def interval_method(self) -> str:
        return self.method.method

    @property
    def stratifier(self) -> str:
        return self.probe.stratifier

    @property
    def stage1_size(self) -> int:
        return self.probe.stage_size


def _check_costs(candidate: ProbeCandidate) -> None:
    costs = candidate.cost_by_generator
    if set(costs) != set(REQUIRED_GENERATORS) or any(costs[g] is None for g in costs):
        raise AnalysisError(
            f"Probe setting {candidate.stratifier} at {candidate.stage_size} questions needs "
            f"the cost of each generator {REQUIRED_GENERATORS}"
        )


def choose_interval_method(candidates: Sequence[MethodCandidate]) -> MethodCandidate:
    """Rule 1: the passing method with the smallest mean width."""
    passing = [c for c in candidates if c.passes]
    if not passing:
        raise AnalysisError("No interval method passes every coverage cell")
    order = {method: k for k, method in enumerate(INTERVAL_METHODS)}
    return min(
        passing,
        key=lambda c: (Fraction(str(c.mean_width)), order.get(c.method, len(order)), c.method),
    )


def _passing(candidates: Sequence[ProbeCandidate]) -> list[ProbeCandidate]:
    for candidate in candidates:
        _check_costs(candidate)
    passing = [c for c in candidates if c.passes_both_generators]
    if not passing:
        raise AnalysisError("No probe setting passes the error-rate study for both generators")
    return passing


def probe_order(candidate: ProbeCandidate, generator: str | None = None) -> tuple[Any, ...]:
    """The order of rule 2: cost, then stage size, then stratifier name.

    With ``generator``, the cost is the cost of that generator alone.
    """
    cost = candidate.cost if generator is None else candidate.generator_cost(generator)
    return (cost, candidate.stage_size, candidate.stratifier)


def choose_probe(candidates: Sequence[ProbeCandidate]) -> ProbeCandidate:
    """Rule 2: the passing setting with the lowest mean cost of both generators."""
    return min(_passing(candidates), key=probe_order)


def choose_probe_for_generator(
    candidates: Sequence[ProbeCandidate], generator: str
) -> ProbeCandidate:
    """The probe that rule 2 would choose from the cost of one generator alone.

    This is a sensitivity check for the report. It does not choose a value.
    """
    return min(_passing(candidates), key=lambda c: probe_order(c, generator))


def method_candidates(coverage: Mapping[str, Any]) -> tuple[MethodCandidate, ...]:
    """One candidate for each method of a coverage summary, in the fixed method order."""
    found = {
        str(m["method"]): MethodCandidate(
            method=str(m["method"]),
            cells=int(m["cells"]),
            cells_failed=int(m["cells_failed"]),
            mean_width=float(m["mean_width"]),
        )
        for m in coverage["methods"]
    }
    return tuple(found[m] for m in INTERVAL_METHODS if m in found)


def _check_prior(true_scores: Sequence[float]) -> None:
    """The grid must run from 0.30 to 0.90 in equal steps: a uniform prior."""
    points = [Fraction(str(s)) for s in true_scores]
    if len(points) < 2 or (points[0], points[-1]) != COST_PRIOR:
        raise AnalysisError(
            "The cost rule needs an error-rate grid of true scores from 0.30 to 0.90"
        )
    steps = {b - a for a, b in pairwise(points)}
    if len(steps) != 1:
        raise AnalysisError("The cost rule needs an error-rate grid with equal steps")


def probe_candidates(
    error_rate: Mapping[str, Any], method: str, *, true_scores: Sequence[float]
) -> tuple[ProbeCandidate, ...]:
    """The combined error-rate settings of ``method``, ordered by stratifier and stage size.

    ``true_scores`` is the error-rate grid. It must be a uniform prior from 0.30 to 0.90.
    """
    _check_prior(true_scores)
    if tuple(error_rate["generators"]) != REQUIRED_GENERATORS:
        raise AnalysisError(f"The probe rule needs both generators {REQUIRED_GENERATORS}")
    found = [
        ProbeCandidate(
            stratifier=str(c["stratifier"]),
            stage_size=int(c["stage_size"]),
            passes_both_generators=bool(c["passes_both_generators"]),
            cost_by_generator=dict(c["mean_expected_cost_fraction_by_generator"]),
        )
        for c in error_rate["combined"]
        if c["method"] == method
    ]
    if not found:
        raise AnalysisError(f"The error-rate study has no setting for interval method {method}")
    return tuple(sorted(found, key=lambda c: (c.stratifier, c.stage_size)))


def choose_values(
    coverage: Mapping[str, Any], error_rate: Mapping[str, Any], *, true_scores: Sequence[float]
) -> Choice:
    """Apply both rules to the simulated results of one benchmark: method first, then probe."""
    methods = method_candidates(coverage)
    method = choose_interval_method(methods)
    probes = probe_candidates(error_rate, method.method, true_scores=true_scores)
    return Choice(method=method, probe=choose_probe(probes), methods=methods, probes=probes)
