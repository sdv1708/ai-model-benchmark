"""Token counts for each saved answer and the cost estimate for an unseen model."""

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import load_reference_panel
from benchmark_reference.threshold_tokens import (
    MissingCount,
    TokenCount,
    TokenTable,
    estimate_question_costs,
    load_token_counts,
)

TASK2 = Path(__file__).parents[1]
EVALS = TASK2.parent / "Evals"
MODELS = ("a", "b", "c")


def _usage(input_tokens: object, output_tokens: object) -> dict[str, object]:
    return {"usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}


def _write_predictions(root: Path, rows: dict[str, list[dict[str, object]]]) -> dict[str, str]:
    """Write one predictions file for each model; return the panel's source hashes."""
    folder = root / "Part 1" / "predictions"
    folder.mkdir(parents=True)
    hashes = {}
    for model, items in rows.items():
        name = f"bench__{model}.jsonl"
        data = "".join(json.dumps({"model": model, **item}) + "\n" for item in items)
        (folder / name).write_bytes(data.encode("utf-8"))
        hashes[f"Part 1/predictions/{name}"] = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return hashes


def _row(index: int, input_tokens: object, output_tokens: object) -> dict[str, object]:
    return {"index": index, "model_output": _usage(input_tokens, output_tokens)}


def _complete(root: Path) -> dict[str, str]:
    return _write_predictions(
        root,
        {
            "a": [_row(0, 10, 90), _row(1, 20, 5)],
            "b": [_row(0, 12, 300), _row(1, 18, 7)],
            "c": [_row(0, 11, 30), _row(1, 22, 3)],
        },
    )


def _load(root: Path, hashes: dict[str, str]) -> TokenTable:
    return load_token_counts(
        root, benchmark="bench", models=MODELS, questions=(0, 1), source_sha256=hashes
    )


def test_loader_reads_input_and_output_tokens_for_each_saved_answer(tmp_path: Path) -> None:
    table = _load(tmp_path, _complete(tmp_path))
    assert table.counts["a"] == {0: TokenCount(10, 90), 1: TokenCount(20, 5)}
    assert table.counts["b"][0] == TokenCount(12, 300)
    assert table.counts["c"][1].total == 25
    assert table.missing == ()
    assert set(table.files) == {f"Part 1/predictions/bench__{m}.jsonl" for m in MODELS}


def test_question_cost_is_the_low_mean_and_high_across_reference_models(tmp_path: Path) -> None:
    costs = estimate_question_costs(_load(tmp_path, _complete(tmp_path)))
    # Question 0 totals: a 100, b 312, c 41.
    assert (costs[0].low, costs[0].mean, costs[0].high) == (41, Fraction(453, 3), 312)
    # Question 1 totals: a 25, b 25, c 25.
    assert (costs[1].low, costs[1].mean, costs[1].high) == (25, Fraction(25), 25)
    assert costs[0].input_mean == Fraction(11)
    assert costs[0].output_mean == Fraction(420, 3)
    assert costs[0].models == 3


def test_missing_counts_are_reported_and_never_treated_as_zero(tmp_path: Path) -> None:
    hashes = _write_predictions(
        tmp_path,
        {
            # a: answer 0 has a null model_output; answer 1 has a null usage record.
            "a": [
                {"index": 0, "model_output": None},
                {"index": 1, "model_output": {"usage": None}},
            ],
            # b: answer 0 has a null output count; answer 1 is absent from the file.
            "b": [_row(0, 12, None)],
            # c: answer 1 has no input_tokens key.
            "c": [_row(0, 11, 30), {"index": 1, "model_output": {"usage": {"output_tokens": 3}}}],
        },
    )
    table = _load(tmp_path, hashes)
    assert table.missing == (
        MissingCount("a", 0, "input_tokens"),
        MissingCount("a", 0, "output_tokens"),
        MissingCount("a", 1, "input_tokens"),
        MissingCount("a", 1, "output_tokens"),
        MissingCount("b", 0, "output_tokens"),
        MissingCount("b", 1, "answer"),
        MissingCount("c", 1, "input_tokens"),
    )
    # No model has both counts for question 1, so its cost cannot be estimated.
    with pytest.raises(AnalysisError, match="question 1"):
        estimate_question_costs(table)
    assert set(table.counts["a"]) == set()
    assert set(table.counts["b"]) == set()
    assert set(table.counts["c"]) == {0}


def test_estimate_uses_only_the_models_with_a_count(tmp_path: Path) -> None:
    hashes = _write_predictions(
        tmp_path,
        {
            "a": [_row(0, 10, 90), _row(1, 20, 5)],
            "b": [_row(0, 12, None), _row(1, 18, 7)],
            "c": [_row(0, 11, 30), _row(1, 22, 3)],
        },
    )
    cost = estimate_question_costs(_load(tmp_path, hashes))[0]
    # A zero for b would give low 12 and mean 153 / 3 = 51. The estimate uses a and c.
    assert (cost.low, cost.mean, cost.high, cost.models) == (41, Fraction(141, 2), 100, 2)


def test_a_prediction_file_that_differs_from_the_panel_source_is_rejected(
    tmp_path: Path,
) -> None:
    hashes = _complete(tmp_path)
    hashes["Part 1/predictions/bench__b.jsonl"] = "0" * 64
    with pytest.raises(AnalysisError, match="SHA-256"):
        _load(tmp_path, hashes)
    del hashes["Part 1/predictions/bench__b.jsonl"]
    with pytest.raises(AnalysisError, match="does not record"):
        _load(tmp_path, hashes)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (_row(0, -1, 90), "input_tokens"),
        (_row(0, "10", 90), "input_tokens"),
        (_row(0, 10, True), "output_tokens"),
        (_row(0, 10, 9.5), "output_tokens"),
        (
            {
                "index": 0,
                "model_output": {
                    "usage": {"input_tokens": 10, "output_tokens": 90, "total_tokens": 99}
                },
            },
            "total_tokens",
        ),
        ({"index": 0, "model_output": {"usage": "none"}}, "usage"),
        ({"index": 0, "model_output": "text"}, "model_output"),
        (_row(7, 10, 90), "question 7"),
        ({"index": 0, "model": "z", "model_output": _usage(10, 90)}, "model"),
    ],
)
def test_invalid_counts_stop_loading(tmp_path: Path, row: dict[str, object], message: str) -> None:
    hashes = _write_predictions(
        tmp_path, {"a": [row, _row(1, 20, 5)], "b": [_row(0, 1, 1)], "c": [_row(0, 1, 1)]}
    )
    with pytest.raises(AnalysisError, match=message):
        _load(tmp_path, hashes)


