"""The error-rate study: wrong decisions and the distance to decide, for two generators."""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import CANDIDATES
from benchmark_reference.threshold_benchmarks import LIVE_CODE_BENCH, ReferencePanel
from benchmark_reference.threshold_error_rate import (
    FLIP,
    GENERATORS,
    RASCH,
    ErrorRateCell,
    Generators,
    distance_to_decide,
    error_rate_pass_line,
    run_error_rate_study,
    summarize_error_rate,
)
from benchmark_reference.threshold_intervals import INTERVAL_METHODS
from benchmark_reference.threshold_policy import ThresholdPolicy, load_policy
from benchmark_reference.two_stage import FinalDecision

DRAFT = load_policy(Path(__file__).parents[1] / "policies" / "threshold-draft.json").benchmarks[
    LIVE_CODE_BENCH
]
REFERENCES = {
    m: {i: float((i * (j + 2)) % 7 < 3 + j) for i in range(60)} for j, m in enumerate("abc")
}
PANEL = ReferencePanel(LIVE_CODE_BENCH, REFERENCES)


def _policy(**changes: object) -> ThresholdPolicy:
    return replace(DRAFT, **changes)  # type: ignore[arg-type]


SMALL_SETTINGS: dict[str, object] = {
    "threshold": 0.6,
    "error_true_scores": (0.3, 0.6, 0.9),
    "error_draws": 30,
    "error_stage_sizes": (12, 30),
}
SMALL = _policy(**SMALL_SETTINGS)


def _cell(
    true_score: str,
    *,
    decided: int,
    wrong: int = 0,
    draws: int = 1000,
    generator: str = RASCH,
    method: str = INTERVAL_METHODS[0],
    stage_size: int = 63,
    truth: FinalDecision | None = None,
) -> ErrorRateCell:
    if truth is None:
        truth = "GO" if Fraction(true_score) >= Fraction("0.7") else "NO GO"
    # Right decisions take the side of the truth; wrong decisions take the other side.
    right = decided - wrong
    go, no_go = (right, wrong) if truth == "GO" else (wrong, right)
    return ErrorRateCell(
        generator=generator,
        stratifier=CANDIDATES[0],
        stage_size=stage_size,
        true_score=true_score,
        full_passes=0,
        truth=truth,
        method=method,
        draws=draws,
        stage1_go=go,
        stage1_no_go=no_go,
        escalated=draws - decided,
        expected=None,
    )


def test_pass_line_is_alpha_plus_three_standard_errors() -> None:
    # 0.05 + 3 * sqrt(0.05 * 0.95 / 1000) = 0.07068, stated as 0.071.
    assert error_rate_pass_line(1000, alpha=0.05) == Fraction(71, 1000)
    # 0.05 + 3 * sqrt(0.05 * 0.95 / 100) = 0.11538.
    assert error_rate_pass_line(100, alpha=0.05) == Fraction(115, 1000)


def test_study_runs_every_generator_stratifier_stage_size_true_score_and_method() -> None:
    cells = run_error_rate_study(PANEL, SMALL)
    keys = {(c.generator, c.stratifier, c.stage_size, c.true_score, c.method) for c in cells}
    assert len(keys) == len(cells) == 2 * len(CANDIDATES) * 2 * 3 * len(INTERVAL_METHODS)
    assert {c.generator for c in cells} == set(GENERATORS) == {RASCH, FLIP}
    assert {c.true_score for c in cells} == {"0.30", "0.60", "0.90"}
    for cell in cells:
        assert cell.draws == 30
        assert cell.stage1_go + cell.stage1_no_go + cell.escalated == 30
        # Only a stage-1 decision on the wrong side of the truth is wrong.
        assert cell.wrong == (cell.stage1_no_go if cell.truth == "GO" else cell.stage1_go)
    # 36 of 60 is the smallest full-set count at or above 0.60, so the truth is GO.
    assert {(c.full_passes, c.truth) for c in cells if c.true_score == "0.60"} == {(36, "GO")}
    assert {c.truth for c in cells if c.true_score == "0.30"} == {"NO GO"}


