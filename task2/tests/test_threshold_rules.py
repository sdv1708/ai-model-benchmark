"""The fixed rules that choose the tuned values of a frozen policy from simulated results."""

from fractions import Fraction
from typing import Any

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_error_rate import GENERATORS
from benchmark_reference.threshold_intervals import INTERVAL_METHODS
from benchmark_reference.threshold_rules import (
    COST_PRIOR,
    REQUIRED_GENERATORS,
    MethodCandidate,
    ProbeCandidate,
    choose_interval_method,
    choose_probe,
    choose_values,
    method_candidates,
    probe_candidates,
)

POOLED, BONFERRONI, WILSON, BOOTSTRAP = INTERVAL_METHODS
GRID = [k / 100 for k in range(30, 91)]


def _method(method: str, *, failed: int = 0, width: float = 0.2) -> MethodCandidate:
    return MethodCandidate(method=method, cells=130, cells_failed=failed, mean_width=width)


def _probe(
    stratifier: str, size: int, rasch: float, flip: float, *, passes: bool = True
) -> ProbeCandidate:
    return ProbeCandidate(
        stratifier=stratifier,
        stage_size=size,
        passes_both_generators=passes,
        cost_by_generator={"rasch": rasch, "reference_flip": flip},
    )


def test_the_rules_use_both_generators_of_the_error_rate_study() -> None:
    assert REQUIRED_GENERATORS == GENERATORS
    assert (Fraction(30, 100), Fraction(90, 100)) == COST_PRIOR


def test_the_method_that_passes_every_cell_with_the_smallest_width_is_chosen() -> None:
    candidates = (
        _method(POOLED, width=0.167),
        _method(BONFERRONI, width=0.349),
        _method(WILSON, width=0.159),
        # The bootstrap is narrowest, but it fails coverage cells.
        _method(BOOTSTRAP, failed=27, width=0.133),
    )
    assert choose_interval_method(candidates).method == WILSON


def test_a_method_that_fails_one_cell_is_not_a_candidate() -> None:
    # The AA-LCR result of #60: Wilson fails 1 of 130 cells.
    candidates = (
        _method(POOLED, width=0.283),
        _method(BONFERRONI, width=0.624),
        _method(WILSON, failed=1, width=0.278),
        _method(BOOTSTRAP, failed=79, width=0.176),
    )
    assert choose_interval_method(candidates).method == POOLED


def test_a_width_tie_goes_to_the_earlier_method_in_the_fixed_order() -> None:
    candidates = (_method(WILSON, width=0.2), _method(POOLED, width=0.2))
    assert choose_interval_method(candidates).method == POOLED


def test_no_passing_method_stops_the_rule() -> None:
    with pytest.raises(AnalysisError, match="No interval method passes every coverage cell"):
        choose_interval_method((_method(BOOTSTRAP, failed=1),))


def test_a_method_with_no_cells_does_not_pass() -> None:
    empty = MethodCandidate(method=POOLED, cells=0, cells_failed=0, mean_width=0.1)
    with pytest.raises(AnalysisError, match="No interval method"):
        choose_interval_method((empty,))


def test_the_passing_probe_with_the_lowest_mean_cost_of_both_generators_is_chosen() -> None:
    candidates = (
        _probe("difficulty_stratified", 32, 0.550, 0.556),
        _probe("difficulty_stratified", 63, 0.460711, 0.460344),
        _probe("response_stratified", 63, 0.461453, 0.479053),
        _probe("difficulty_stratified", 95, 0.481873, 0.483124),
    )
    chosen = choose_probe(candidates)
    assert (chosen.stratifier, chosen.stage_size) == ("difficulty_stratified", 63)
    # The cost is the exact mean of the two generators.
    assert chosen.cost == (Fraction("0.460711") + Fraction("0.460344")) / 2


def test_a_cheaper_probe_that_fails_the_error_rate_study_is_not_a_candidate() -> None:
    candidates = (
        _probe("response_stratified", 32, 0.30, 0.30, passes=False),
        _probe("difficulty_stratified", 63, 0.46, 0.46),
    )
    assert choose_probe(candidates).stage_size == 63


def test_each_generator_has_equal_weight() -> None:
    # Rasch alone prefers the first probe; the mean of both generators prefers the second.
    candidates = (
        _probe("difficulty_stratified", 63, 0.40, 0.60),
        _probe("response_stratified", 63, 0.45, 0.50),
    )
    assert choose_probe(candidates).stratifier == "response_stratified"


def test_a_cost_tie_goes_to_the_smaller_stage_size_then_the_stratifier_name() -> None:
    tied = (
        _probe("response_stratified", 95, 0.5, 0.5),
        _probe("response_stratified", 63, 0.5, 0.5),
        _probe("difficulty_stratified", 63, 0.5, 0.5),
    )
    chosen = choose_probe(tied)
    assert (chosen.stratifier, chosen.stage_size) == ("difficulty_stratified", 63)


