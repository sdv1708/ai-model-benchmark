"""AA-LCR public contracts with independent, synthetic answers."""

import math
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

from benchmark_reference.experiments import evaluate_experiment
from benchmark_reference.long_context import CANDIDATES, TaskMetadata, select_long_context
from benchmark_reference.models import AnalysisError, SampleResult, Source
from benchmark_reference.transfer import evaluate_pair_transfer


def test_metadata_selection_covers_length_and_document_count_with_population_weights() -> None:
    # Three occupied groups of sizes 2, 2, 8; a budget of 3 must keep all three.
    metadata = {
        i: TaskMetadata(100 if i < 4 else 1000, ("a",) if i < 2 else ("a", "b")) for i in range(12)
    }
    selected = select_long_context(
        {"reference": dict.fromkeys(range(12), 1.0)},
        metadata=metadata,
        strategy="metadata_stratified",
        keep_ratio=0.25,
        seed=0,
    )
    assert len(selected) == 3
    assert sorted(x.population_count for x in selected) == [2, 2, 8]
    assert sorted(x.weight for x in selected) == [1 / 6, 1 / 6, 2 / 3]
    assert math.fsum(x.weight for x in selected) == 1


def test_aa_lcr_score_and_pair_folds_exclude_target_labels_and_recover_census() -> None:
    metadata = {i: TaskMetadata(100 + i, ("a",)) for i in range(12)}
    scores = {
        "a": dict.fromkeys(range(12), 1.0),
        "b": dict.fromkeys(range(12), 0.0),
        "c": {i: float(i % 2) for i in range(12)},
    }
    selector = partial(select_long_context, metadata=metadata)
    before = evaluate_experiment(
        scores,
        keep_ratios=(0.5, 1.0),
        seeds=(0,),
        candidate_strategies=CANDIDATES,
        candidate_selector=selector,
    )
    pairs_before = evaluate_pair_transfer(
        scores,
        keep_ratios=(0.5, 1.0),
        seeds=(0,),
        candidate_strategies=CANDIDATES,
        candidate_selector=selector,
    )
    scores["a"] = dict.fromkeys(range(12), 0.0)
    scores["b"] = dict.fromkeys(range(12), 1.0)
    pairs_after = evaluate_pair_transfer(
        scores,
        keep_ratios=(0.5, 1.0),
        seeds=(0,),
        candidate_strategies=CANDIDATES,
        candidate_selector=selector,
    )
    for left, right in zip(pairs_before, pairs_after, strict=True):
        if left.models == ("a", "b"):
            assert left.selection == right.selection
            assert left.reference_models == ("c",)
    for run in before:
        assert run.held_out_model not in run.reference_models
        if run.keep_ratio == 1:
            assert run.estimates == pytest.approx(run.full_scores)
            assert run.ordering.pair_agreement == 1


def test_judge_flip_sensitivity_is_a_bound_not_a_noise_estimate() -> None:
    from benchmark_reference.judge_noise import flip_envelope, full_pair_tipping
    from benchmark_reference.pruning import SelectedSample

    # One adverse change can remove the .25 success or add the .75 failure.
    selection = (SelectedSample(0, 0.25, "a", 1, 1), SelectedSample(1, 0.75, "b", 3, 1))
    assert flip_envelope(selection, {0: 1.0, 1: 0.0}, flip_count=0) == (0.25, 0.25)
    assert flip_envelope(selection, {0: 1.0, 1: 0.0}, flip_count=1) == (0.0, 1.0)
    tipping = full_pair_tipping({"a": {0: 1.0, 1: 1.0}, "b": {0: 0.0, 1: 0.0}})
    assert tipping[0]["minimum_total_flips_to_tie"] == 2
    assert tipping[0]["minimum_total_flips_to_reverse"] == 3