def test_a_repeated_answer_stops_loading(tmp_path: Path) -> None:
    hashes = _write_predictions(tmp_path, {"a": [_row(0, 1, 1), _row(0, 1, 1)], "b": [], "c": []})
    with pytest.raises(AnalysisError, match="repeats"):
        _load(tmp_path, hashes)


@pytest.mark.parametrize(
    ("panel", "benchmark", "low", "high", "everything"),
    [
        # Hand totals from the six committed prediction files, input plus output.
        ("lcb-reference-panel.json", "live_code_bench_v5", 1_555_578, 7_177_805, 13_596_984),
        ("aa-lcr-reference-panel.json", "aa_lcr", 9_445_718, 9_800_167, 28_848_604),
    ],
)
def test_committed_predictions_give_a_count_for_every_reference_answer(
    panel: str, benchmark: str, low: int, high: int, everything: int
) -> None:
    loaded = load_reference_panel(TASK2 / "data" / panel, benchmark=benchmark)
    table = load_token_counts(
        EVALS,
        benchmark=benchmark,
        models=tuple(sorted(loaded.references)),
        questions=tuple(sorted(next(iter(loaded.references.values())))),
        source_sha256=loaded.source_sha256,
    )
    assert table.missing == ()
    costs = estimate_question_costs(table)
    assert sum(c.low for c in costs.values()) == low
    assert sum(c.high for c in costs.values()) == high
    assert sum(c.mean for c in costs.values()) * 3 == everything