def test_no_passing_probe_stops_the_rule() -> None:
    with pytest.raises(AnalysisError, match="No probe setting passes"):
        choose_probe((_probe("difficulty_stratified", 63, 0.4, 0.4, passes=False),))


@pytest.mark.parametrize(
    "costs",
    [
        {"rasch": 0.4},
        {"rasch": 0.4, "reference_flip": None},
        {"rasch": 0.4, "reference_flip": 0.4, "other": 0.4},
    ],
)
def test_a_probe_needs_the_cost_of_exactly_both_generators(costs: dict[str, Any]) -> None:
    candidate = ProbeCandidate("difficulty_stratified", 63, True, costs)
    with pytest.raises(AnalysisError, match="cost of each generator"):
        choose_probe((candidate,))


def _coverage() -> dict[str, Any]:
    return {
        "methods": [
            {"method": POOLED, "cells": 130, "cells_failed": 0, "mean_width": 0.167217},
            {"method": BONFERRONI, "cells": 130, "cells_failed": 0, "mean_width": 0.34905},
            {"method": WILSON, "cells": 130, "cells_failed": 0, "mean_width": 0.158909},
            {"method": BOOTSTRAP, "cells": 130, "cells_failed": 27, "mean_width": 0.132938},
        ]
    }


def _combined(method: str, stratifier: str, size: int, rasch: float, flip: float) -> dict[str, Any]:
    return {
        "stratifier": stratifier,
        "stage_size": size,
        "method": method,
        "passes_both_generators": True,
        "mean_expected_cost_fraction_by_generator": {"rasch": rasch, "reference_flip": flip},
    }


def _error_rate() -> dict[str, Any]:
    return {
        "generators": ["rasch", "reference_flip"],
        "combined": [
            _combined(POOLED, "difficulty_stratified", 63, 0.30, 0.30),
            _combined(WILSON, "difficulty_stratified", 63, 0.460711, 0.460344),
            _combined(WILSON, "response_stratified", 63, 0.461453, 0.479053),
            _combined(WILSON, "difficulty_stratified", 32, 0.550513, 0.556083),
        ],
    }


def test_candidates_come_from_the_summary_documents_of_the_studies() -> None:
    methods = method_candidates(_coverage())
    assert [m.method for m in methods] == list(INTERVAL_METHODS)
    assert methods[3] == MethodCandidate(BOOTSTRAP, 130, 27, 0.132938)
    probes = probe_candidates(_error_rate(), WILSON, true_scores=GRID)
    # Only the settings of the chosen method, ordered by stratifier and stage size.
    assert [(p.stratifier, p.stage_size) for p in probes] == [
        ("difficulty_stratified", 32),
        ("difficulty_stratified", 63),
        ("response_stratified", 63),
    ]


def test_the_values_are_chosen_method_first_then_probe_for_that_method() -> None:
    choice = choose_values(_coverage(), _error_rate(), true_scores=GRID)
    # Pooled exact has the cheapest probe, but Wilson is the chosen method.
    assert choice.interval_method == WILSON
    assert (choice.stratifier, choice.stage1_size) == ("difficulty_stratified", 63)
    assert [p.stage_size for p in choice.probes] == [32, 63, 63]
    assert len(choice.methods) == 4


@pytest.mark.parametrize(
    "grid",
    [
        [k / 100 for k in range(30, 90)],  # stops at 0.89
        [k / 100 for k in range(31, 91)],  # starts at 0.31
    ],
)
def test_the_cost_prior_must_span_030_to_090(grid: list[float]) -> None:
    with pytest.raises(AnalysisError, match=r"0\.30 to 0\.90"):
        probe_candidates(_error_rate(), WILSON, true_scores=grid)


def test_a_coarser_grid_with_equal_steps_is_also_a_uniform_prior() -> None:
    grid = [k / 100 for k in range(30, 91, 5)]
    assert len(probe_candidates(_error_rate(), WILSON, true_scores=grid)) == 3


def test_an_uneven_grid_is_not_a_uniform_prior() -> None:
    grid = [0.30, 0.31, 0.50, 0.90]
    with pytest.raises(AnalysisError, match="equal steps"):
        probe_candidates(_error_rate(), WILSON, true_scores=grid)


def test_a_study_without_both_generators_cannot_choose_a_probe() -> None:
    error = {**_error_rate(), "generators": ["rasch"]}
    with pytest.raises(AnalysisError, match="both generators"):
        probe_candidates(error, WILSON, true_scores=GRID)


def test_a_method_without_settings_in_the_error_rate_study_stops_the_rule() -> None:
    with pytest.raises(AnalysisError, match="no setting"):
        probe_candidates(_error_rate(), BONFERRONI, true_scores=GRID)