def test_a_census_probe_decides_every_draw_and_is_never_wrong() -> None:
    cells = run_error_rate_study(PANEL, _policy(**{**SMALL_SETTINGS, "error_stage_sizes": (60,)}))
    for cell in cells:
        assert (cell.decided, cell.wrong) == (30, 0), cell


def test_every_setting_sees_the_same_simulated_models() -> None:
    # The cells of one stage size do not change when another stage size joins the study,
    # and a census probe sees the same models as the smaller probe.
    alone = run_error_rate_study(PANEL, _policy(**{**SMALL_SETTINGS, "error_stage_sizes": (12,)}))
    both = run_error_rate_study(PANEL, SMALL)
    assert alone == tuple(c for c in both if c.stage_size == 12)


def test_study_is_repeatable_and_does_not_depend_on_the_worker_count() -> None:
    first = run_error_rate_study(PANEL, SMALL)
    assert first == run_error_rate_study(PANEL, SMALL)
    assert first == run_error_rate_study(PANEL, SMALL, workers=3)


def test_the_two_generators_give_different_draws() -> None:
    cells = run_error_rate_study(PANEL, SMALL)
    by_generator = {
        g: [(c.stage1_go, c.stage1_no_go) for c in cells if c.generator == g] for g in GENERATORS
    }
    assert by_generator[RASCH] != by_generator[FLIP]


def test_flip_targets_rotate_through_the_reference_models() -> None:
    generators = Generators(REFERENCES)
    for replicate in range(6):
        base = "abc"[replicate % 3]
        target = generators.draw(FLIP, 0.5, seed=11, replicate=replicate)
        assert target == generators.flip.draw(0.5, seed=11, base=base)
    assert generators.draw(RASCH, 0.5, seed=11, replicate=4) == generators.rasch.draw(0.5, seed=11)


def test_unknown_generator_is_rejected() -> None:
    with pytest.raises(AnalysisError, match="generator"):
        Generators(REFERENCES).draw("uniform", 0.5, seed=0, replicate=0)


def test_a_stage_size_larger_than_the_population_is_rejected() -> None:
    with pytest.raises(AnalysisError, match="exceeds"):
        run_error_rate_study(PANEL, _policy(error_stage_sizes=(12, 61)))


def test_workers_must_be_a_positive_integer() -> None:
    with pytest.raises(AnalysisError, match="workers"):
        run_error_rate_study(PANEL, SMALL, workers=0)


# The distance to decide. A point is (true score - threshold, decided share).


def _points(rates: dict[str, str]) -> list[tuple[Fraction, Fraction]]:
    return [(Fraction(d), Fraction(r)) for d, r in rates.items()]


def test_distance_to_decide_is_the_nearest_distance_beyond_which_every_point_decides() -> None:
    points = _points(
        {
            "-0.3": "1",
            "-0.2": "0.97",
            "-0.1": "0.6",
            "0": "0.01",
            "0.1": "0.5",
            "0.2": "0.95",
        }
    )
    result = distance_to_decide(points, level=Fraction(95, 100))
    assert result == {"below": Fraction(2, 10), "above": Fraction(2, 10), "both": Fraction(2, 10)}


def test_a_dip_far_from_the_threshold_moves_the_distance_out() -> None:
    # -0.2 decides, but -0.3 does not, so the claim holds only from -0.4 on.
    points = _points({"-0.4": "0.99", "-0.3": "0.94", "-0.2": "0.99", "0": "0", "0.1": "1"})
    result = distance_to_decide(points, level=Fraction(95, 100))
    assert result["below"] == Fraction(4, 10)
    assert result["above"] == Fraction(1, 10)
    assert result["both"] == Fraction(4, 10)


def test_a_side_that_never_decides_has_no_distance() -> None:
    points = _points({"-0.2": "1", "-0.1": "0.99", "0": "0.2", "0.1": "0.9"})
    result = distance_to_decide(points, level=Fraction(95, 100))
    assert result == {"below": Fraction(1, 10), "above": None, "both": None}


def test_a_side_without_points_has_no_distance() -> None:
    points = _points({"-0.2": "1", "-0.1": "0.99"})
    assert distance_to_decide(points, level=Fraction(95, 100))["above"] is None


