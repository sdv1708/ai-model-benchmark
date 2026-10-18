"""Pairwise transfer: neither compared model participates in selector fitting."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from benchmark_reference.experiments import DEFAULT_RATIOS, DEFAULT_SEEDS, ordering_fidelity
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import (
    BASELINES,
    CANDIDATES,
    CandidateSelector,
    ReferenceScores,
    SelectedSample,
    select_baseline,
    select_samples,
)
from benchmark_reference.uncertainty import (
    ConfidenceInterval,
    paired_difference_interval,
    validate_confidence,
)

type PairConclusion = Literal["a_above_b", "b_above_a", "tie", "inconclusive"]


@dataclass(frozen=True, slots=True)
class PairTransferRun:
    strategy: str
    role: str
    keep_ratio: float
    seed: int
    models: tuple[str, str]
    reference_models: tuple[str, ...]
    population_count: int
    selection: tuple[SelectedSample, ...]
    full_difference: float
    estimated_difference: float
    difference_interval: ConfidenceInterval | None
    relation_preserved: bool
    conclusion: PairConclusion


def evaluate_pair_transfer(
    scores: ReferenceScores,
    *,
    keep_ratios: Sequence[float] = DEFAULT_RATIOS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    confidence: float = 0.95,
    candidate_strategies: tuple[str, ...] = CANDIDATES,
    candidate_selector: CandidateSelector = select_samples,
) -> tuple[PairTransferRun, ...]:
    """Hold out both compared models, then score their paired common subset.

    Difference intervals bound directional discordances with half the failure
    budget each. This uses no independence assumption about model outcomes on the
    same tasks. Bounds can be conservative and must abstain at zero.
    With three shipped models there is only ONE reference; disclose this weaker
    feature panel rather than counting fitted reference scores as transfer evidence.
    """
    validate_confidence(confidence)
    if len(scores) < 3:
        raise AnalysisError("Pair transfer requires at least three models")
    if not keep_ratios or len(set(keep_ratios)) != len(keep_ratios):
        raise AnalysisError("keep_ratios must be nonempty and unique")
    if not seeds or len(set(seeds)) != len(seeds):
        raise AnalysisError("seeds must be nonempty and unique")
    select_baseline(scores, strategy="uniform_random", keep_ratio=1, seed=0)
    population = len(next(iter(scores.values())))
    full = {model: math.fsum(values.values()) / population for model, values in scores.items()}
    runs = []
    for a, b in combinations(sorted(scores), 2):
        references = {model: values for model, values in scores.items() if model not in (a, b)}
        for strategy in (*candidate_strategies, *BASELINES):
            selector = candidate_selector if strategy in candidate_strategies else select_baseline
            for ratio in sorted(keep_ratios):
                for seed in sorted(seeds):
                    selection = selector(references, strategy=strategy, keep_ratio=ratio, seed=seed)
                    estimates = {
                        model: math.fsum(
                            item.weight * scores[model][item.index] for item in selection
                        )
                        for model in (a, b)
                    }
                    difference = math.fsum(
                        item.weight * (scores[a][item.index] - scores[b][item.index])
                        for item in selection
                    )
                    interval = None
                    conclusion: PairConclusion = "inconclusive"
                    if (
                        strategy not in ("easiest_only", "hardest_only")
                        or len(selection) == population
                    ):
                        interval = paired_difference_interval(
                            selection,
                            {item.index: scores[a][item.index] for item in selection},
                            {item.index: scores[b][item.index] for item in selection},
                            confidence=confidence,
                        )
                        if interval.lower > 0:
                            conclusion = "a_above_b"
                        elif interval.upper < 0:
                            conclusion = "b_above_a"
                        elif interval.lower == interval.upper == 0:
                            conclusion = "tie"
                    runs.append(
                        PairTransferRun(
                            strategy,
                            "candidate"
                            if strategy in candidate_strategies
                            else "comparison_baseline",
                            ratio,
                            seed,
                            (a, b),
                            tuple(sorted(references)),
                            population,
                            selection,
                            math.fsum(scores[a][i] - scores[b][i] for i in scores[a]) / population,
                            difference,
                            interval,
                            ordering_fidelity({a: full[a], b: full[b]}, estimates).pair_agreement
                            == 1,
                            conclusion,
                        )
                    )
    return tuple(runs)
