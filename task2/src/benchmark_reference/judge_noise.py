"""Conditional adversarial label sensitivity, never an estimated judge flip rate."""

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations

from benchmark_reference.experiments import ExperimentRun
from benchmark_reference.models import AnalysisError, SampleResult
from benchmark_reference.pruning import ReferenceScores, SelectedSample, select_baseline


def flip_envelope(
    selection: Sequence[SelectedSample], grades: Mapping[int, float], *, flip_count: int
) -> tuple[float, float]:
    """Exact extrema of a fixed weighted estimate under at most b binary flips.

    The total pool budget may all hit selected samples; unsampled flips contribute
    zero to this estimator. The selection and its historical features stay fixed.
    """
    if isinstance(flip_count, bool) or not isinstance(flip_count, int) or flip_count < 0:
        raise AnalysisError("flip_count must be a nonnegative integer")
    if not selection or len({x.index for x in selection}) != len(selection):
        raise AnalysisError("Expected unique nonempty selection")
    if any(
        x.index not in grades
        or isinstance(grades[x.index], bool)
        or grades[x.index] not in (0, 1)
        or not math.isfinite(x.weight)
        or x.weight <= 0
        for x in selection
    ) or not math.isclose(math.fsum(x.weight for x in selection), 1, abs_tol=1e-12):
        raise AnalysisError("Expected binary grades and positive normalized weights")
    estimate = math.fsum(x.weight * grades[x.index] for x in selection)
    down = sorted((x.weight for x in selection if grades[x.index] == 1), reverse=True)
    up = sorted((x.weight for x in selection if grades[x.index] == 0), reverse=True)
    return max(0.0, estimate - math.fsum(down[:flip_count])), min(
        1.0, estimate + math.fsum(up[:flip_count])
    )


def full_pair_tipping(scores: ReferenceScores) -> list[dict[str, object]]:
    """Minimum total grade-cell flips across either model, with outputs fixed."""
    select_baseline(scores, strategy="uniform_random", keep_ratio=1, seed=0)
    rows: list[dict[str, object]] = []
    for a, b in combinations(sorted(scores), 2):
        difference = int(sum(scores[a].values()) - sum(scores[b].values()))
        gap = abs(difference)
        rows.append(
            {
                "models": (a, b),
                "signed_success_count_gap": difference,
                "minimum_total_flips_to_tie": gap,
                "minimum_total_flips_to_reverse": gap + 1 if gap else None,
                "minimum_total_flips_to_break_tie": 1 if not gap else None,
            }
        )
    return rows


def noise_report(
    samples: Sequence[SampleResult], runs: Sequence[ExperimentRun], *, flip_counts: Sequence[int]
) -> dict[str, object]:
    """Inventory the one-review design and enumerate conditional sensitivity scenarios."""
    scores: dict[str, dict[int, float]] = {}
    identities: Counter[tuple[str, int]] = Counter()
    judges: Counter[str] = Counter()
    for sample in samples:
        scores.setdefault(sample.model, {})[sample.index] = sample.score
        identities[(sample.model, sample.index)] += 1
        judges[json.dumps(sample.metadata.get("judge_metadata", {}), sort_keys=True)] += 1
    select_baseline(scores, strategy="uniform_random", keep_ratio=1, seed=0)
    if any(count != 1 for count in identities.values()):
        raise AnalysisError("Expected exactly one recorded review per model/sample")
    population = len(next(iter(scores.values())))
    if (
        not flip_counts
        or len(set(flip_counts)) != len(flip_counts)
        or any(
            isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= population
            for b in flip_counts
        )
    ):
        raise AnalysisError("flip_counts must be unique integers between zero and population size")
    sensitivity: list[dict[str, object]] = []
    for run in runs:
        grades = scores[run.held_out_model]
        successes = sum(grades.values())
        interval = run.score_intervals[run.held_out_model]
        for budget in sorted(flip_counts):
            low, high = flip_envelope(run.selection, grades, flip_count=budget)
            sensitivity.append(
                {
                    "strategy": run.strategy,
                    "role": run.role,
                    "keep_ratio": run.keep_ratio,
                    "seed": run.seed,
                    "held_out_model": run.held_out_model,
                    "flip_count": budget,
                    "pool_flip_fraction": budget / population,
                    "fixed_selection_estimate_lower": low,
                    "fixed_selection_estimate_upper": high,
                    "full_recorded_score_lower": max(0, successes - budget) / population,
                    "full_recorded_score_upper": min(population, successes + budget) / population,
                    "design_plus_flip_lower": max(0, interval.lower - budget / population)
                    if interval
                    else None,
                    "design_plus_flip_upper": min(1, interval.upper + budget / population)
                    if interval
                    else None,
                }
            )
    return {
        "recorded_grade_count": len(samples),
        "distinct_model_answers": len(identities),
        "reviews_per_answer": 1,
        "answers_with_repeat_reviews": 0,
        "estimated_judge_flip_rate": None,
        "estimated_judge_variance": None,
        "flip_counts": sorted(flip_counts),
        "judge_metadata_inventory": [
            {"metadata": json.loads(key), "count": count} for key, count in sorted(judges.items())
        ],
        "interpretation": [
            "One review per fixed answer cannot identify judge nondeterminism or bias.",
            "Seed variation and design intervals condition on stored grades, not judge reruns.",
            "Cross-model disagreements mix capability, generation and grading; not "
            "judge replicates.",
            "Flip budgets are hypothetical upper bounds, not measured or probabilistic flip rates.",
            "Sensitivity holds reference features and selection fixed; "
            "reference-label refitting is unmeasured.",
            "Design-plus-flip bounds widen finite-pool intervals by b/N for a "
            "fixed latent grade table.",
            "They retain design coverage only conditional on at most b errors, not "
            "judge correctness.",
            "At census sampling uncertainty vanishes; judge uncertainty remains unidentified.",
        ],
        "repeat_judging_plan": (
            "Freeze prompts, answers, rubric and judge version. Rejudge every "
            "answer at least 3 times "
            "with independent calls, retaining every grade, seed and "
            "configuration. Report within-answer "
            "disagreement, per-model repeat-score variation and paired rank "
            "changes; resample document "
            "sets and judge replicates separately. Use human adjudication to "
            "assess systematic bias."
        ),
        "full_pair_tipping": full_pair_tipping(scores),
        "sensitivity": sensitivity,
    }