def test_the_threshold_point_belongs_to_the_side_at_or_above_the_threshold() -> None:
    points = _points({"-0.1": "1", "0": "1"})
    assert distance_to_decide(points, level=Fraction(95, 100)) == {
        "below": Fraction(1, 10),
        "above": Fraction(0),
        "both": Fraction(1, 10),
    }


# The summary.


def _summary(cells: list[ErrorRateCell]) -> dict[str, Any]:
    return summarize_error_rate(cells, threshold=0.7, draws=1000, alpha=0.05)


def test_a_setting_passes_only_when_every_true_score_is_at_or_below_the_pass_line() -> None:
    passing = [_cell("0.50", decided=1000, wrong=71), _cell("0.90", decided=1000)]
    failing = [_cell("0.50", decided=1000, wrong=72), _cell("0.90", decided=1000)]
    (good,) = _summary(passing)["settings"]
    (bad,) = _summary(failing)["settings"]
    assert good["passes"] is True
    assert good["max_wrong_rate"] == 0.071
    assert bad["passes"] is False
    assert bad["failing_true_scores"] == ["0.50"]
    assert bad["max_wrong_rate_true_score"] == "0.50"


def test_summary_gives_the_distance_to_decide_in_points() -> None:
    cells = [
        _cell("0.55", decided=990),
        _cell("0.60", decided=960),
        _cell("0.65", decided=400),
        _cell("0.70", decided=10),
        _cell("0.75", decided=300),
        _cell("0.80", decided=949),
        _cell("0.85", decided=950),
    ]
    (setting,) = _summary(cells)["settings"]
    assert setting["d95_below"] == 0.1
    assert setting["d95_above"] == 0.15
    assert setting["d95"] == 0.15
    assert setting["decided_share"] == round((990 + 960 + 400 + 10 + 300 + 949 + 950) / 7000, 6)


def test_the_truth_sets_the_side_of_a_true_score() -> None:
    # With few questions, the full-set score of a 0.69 model can reach the 0.70 threshold.
    # Its truth is GO, so it counts on the side above the threshold.
    cells = [
        _cell("0.50", decided=1000),
        _cell("0.69", decided=1000, truth="GO"),
    ]
    (setting,) = _summary(cells)["settings"]
    assert (setting["d95_below"], setting["d95_above"]) == (0.2, 0.01)


def test_the_combined_setting_needs_both_generators_to_pass() -> None:
    cells = [
        _cell("0.50", decided=1000, wrong=10, generator=RASCH),
        _cell("0.90", decided=1000, generator=RASCH),
        _cell("0.50", decided=1000, wrong=80, generator=FLIP),
        _cell("0.90", decided=1000, generator=FLIP),
    ]
    summary = _summary(cells)
    (combined,) = summary["combined"]
    assert combined["passes_both_generators"] is False
    assert combined["max_wrong_rate"] == 0.08
    assert combined["failing_generators"] == [FLIP]
    assert summary["pass_line"] == 0.071


def test_the_combined_distance_is_the_larger_distance_of_the_two_generators() -> None:
    rasch = [_cell("0.50", decided=1000), _cell("0.60", decided=1000), _cell("0.80", decided=980)]
    flip = [
        _cell("0.50", decided=1000, generator=FLIP),
        _cell("0.60", decided=900, generator=FLIP),
        _cell("0.80", decided=990, generator=FLIP),
    ]
    (combined,) = _summary(rasch + flip)["combined"]
    assert combined["d95_by_generator"] == {RASCH: 0.1, FLIP: 0.2}
    assert combined["d95"] == 0.2
    assert (combined["d95_below"], combined["d95_above"]) == (0.2, 0.1)


def test_the_combined_distance_is_none_when_one_generator_never_decides() -> None:
    rasch = [_cell("0.50", decided=1000), _cell("0.80", decided=980)]
    flip = [_cell("0.50", decided=1000, generator=FLIP), _cell("0.80", decided=10, generator=FLIP)]
    (combined,) = _summary(rasch + flip)["combined"]
    assert combined["d95"] is None
    # Both generators decide at 0.50, so the side below the threshold still has a distance.
    assert (combined["d95_below"], combined["d95_above"]) == (0.2, None)
