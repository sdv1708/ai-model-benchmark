"""Leave-one-model-out experiments and tie-aware fidelity on a common subset."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

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
from benchmark_reference.uncertainty import ConfidenceInterval, score_interval, validate_confidence

DEFAULT_RATIOS = (0.1, 0.2, 0.3, 0.5, 1.0)
DEFAULT_SEEDS = tuple(range(20))


@dataclass(frozen=True, slots=True)
class OrderingFidelity:
    """A tie is never silently counted as a preserved strict ordering."""

    concordant: int
    discordant: int
    full_only_ties: int
    subset_only_ties: int
    joint_ties: int
    pair_agreement: float
    kendall_tau_b: float | None


def ordering_fidelity(
    full: Mapping[str, float], estimated: Mapping[str, float]
) -> OrderingFidelity:
    """Compare every model pair; tau-b is undefined for a constant ranking.

    Differences within 1e-12 are ties, avoiding floating summation artifacts. This
    small tolerance is numerical, not a claimed practical equivalence margin.
    """
    if set(full) != set(estimated) or len(full) < 2:
        raise AnalysisError("Ordering requires the same two or more models")
    if any(not math.isfinite(x) for values in (full, estimated) for x in values.values()):
        raise AnalysisError("Ordering scores must be finite")

    def sign(value: float) -> int:
        return 0 if abs(value) <= 1e-12 else (1 if value > 0 else -1)

    concordant = discordant = full_ties = subset_ties = joint = 0
    for a, b in combinations(sorted(full), 2):
        left, right = sign(full[a] - full[b]), sign(estimated[a] - estimated[b])
        if left == right == 0:
            joint += 1
        elif left == 0:
            full_ties += 1
        elif right == 0:
            subset_ties += 1
        elif left == right:
            concordant += 1
        else:
            discordant += 1
    pairs = concordant + discordant + full_ties + subset_ties + joint
    denominator = math.sqrt(
        (concordant + discordant + full_ties) * (concordant + discordant + subset_ties)
    )
    return OrderingFidelity(
        concordant,
        discordant,
        full_ties,
        subset_ties,
        joint,
        (concordant + joint) / pairs,
        (concordant - discordant) / denominator if denominator else None,
    )


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    """Selection is shared by all scored models in this fold; only one is held out."""

    strategy: str
    role: str
    keep_ratio: float
    seed: int
    held_out_model: str
    reference_models: tuple[str, ...]
    population_count: int
    selection: tuple[SelectedSample, ...]
    full_scores: dict[str, float]
    estimates: dict[str, float]
    raw_subset_means: dict[str, float]
    ordering: OrderingFidelity
    score_intervals: dict[str, ConfidenceInterval | None]


def evaluate_experiment(
    scores: ReferenceScores,
    *,
    keep_ratios: Sequence[float] = DEFAULT_RATIOS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    confidence: float = 0.95,
    candidate_strategies: tuple[str, ...] = CANDIDATES,
    candidate_selector: CandidateSelector = select_samples,
) -> tuple[ExperimentRun, ...]:
    """Evaluate all candidates and explicitly marked trivial comparisons.

    Holds out each model in turn BEFORE fitting features, allocation, or selection.
    Every seed/ratio/fold uses the same historical-only inputs for every method.
    All models are scored on that fold's common subset, but its two reference-model
    scores are in-sample diagnostics. Only the held-out score is a transfer test.
    """
    validate_confidence(confidence)
    if len(scores) < 3:
        raise AnalysisError("Leave-one-model-out evaluation requires at least three models")
    if not keep_ratios or len(set(keep_ratios)) != len(keep_ratios):
        raise AnalysisError("keep_ratios must be nonempty and unique")
    if not seeds or len(set(seeds)) != len(seeds):
        raise AnalysisError("seeds must be nonempty and unique")
    # Validate all identities/grades even when the invalid model would be held out.
    select_baseline(scores, strategy="uniform_random", keep_ratio=1.0, seed=0)
    full = {
        model: math.fsum(values.values()) / len(values) for model, values in sorted(scores.items())
    }
    population_count = len(next(iter(scores.values())))
    runs = []
    for held_out in sorted(scores):
        references = {model: values for model, values in scores.items() if model != held_out}
        for strategy in (*candidate_strategies, *BASELINES):
            selector = candidate_selector if strategy in candidate_strategies else select_baseline
            for ratio in sorted(keep_ratios):
                for seed in sorted(seeds):
                    selection = selector(references, strategy=strategy, keep_ratio=ratio, seed=seed)
                    estimates = {
                        model: math.fsum(item.weight * values[item.index] for item in selection)
                        for model, values in sorted(scores.items())
                    }
                    raw = {
                        model: math.fsum(values[item.index] for item in selection) / len(selection)
                        for model, values in sorted(scores.items())
                    }
                    runs.append(
                        ExperimentRun(
                            strategy,
                            "candidate"
                            if strategy in candidate_strategies
                            else "comparison_baseline",
                            ratio,
                            seed,
                            held_out,
                            tuple(sorted(references)),
                            population_count,
                            selection,
                            full,
                            estimates,
                            raw,
                            ordering_fidelity(full, estimates),
                            {
                                model: score_interval(
                                    selection,
                                    {item.index: values[item.index] for item in selection},
                                    confidence=confidence,
                                )
                                if strategy not in ("easiest_only", "hardest_only")
                                or len(selection) == population_count
                                else None
                                for model, values in sorted(scores.items())
                            },
                        )
                    )
    return tuple(runs)
