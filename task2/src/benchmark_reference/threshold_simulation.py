"""Simulated target models with known full-set scores, from reference difficulty.

Each question's difficulty is its reference pass rate. A simulated model follows a
Rasch-style model. Question ``i`` passes with odds proportional to
``(p + 0.5) / (m + 0.5 - p)``, where ``p`` of ``m`` reference models pass it. The
draw has exactly ``K = ceil(true_score * N)`` passes. The full-set score is
therefore known: it is the smallest score at or above the chosen value. The
common ability term cancels under that condition, so no fitting is needed.

Simulated grades are targets. They never become selection information.
"""

import math
import random
from collections.abc import Mapping
from fractions import Fraction

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, validate_references


def _log_add(a: float, b: float) -> float:
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    high, low = max(a, b), min(a, b)
    return high + math.log1p(math.exp(low - high))


def target_pass_count(true_score: float, population: int) -> int:
    """Smallest pass count whose full-set score is at or above ``true_score``."""
    if (
        isinstance(true_score, bool)
        or not isinstance(true_score, int | float)
        or not math.isfinite(true_score)
        or not 0 <= true_score <= 1
    ):
        raise AnalysisError("A simulated true score must be finite and in [0, 1]")
    return math.ceil(Fraction(str(true_score)) * population)


class SimulationGenerator:
    """Draw binary grades for simulated models from one fixed reference panel."""

    def __init__(self, references: ReferenceScores) -> None:
        ids = validate_references(references)
        models = len(references)
        passes = {i: sum(int(scores[i]) for scores in references.values()) for i in ids}
        self.ids = tuple(ids)
        self.difficulty: Mapping[int, float] = {i: passes[i] / models for i in ids}
        log_odds = [math.log((passes[i] + 0.5) / (models + 0.5 - passes[i])) for i in ids]
        # tail[k] = log of the sum, over size-k subsets of the remaining questions, of
        # the product of their odds. take[j][k] = P(question j passes | k passes remain).
        count = len(ids)
        tail = [0.0] + [-math.inf] * count
        take: list[list[float]] = [[]] * count
        for j in range(count - 1, -1, -1):
            remaining = count - j
            new = [0.0] + [-math.inf] * count
            row = [0.0] * (remaining + 1)
            for k in range(1, remaining + 1):
                with_j = log_odds[j] + tail[k - 1]
                new[k] = _log_add(tail[k], with_j)
                row[k] = 1.0 if k == remaining else math.exp(with_j - new[k])
            take[j] = row
            tail = new
        self._take = take

    def draw(self, true_score: float, *, seed: int) -> dict[int, float]:
        """Grades with exactly ``ceil(true_score * N)`` passes; repeatable per seed."""
        remaining = target_pass_count(true_score, len(self.ids))
        rng = random.Random(seed)
        grades: dict[int, float] = {}
        for j, index in enumerate(self.ids):
            passed = remaining > 0 and rng.random() < self._take[j][remaining]
            grades[index] = 1.0 if passed else 0.0
            remaining -= passed
        return grades