@pytest.mark.parametrize("strategy", CANDIDATES)
def test_selection_is_seeded_order_independent_and_cannot_see_held_out_grades(
    strategy: str,
) -> None:
    metadata = {i: TaskMetadata(100 + i, ("a", "b")) for i in range(100)}
    scores = {
        "a": {i: float(i % 2) for i in range(100)},
        "b": {i: float(i % 3 == 0) for i in range(100)},
        "target": dict.fromkeys(range(100), 0.0),
    }
    selector = partial(select_long_context, metadata=metadata)
    before = evaluate_experiment(
        scores,
        keep_ratios=(0.2,),
        seeds=(0,),
        candidate_strategies=(strategy,),
        candidate_selector=selector,
    )
    scores["target"] = dict.fromkeys(range(100), 1.0)
    after = evaluate_experiment(
        scores,
        keep_ratios=(0.2,),
        seeds=(0,),
        candidate_strategies=(strategy,),
        candidate_selector=selector,
    )
    assert next(r.selection for r in before if r.held_out_model == "target") == next(
        r.selection for r in after if r.held_out_model == "target"
    )
    refs = {m: v for m, v in scores.items() if m != "target"}
    first = selector(refs, strategy=strategy, keep_ratio=0.2, seed=0)
    assert first == select_long_context(
        {m: dict(reversed(list(v.items()))) for m, v in reversed(refs.items())},
        metadata=dict(reversed(list(metadata.items()))),
        strategy=strategy,
        keep_ratio=0.2,
        seed=0,
    )
    assert first != selector(refs, strategy=strategy, keep_ratio=0.2, seed=1)
    assert len({x.index for x in first}) == 20


@pytest.mark.parametrize("strategy", ["uniform_random", "easiest_only", "hardest_only"])
def test_forbidden_baselines_cannot_be_long_context_candidates(strategy: str) -> None:
    with pytest.raises(AnalysisError, match="Unknown AA-LCR candidate"):
        select_long_context(
            {"a": {0: 1.0}},
            metadata={0: TaskMetadata(100, ("a",))},
            strategy=strategy,
            keep_ratio=1,
            seed=0,
        )


def test_insufficient_coverage_budget_fails_instead_of_losing_a_length_group() -> None:
    with pytest.raises(AnalysisError, match="cannot cover"):
        select_long_context(
            {"a": dict.fromkeys(range(12), 1.0)},
            metadata={i: TaskMetadata(100 + i, ("a",)) for i in range(12)},
            strategy=CANDIDATES[0],
            keep_ratio=0.01,
            seed=0,
        )


def test_metadata_uses_shared_benchmark_fields_and_rejects_cross_model_conflicts() -> None:
    from benchmark_reference.long_context import extract_metadata

    source = Source(Path("test.jsonl"), 1)
    sample = SampleResult(
        "aa_lcr",
        "a",
        "default",
        0,
        "acc",
        1.0,
        {
            "sample_metadata": {
                "input_tokens": 100,
                "data_source_urls": "b;a;a",
                "question": "q",
                "model_specific": "a",
            }
        },
        source,
        source,
    )
    other = replace(
        sample,
        model="b",
        metadata={
            "sample_metadata": {
                "input_tokens": 100,
                "data_source_urls": "a;b",
                "question": "q",
                "model_specific": "b",
            }
        },
    )
    assert extract_metadata([sample, other]) == {0: TaskMetadata(100, ("a", "b"))}
    conflict = replace(
        other,
        metadata={
            "sample_metadata": {"input_tokens": 101, "data_source_urls": "a;b", "question": "q"}
        },
    )
    with pytest.raises(AnalysisError, match="Cross-model benchmark metadata conflict"):
        extract_metadata([sample, conflict])


def test_flip_bounds_match_exhaustive_changes_of_an_unequal_weight_subset() -> None:
    from itertools import combinations

    from benchmark_reference.judge_noise import flip_envelope
    from benchmark_reference.pruning import SelectedSample

    selection = tuple(
        SelectedSample(i, w, str(i), 1, 1) for i, w in enumerate((0.1, 0.2, 0.3, 0.4))
    )
    grades = {0: 1.0, 1: 0.0, 2: 1.0, 3: 0.0}
    for budget in range(5):
        estimates = []
        for size in range(budget + 1):
            for flipped in combinations(range(4), size):
                estimates.append(
                    sum(
                        x.weight * (1 - grades[x.index] if x.index in flipped else grades[x.index])
                        for x in selection
                    )
                )
        assert flip_envelope(selection, grades, flip_count=budget) == pytest.approx(
            (min(estimates), max(estimates))
        )


@pytest.mark.parametrize("names", [(), ("uniform_random",), ("custom", "custom"), ("",)])
def test_evaluators_reject_invalid_candidate_registration(names: tuple[str, ...]) -> None:
    from benchmark_reference.pruning import select_baseline

    scores = {model: {0: 0.0, 1: 1.0} for model in ("a", "b", "c")}
    for evaluate in (evaluate_experiment, evaluate_pair_transfer):
        with pytest.raises(AnalysisError, match="Candidate strategies"):
            evaluate(
                scores,
                keep_ratios=(1,),
                seeds=(0,),
                candidate_strategies=names,
                candidate_selector=select_baseline,
            )
