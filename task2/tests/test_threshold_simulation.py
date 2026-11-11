"""Simulated models: reference difficulty and an exact chosen full-set score."""

import math
from collections import Counter
from itertools import combinations

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_simulation import FlipGenerator, SimulationGenerator

# Three reference models: question 0 is passed by none, 1 by one, 2 by two, 3 by all.
REFERENCES = {
    "a": {0: 0, 1: 1, 2: 1, 3: 1},
    "b": {0: 0, 1: 0, 2: 1, 3: 1},
    "c": {0: 0, 1: 0, 2: 0, 3: 1},
}


def test_difficulty_is_the_reference_pass_rate() -> None:
    generator = SimulationGenerator(REFERENCES)
    assert generator.difficulty == {0: 0.0, 1: 1 / 3, 2: 2 / 3, 3: 1.0}


@pytest.mark.parametrize(
    ("true_score", "passes"),
    # ceil(true_score * 4): the smallest full-set score at or above the target.
    [(0.0, 0), (0.25, 1), (0.3, 2), (0.5, 2), (0.51, 3), (1.0, 4)],
)
def test_draw_hits_the_chosen_full_set_score_exactly(true_score: float, passes: int) -> None:
    generator = SimulationGenerator(REFERENCES)
    for seed in range(25):
        grades = generator.draw(true_score, seed=seed)
        assert set(grades) == {0, 1, 2, 3}
        assert set(grades.values()) <= {0.0, 1.0}
        assert sum(grades.values()) == passes


def test_easy_questions_pass_more_often_than_hard_questions() -> None:
    # Two questions: none of 3 references pass one, all pass the other. Shrunk pass
    # rates are 0.5/4 and 3.5/4, so odds are 1/7 and 7. With one pass in total,
    # P(easy passes) = 7 / (7 + 1/7) = 0.98.
    references = {m: {0: 0, 1: 1} for m in ("a", "b", "c")}
    generator = SimulationGenerator(references)
    draws = 5000
    easy = sum(generator.draw(0.5, seed=seed)[1] for seed in range(draws))
    assert abs(easy / draws - 0.98) < 0.01


def test_pass_sets_follow_the_conditional_rasch_distribution() -> None:
    # Brute-force oracle: P(pass set S | |S| = 2) is proportional to the product of
    # the odds in S. Odds for 0..3 of 3 reference passes are 1/7, 3/5, 5/3 and 7.
    odds = {0: 1 / 7, 1: 3 / 5, 2: 5 / 3, 3: 7.0}
    pairs = list(combinations(odds, 2))
    total = math.fsum(odds[a] * odds[b] for a, b in pairs)
    expected = {pair: odds[pair[0]] * odds[pair[1]] / total for pair in pairs}
    generator = SimulationGenerator(REFERENCES)
    draws = 20000
    seen = Counter(
        tuple(i for i, g in generator.draw(0.5, seed=seed).items() if g) for seed in range(draws)
    )
    for pair, probability in expected.items():
        assert abs(seen[pair] / draws - probability) < 0.01, pair


def test_draws_repeat_for_one_seed_and_vary_across_seeds() -> None:
    references = {m: {i: float((i + j) % 3 == 0) for i in range(60)} for j, m in enumerate("abc")}
    generator = SimulationGenerator(references)
    assert generator.draw(0.6, seed=7) == generator.draw(0.6, seed=7)
    assert len({tuple(generator.draw(0.6, seed=s).values()) for s in range(10)}) > 1


@pytest.mark.parametrize("true_score", [-0.1, 1.1, float("nan")])
def test_true_score_outside_unit_interval_is_rejected(true_score: float) -> None:
    with pytest.raises(AnalysisError, match="true score"):
        SimulationGenerator(REFERENCES).draw(true_score, seed=0)


# The flip generator starts from the real grades of one reference model.


def test_flip_generator_lists_the_reference_models_in_sorted_order() -> None:
    assert FlipGenerator({"c": REFERENCES["c"], "a": REFERENCES["a"]}).models == ("a", "c")


@pytest.mark.parametrize("base", ["a", "b", "c"])
@pytest.mark.parametrize(("true_score", "passes"), [(0.0, 0), (0.3, 2), (0.51, 3), (1.0, 4)])
def test_flip_draw_hits_the_chosen_full_set_score_exactly(
    base: str, true_score: float, passes: int
) -> None:
    generator = FlipGenerator(REFERENCES)
    for seed in range(10):
        grades = generator.draw(true_score, seed=seed, base=base)
        assert set(grades) == {0, 1, 2, 3}
        assert set(grades.values()) <= {0.0, 1.0}
        assert sum(grades.values()) == passes


def test_flip_draw_changes_only_as_many_grades_as_it_must_and_in_one_direction() -> None:
    references = {
        m: {i: float((i * (j + 2)) % 7 < 3 + j) for i in range(60)} for j, m in enumerate("abc")
    }
    generator = FlipGenerator(references)
    for base, real in references.items():
        real_passes = int(sum(real.values()))
        for true_score in (0.2, 0.5, 0.8):
            grades = generator.draw(true_score, seed=3, base=base)
            changed = [i for i in real if grades[i] != real[i]]
            target = math.ceil(true_score * 60)
            assert len(changed) == abs(target - real_passes)
            # A draw above the real score only adds passes; a draw below only removes them.
            assert all(grades[i] == float(target > real_passes) for i in changed)


def test_flip_draw_at_the_real_score_returns_the_real_grades() -> None:
    # Model b passes 2 of 4 questions, so a 0.5 draw needs no flip.
    assert FlipGenerator(REFERENCES).draw(0.5, seed=9, base="b") == {
        i: float(g) for i, g in REFERENCES["b"].items()
    }


def test_flip_draw_chooses_the_flipped_questions_uniformly() -> None:
    # Model b fails questions 0 and 1. A 0.75 draw needs one more pass, so each of
    # the two fails becomes the pass with probability 1/2.
    generator = FlipGenerator(REFERENCES)
    draws = 4000
    seen = Counter(
        next(i for i in (0, 1) if generator.draw(0.75, seed=s, base="b")[i]) for s in range(draws)
    )
    assert abs(seen[0] / draws - 0.5) < 0.03


def test_flip_draws_repeat_for_one_seed_and_vary_across_seeds() -> None:
    references = {m: {i: float((i + j) % 3 == 0) for i in range(60)} for j, m in enumerate("abc")}
    generator = FlipGenerator(references)
    assert generator.draw(0.6, seed=7, base="a") == generator.draw(0.6, seed=7, base="a")
    assert len({tuple(generator.draw(0.6, seed=s, base="a").values()) for s in range(10)}) > 1


def test_flip_draw_rejects_an_unknown_base_model() -> None:
    with pytest.raises(AnalysisError, match="not a reference model"):
        FlipGenerator(REFERENCES).draw(0.5, seed=0, base="z")


@pytest.mark.parametrize("true_score", [-0.1, 1.1, float("nan")])
def test_flip_true_score_outside_unit_interval_is_rejected(true_score: float) -> None:
    with pytest.raises(AnalysisError, match="true score"):
        FlipGenerator(REFERENCES).draw(true_score, seed=0, base="a")
