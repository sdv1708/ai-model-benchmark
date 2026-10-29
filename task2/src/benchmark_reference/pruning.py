"""Reference-only LiveCodeBench selection; target outcomes are never an input.

Candidates cover historical difficulty or full reference response patterns, then
sample within every occupied stratum. Population weights correct integer allocation.
No model names, sample IDs, seeds or ratios are tuned to target performance.
"""

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from benchmark_reference.models import AnalysisError

CANDIDATES = ("difficulty_stratified", "response_stratified")
BASELINES = ("uniform_random", "easiest_only", "hardest_only")
type ReferenceScores = Mapping[str, Mapping[int, float]]


@dataclass(frozen=True, slots=True)
class SelectedSample:
    """Weight is the contribution to a full-population mean, not a raw count."""

    index: int
    weight: float
    stratum: str
    population_count: int
    selected_count: int


class CandidateSelector(Protocol):
    def __call__(
        self, references: ReferenceScores, *, strategy: str, keep_ratio: float, seed: int
    ) -> tuple[SelectedSample, ...]: ...


def _validate(references: ReferenceScores, keep_ratio: float, seed: int) -> tuple[list[int], int]:
    if (
        isinstance(keep_ratio, bool)
        or not isinstance(keep_ratio, int | float)
        or not math.isfinite(keep_ratio)
        or not 0 < keep_ratio <= 1
    ):
        raise AnalysisError("keep_ratio must be finite and in (0, 1]")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise AnalysisError("seed must be an integer")
    ids = validate_references(references)
    return ids, math.ceil(len(ids) * keep_ratio)


def validate_references(references: ReferenceScores) -> list[int]:
    """Sorted question ids shared by every named reference model; grades are binary."""
    if not references or any(not model for model in references):
        raise AnalysisError("Selection requires named reference models")
    ids = set(next(iter(references.values())))
    if not ids:
        raise AnalysisError("Selection requires nonempty reference samples")
    for model, scores in references.items():
        if set(scores) != ids:
            raise AnalysisError(f"Reference sample identities differ for {model}")
        for index, score in scores.items():
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise AnalysisError("Reference indices must be nonnegative integers")
            if isinstance(score, bool) or not isinstance(score, int | float) or score not in (0, 1):
                raise AnalysisError(f"Reference score for {model}#{index} must be binary")
    return sorted(ids)


def _priority(seed: int, index: int) -> bytes:
    # Stable across input order, processes and Python versions; no global RNG state.
    return hashlib.sha256(f"lcb-pruning-v1:{seed}:{index}".encode("ascii")).digest()


def select_samples(
    references: ReferenceScores, *, strategy: str, keep_ratio: float, seed: int
) -> tuple[SelectedSample, ...]:
    """Select ceil(N * keep_ratio) unique tasks using historical models only.

    ``difficulty_stratified`` groups by number of reference passes;
    ``response_stratified`` retains the identity of who passed, including opposite
    disagreements. Each occupied group gets one task, then remaining slots go to
    the largest deficit from proportional allocation (lexical group tie-break).
    Hash priorities sample without replacement within groups. Budgets below the
    number of groups fail explicitly: no uncovered stratum receives invented weight.

    To evaluate an unseen model, callers must exclude it from ``references``. The
    experiment runner constructs that exclusion before calling this boundary.
    Trivial methods are unavailable here; see ``select_baseline`` for comparisons.
    """
    if strategy not in CANDIDATES:
        raise AnalysisError(f"Unknown candidate strategy {strategy!r}; choose {CANDIDATES}")
    _, budget = _validate(references, keep_ratio, seed)
    return select_strata(reference_strata(references, strategy=strategy), budget=budget, seed=seed)


def reference_strata(references: ReferenceScores, *, strategy: str) -> dict[str, list[int]]:
    """Group questions by reference pass count or by the full reference pass pattern."""
    if strategy not in CANDIDATES:
        raise AnalysisError(f"Unknown candidate strategy {strategy!r}; choose {CANDIDATES}")
    ids = validate_references(references)
    models = sorted(references)
    groups: dict[str, list[int]] = defaultdict(list)
    for index in ids:
        pattern = tuple(int(references[model][index]) for model in models)
        key = (
            f"passes:{sum(pattern)}/{len(models)}"
            if strategy == "difficulty_stratified"
            else "pattern:" + "".join(map(str, pattern))
        )
        groups[key].append(index)
    return dict(groups)


def select_strata(
    groups: Mapping[str, list[int]], *, budget: int, seed: int
) -> tuple[SelectedSample, ...]:
    """Allocate a covered stratified sample with full-population mean weights.

    Callers supply a disjoint, nonempty partition and a valid integer budget.
    Reuse the established hash design so LCB selections remain byte-identical.
    """
    ids = [index for members in groups.values() for index in members]
    if (
        not ids
        or any(not members for members in groups.values())
        or len(set(ids)) != len(ids)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
        or not 0 < budget <= len(ids)
        or isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        raise AnalysisError("Invalid strata, budget, or seed")
    if budget < len(groups):
        raise AnalysisError(f"Budget {budget} cannot cover {len(groups)} occupied strata")
    allocation = dict.fromkeys(sorted(groups), 1)
    for _ in range(budget - len(groups)):
        key = min(
            (key for key in allocation if allocation[key] < len(groups[key])),
            key=lambda key: (-(budget * len(groups[key]) - allocation[key] * len(ids)), key),
        )
        allocation[key] += 1
    selected: list[SelectedSample] = []
    for key, count in allocation.items():
        members = sorted(groups[key], key=lambda index: (_priority(seed, index), index))[:count]
        selected.extend(
            SelectedSample(
                index, len(groups[key]) / (len(ids) * count), key, len(groups[key]), count
            )
            for index in members
        )
    return tuple(sorted(selected, key=lambda item: item.index))


def select_baseline(
    references: ReferenceScores, *, strategy: str, keep_ratio: float, seed: int
) -> tuple[SelectedSample, ...]:
    """Comparison only: forbidden trivial methods cannot become candidate strategies."""
    if strategy not in BASELINES:
        raise AnalysisError(f"Unknown comparison baseline {strategy!r}")
    ids, budget = _validate(references, keep_ratio, seed)
    means = {index: math.fsum(scores[index] for scores in references.values()) for index in ids}
    sign = -1 if strategy == "easiest_only" else 1
    ordered = sorted(
        ids,
        key=lambda index: (
            0 if strategy == "uniform_random" else sign * means[index],
            _priority(seed, index),
            index,
        ),
    )[:budget]
    return tuple(
        SelectedSample(index, 1 / budget, "comparison_only", len(ids), budget)
        for index in sorted(ordered)
    )
