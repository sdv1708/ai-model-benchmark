"""Behavior tests for the benchmark reference pipeline and issue #14 acceptance."""

import json
from pathlib import Path

import pytest

from benchmark_reference.analysis import aggregate_samples, analyze_pair
from benchmark_reference.inputs import (
    MMMU_MODEL,
    MMMU_SUBJECTS,
    discover_pairs,
    index_rows,
    read_jsonl,
)
from benchmark_reference.models import (
    AnalysisError,
    FilePair,
    JsonlRow,
    JsonValue,
    Metric,
    SampleResult,
    Source,
)
from benchmark_reference.reporting import write_outputs


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """Write ``rows`` as UTF-8 JSONL, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_pair(
    tmp_path: Path, *, metric: Metric = "pass", benchmark: str = "live_code_bench_v5"
) -> FilePair:
    """Build a 2-sample FilePair for ``fixture-model`` under ``tmp_path``."""
    return FilePair(
        benchmark=benchmark,
        model="fixture-model",
        subset="default",
        metric=metric,
        expected_samples=2,
        predictions=tmp_path / "predictions.jsonl",
        reviews=tmp_path / "reviews.jsonl",
    )


def pred(index: object, model: str = "fixture-model", **extra: object) -> dict[str, object]:
    """Return a valid prediction row; ``extra`` overrides or adds fields."""
    return {"index": index, "model": model, "metadata": {}, "model_output": {"error": None}} | extra


def review(
    index: object, value: object = 1.0, metric: str = "pass", **score: object
) -> dict[str, object]:
    """Return a valid review row scoring ``value`` on ``metric``; ``score`` adds score fields."""
    return {
        "index": index,
        "sample_score": {"score": {"value": {metric: value}, "main_score_name": metric} | score},
    }


def write_valid(pair: FilePair) -> None:
    """Write shuffled predictions and ordered reviews scoring index 0 => 1, index 1 => 0."""
    write_jsonl(pair.predictions, [pred(1), pred(0)])
    write_jsonl(pair.reviews, [review(0, 1.0, pair.metric), review(1, 0.0, pair.metric)])


# ---------- JSONL parsing ----------


def test_reader_preserves_source_line(tmp_path: Path) -> None:
    """Rows keep their file order and one-based source line numbers."""
    path = tmp_path / "input.jsonl"
    write_jsonl(path, [{"index": 8}, {"index": 3}])
    rows = list(read_jsonl(path))
    assert [row.value["index"] for row in rows] == [8, 3]
    assert [row.source for row in rows] == [Source(path, 1), Source(path, 2)]


@pytest.mark.parametrize("content", ['{"index":\n', "[]\n", "\n", '{"index": NaN}\n'])
def test_reader_rejects_invalid_records(tmp_path: Path, content: str) -> None:
    """Malformed JSON, non-objects, blank lines and NaN fail with file and line."""
    path = tmp_path / "broken.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AnalysisError) as exc:
        list(read_jsonl(path))
    assert path.name in str(exc.value)
    assert ":1" in str(exc.value)


def test_reader_rejects_lfs_pointer(tmp_path: Path) -> None:
    """A Git LFS pointer is reported as such instead of as bad JSON."""
    path = tmp_path / "pointer.jsonl"
    path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:ab\nsize 1\n")
    with pytest.raises(AnalysisError, match="LFS"):
        list(read_jsonl(path))


def test_reader_reports_missing_file_and_bad_encoding(tmp_path: Path) -> None:
    """Unreadable files and non-UTF-8 bytes become AnalysisErrors."""
    with pytest.raises(AnalysisError, match="Cannot read"):
        list(read_jsonl(tmp_path / "nope.jsonl"))
    bad = tmp_path / "latin.jsonl"
    bad.write_bytes(b'{"a": "\xff"}\n')
    with pytest.raises(AnalysisError, match="UTF-8"):
        list(read_jsonl(bad))


@pytest.mark.parametrize(
    "content",
    ['{"index": 0, "index": 1}\n', '{"nested": {"score": 0, "score": 1}}\n', '{"x": 1e999}\n'],
)
def test_reader_rejects_ambiguous_keys_and_numeric_overflow(tmp_path: Path, content: str) -> None:
    path = tmp_path / "ambiguous.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AnalysisError, match=r"duplicate JSON key|non-finite JSON number"):
        list(read_jsonl(path))


def test_invalid_utf8_names_the_exact_line(tmp_path: Path) -> None:
    path = tmp_path / "encoding.jsonl"
    path.write_bytes(b'{"index": 0}\n{"index": 1}\n{"bad": "\xff"}\n')
    with pytest.raises(AnalysisError, match=r":3: not valid UTF-8"):
        list(read_jsonl(path))


# ---------- Index validation ----------


def rows_for(path: Path, indices: list[JsonValue]) -> list[JsonlRow]:
    """Build JsonlRows with the given index values on consecutive lines."""
    return [JsonlRow(Source(path, n), {"index": i}) for n, i in enumerate(indices, start=1)]


def test_duplicate_indices_are_not_overwritten(tmp_path: Path) -> None:
    """A repeated index raises instead of silently replacing the first row."""
    with pytest.raises(AnalysisError, match="Duplicate index 4"):
        index_rows(rows_for(tmp_path / "input.jsonl", [4, 4]), expected_samples=2)


@pytest.mark.parametrize("bad", [True, -1, "1", 1.5, None])
def test_invalid_indices_are_rejected(tmp_path: Path, bad: JsonValue) -> None:
    """Booleans, negatives, strings, floats and null are not valid indices."""
    with pytest.raises(AnalysisError, match="index"):
        index_rows(rows_for(tmp_path / "x.jsonl", [0, bad]), expected_samples=2)


def test_wrong_count_is_rejected(tmp_path: Path) -> None:
    """Fewer rows than the contract expects is an error, not a smaller run."""
    with pytest.raises(AnalysisError, match="expected 3 samples, found 2"):
        index_rows(rows_for(tmp_path / "x.jsonl", [0, 1]), expected_samples=3)


def test_index_rows_returns_sorted_lookup(tmp_path: Path) -> None:
    """The lookup is ordered by index regardless of file order."""
    result = index_rows(rows_for(tmp_path / "x.jsonl", [5, 2]), expected_samples=2)
    assert list(result) == [2, 5]


# ---------- Joins and normalization ----------


def test_shuffled_files_join_by_index_and_keep_identity(tmp_path: Path) -> None:
    """Shuffled files join by index and keep identity, source lines and empty metadata."""
    pair = make_pair(tmp_path)
    write_valid(pair)
    samples = analyze_pair(pair)
    assert [(sample.index, sample.score) for sample in samples] == [(0, 1.0), (1, 0.0)]
    assert all(
        sample.model == pair.model and sample.benchmark == pair.benchmark for sample in samples
    )
    assert samples[0].prediction_source.line == 2
    assert samples[0].review_source.line == 1
    assert samples[0].metadata == {}


def test_equal_counts_do_not_hide_mismatched_indices(tmp_path: Path) -> None:
    """Same row count but different index sets fails, naming the unmatched index."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0), pred(1)])
    write_jsonl(pair.reviews, [review(0), review(2)])
    with pytest.raises(AnalysisError, match=r"predictions with no review: \[1\]"):
        analyze_pair(pair)


def test_offset_review_indices_join_by_index(tmp_path: Path) -> None:
    """AA-LCR style non-zero starting indices still join correctly."""
    pair = make_pair(tmp_path, metric="acc", benchmark="aa_lcr")
    write_jsonl(pair.predictions, [pred(73), pred(74)])
    write_jsonl(pair.reviews, [review(74, 0.0, "acc"), review(73, 1.0, "acc")])
    assert [(s.index, s.score) for s in analyze_pair(pair)] == [(73, 1.0), (74, 0.0)]


def test_missing_partner_files_are_distinguished(tmp_path: Path) -> None:
    """A missing reviews file and a missing predictions file give different errors."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0), pred(1)])
    with pytest.raises(AnalysisError, match="reviews file invalid"):
        analyze_pair(pair)
    pair.predictions.unlink()
    write_jsonl(pair.reviews, [review(0), review(1)])
    with pytest.raises(AnalysisError, match="predictions file invalid"):
        analyze_pair(pair)


def test_wrong_prediction_model_is_rejected(tmp_path: Path) -> None:
    """Predictions from a different model than the pair expects are refused."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0, "other-model"), pred(1)])
    write_jsonl(pair.reviews, [review(0), review(1)])
    with pytest.raises(AnalysisError, match="other-model"):
        analyze_pair(pair)


def test_boolean_index_in_file_is_rejected(tmp_path: Path) -> None:
    """A JSON ``true`` index in a prediction file is rejected during the join."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(True), pred(1)])
    write_jsonl(pair.reviews, [review(0), review(1)])
    with pytest.raises(AnalysisError, match="index"):
        analyze_pair(pair)


@pytest.mark.parametrize(
    "bad_review",
    [
        {"index": 0},  # no sample_score
        {"index": 0, "sample_score": {"score": {"value": {}, "main_score_name": "pass"}}},
        review(0, True),  # boolean score
        review(0, 0.5),  # non-binary
        review(0, float("nan")),  # rejected by the reader (NaN literal)
        review(0, "1"),  # string score
        review(0, 1.0, "acc"),  # wrong metric name
        {"index": 0, "sample_score": "oops"},  # malformed nested object
    ],
)
def test_invalid_scores_are_rejected(tmp_path: Path, bad_review: dict[str, object]) -> None:
    """Absent, boolean, non-binary, non-numeric or malformed scores fail validation."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0), pred(1)])
    write_jsonl(pair.reviews, [bad_review, review(1)])
    with pytest.raises(AnalysisError):
        analyze_pair(pair)


def test_generation_error_is_surfaced(tmp_path: Path) -> None:
    """A non-empty model_output.error is reported, not scored or dropped."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0, model_output={"error": "timeout"}), pred(1)])
    write_jsonl(pair.reviews, [review(0), review(1)])
    with pytest.raises(AnalysisError, match=r"generation error.*timeout"):
        analyze_pair(pair)


@pytest.mark.parametrize("metadata", [False, [], "", 0])
def test_falsey_non_object_metadata_is_invalid(tmp_path: Path, metadata: object) -> None:
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0, metadata=metadata), pred(1)])
    write_jsonl(pair.reviews, [review(0), review(1)])
    with pytest.raises(AnalysisError, match=r"metadata.*must be an object"):
        analyze_pair(pair)


def test_judge_metadata_must_be_an_object(tmp_path: Path) -> None:
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0), pred(1)])
    write_jsonl(pair.reviews, [review(0, metadata=[]), review(1)])
    with pytest.raises(AnalysisError, match=r"judge metadata.*must be an object"):
        analyze_pair(pair)


def test_extremely_large_score_is_a_validation_error(tmp_path: Path) -> None:
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0), pred(1)])
    write_jsonl(pair.reviews, [review(0, 10**500), review(1)])
    with pytest.raises(AnalysisError, match="exactly 0 or 1"):
        analyze_pair(pair)


def test_aa_lcr_metadata_and_judge_are_kept(tmp_path: Path) -> None:
    """AA-LCR sample metadata and judge metadata are kept under documented names."""
    pair = make_pair(tmp_path, metric="acc", benchmark="aa_lcr")
    write_jsonl(
        pair.predictions,
        [pred(0, metadata={"question": "Q?"}), pred(1, metadata={"question": "R?"})],
    )
    write_jsonl(
        pair.reviews,
        [
            {
                "index": i,
                "sample_score": {
                    "score": {
                        "value": {"acc": 1.0},
                        "main_score_name": "acc",
                        "metadata": {"source": "llm_judge"},
                    },
                    "sample_id": str(i),
                    "sample_metadata": {"question": "Q?" if i == 0 else "R?"},
                },
            }
            for i in (0, 1)
        ],
    )
    first = analyze_pair(pair)[0]
    assert first.metadata == {
        "sample_metadata": {"question": "Q?"},
        "judge_metadata": {"source": "llm_judge"},
    }


def test_metadata_conflict_is_rejected(tmp_path: Path) -> None:
    """Prediction and review metadata that disagree on a key raise an error."""
    pair = make_pair(tmp_path)
    write_jsonl(pair.predictions, [pred(0, metadata={"q": "a"}), pred(1)])
    rev: dict[str, object] = {
        "index": 0,
        "sample_score": {
            "score": {"value": {"pass": 1}, "main_score_name": "pass"},
            "sample_metadata": {"q": "b"},
        },
    }
    write_jsonl(pair.reviews, [rev, review(1)])
    with pytest.raises(AnalysisError, match="conflict"):
        analyze_pair(pair)


# ---------- Full-data aggregation ----------


def sample(
    index: int,
    score: float,
    *,
    benchmark: str = "aa_lcr",
    model: str = "fixture-model",
    subset: str = "default",
    metric: Metric = "acc",
) -> SampleResult:
    """Build a SampleResult directly, bypassing file validation."""
    return SampleResult(
        benchmark=benchmark,
        model=model,
        subset=subset,
        index=index,
        metric=metric,
        score=score,
        metadata={},
        prediction_source=Source(Path("predictions.jsonl"), index + 1),
        review_source=Source(Path("reviews.jsonl"), index + 1),
    )


def test_full_score_uses_every_sample() -> None:
    """[1, 0, 1, 1] gives count 4, sum 3 and mean 0.75."""
    summaries = aggregate_samples([sample(i, s) for i, s in enumerate([1.0, 0.0, 1.0, 1.0])])
    assert len(summaries) == 1
    assert summaries[0].sample_count == 4
    assert summaries[0].score_sum == 3.0
    assert summaries[0].mean_score == 0.75


def test_groups_stay_separate_and_sorted() -> None:
    """Models and benchmarks aggregate separately and come out in identity order."""
    summaries = aggregate_samples(
        [
            sample(0, 1.0, model="b"),
            sample(0, 0.0, model="a"),
            sample(0, 1.0, benchmark="live_code_bench_v5", metric="pass"),
            sample(1, 1.0, model="a"),
        ]
    )
    assert [(s.benchmark, s.model, s.mean_score) for s in summaries] == [
        ("aa_lcr", "a", 0.5),
        ("aa_lcr", "b", 1.0),
        ("live_code_bench_v5", "fixture-model", 1.0),
    ]


def test_same_index_in_different_subsets_is_not_a_duplicate() -> None:
    """MMMU indices restart per subject, so identity includes the subset."""
    samples = [sample(0, 1.0, subset="Art"), sample(0, 0.0, subset="Biology")]
    assert len(aggregate_samples(samples)) == 2


@pytest.mark.parametrize(
    "samples",
    [
        [],
        [sample(0, 1.0), sample(0, 0.0)],  # duplicate identity
        [sample(0, 1.0), sample(1, 1.0, metric="pass")],  # inconsistent metric
        [sample(0, 2.0)],  # invalid score
        [sample(0, float("nan"))],
        [sample(-1, 1.0)],
    ],
)
def test_aggregate_rejects_invalid_input(samples: list[SampleResult]) -> None:
    """Empty input, duplicates, mixed metrics and invalid scores/indices are errors."""
    with pytest.raises(AnalysisError):
        aggregate_samples(samples)


# ---------- Input inventory ----------


def build_inventory(root: Path) -> None:
    """Create empty files with the exact shipped Evals/ names and layout."""
    for kind in ("predictions", "reviews"):
        (root / "Part 1" / kind).mkdir(parents=True)
        for benchmark in ("aa_lcr", "live_code_bench_v5"):
            for model in ("gpt-oss-120b", "kimi-k2.5", "minimax-m2.5"):
                (root / "Part 1" / kind / f"{benchmark}__{model}.jsonl").touch()
        (root / "MMMU" / kind / MMMU_MODEL).mkdir(parents=True)
        for subject in MMMU_SUBJECTS:
            (root / "MMMU" / kind / MMMU_MODEL / f"mmmu_{subject}.jsonl").touch()


def test_discovery_inventory(tmp_path: Path) -> None:
    """28 pairs: 6 Part A reference pairs plus 22 MMMU pairs, in a stable order."""
    build_inventory(tmp_path)
    pairs = discover_pairs(tmp_path)
    assert len(pairs) == 28
    assert sum(p.include_in_reference for p in pairs) == 6
    assert [p.benchmark for p in pairs[:3]] == ["aa_lcr"] * 3
    assert {p.expected_samples for p in pairs if p.benchmark == "live_code_bench_v5"} == {315}
    assert pairs == discover_pairs(tmp_path)


def test_discovery_rejects_missing_partner_orphan_and_missing_dir(tmp_path: Path) -> None:
    """A missing partner, an unexpected file and a missing directory all fail."""
    build_inventory(tmp_path)
    victim = tmp_path / "Part 1" / "reviews" / "aa_lcr__kimi-k2.5.jsonl"
    victim.unlink()
    with pytest.raises(AnalysisError, match="missing files"):
        discover_pairs(tmp_path)
    victim.touch()
    (tmp_path / "MMMU" / "reviews" / MMMU_MODEL / "mmmu_Extra.jsonl").touch()
    with pytest.raises(AnalysisError, match="unexpected entries"):
        discover_pairs(tmp_path)
    with pytest.raises(AnalysisError, match="Missing input directory"):
        discover_pairs(tmp_path / "does-not-exist")


# ---------- Report publication ----------


def test_reports_are_byte_identical_and_traceable(tmp_path: Path) -> None:
    """Two runs write identical bytes; sources and hashes trace each score to its inputs."""
    data = tmp_path / "data"
    pair = FilePair(
        benchmark="aa_lcr",
        model="fixture-model",
        subset="default",
        metric="acc",
        expected_samples=2,
        predictions=data / "predictions.jsonl",
        reviews=data / "reviews.jsonl",
    )
    write_jsonl(pair.predictions, [pred(1), pred(0)])
    write_jsonl(pair.reviews, [review(0, 1.0, "acc"), review(1, 0.0, "acc")])
    samples = analyze_pair(pair)
    summaries = aggregate_samples(samples)

    for name in ("run1", "run2"):
        write_outputs(
            tmp_path / name, data_root=data, pairs=[pair], samples=samples, summaries=summaries
        )
    for name in ("samples.jsonl", "full_scores.json", "manifest.json"):
        assert (tmp_path / "run1" / name).read_bytes() == (tmp_path / "run2" / name).read_bytes()

    manifest = json.loads((tmp_path / "run1" / "manifest.json").read_text(encoding="utf-8"))
    assert {i["path"] for i in manifest["inputs"]} == {"predictions.jsonl", "reviews.jsonl"}
    assert all(len(i["sha256"]) == 64 and i["rows"] == 2 for i in manifest["inputs"])
    first = json.loads((tmp_path / "run1" / "samples.jsonl").read_text("utf-8").splitlines()[0])
    assert first["prediction_source"] == {"path": "predictions.jsonl", "line": 2}
    assert first["review_source"] == {"path": "reviews.jsonl", "line": 1}


def test_report_rejects_incorrect_summary(tmp_path: Path) -> None:
    from dataclasses import replace

    pair = make_pair(tmp_path / "data")
    write_valid(pair)
    samples = analyze_pair(pair)
    wrong_summary = replace(aggregate_samples(samples)[0], mean_score=1.0)
    with pytest.raises(AnalysisError, match="summaries do not match"):
        write_outputs(
            tmp_path / "output",
            data_root=tmp_path / "data",
            pairs=[pair],
            samples=samples,
            summaries=[wrong_summary],
        )
    assert not (tmp_path / "output").exists()


def test_report_writer_protects_input_directory(tmp_path: Path) -> None:
    pair = make_pair(tmp_path / "data")
    write_valid(pair)
    samples = analyze_pair(pair)
    with pytest.raises(AnalysisError, match="inside the input data"):
        write_outputs(
            tmp_path / "data" / "reports",
            data_root=tmp_path / "data",
            pairs=[pair],
            samples=samples,
            summaries=aggregate_samples(samples),
        )


def test_write_outputs_rejects_count_mismatch_without_writing(tmp_path: Path) -> None:
    """A pair whose validated sample count differs from expected writes no report."""
    data = tmp_path / "data"
    pair = FilePair(
        benchmark="aa_lcr",
        model="fixture-model",
        subset="default",
        metric="acc",
        expected_samples=3,
        predictions=data / "predictions.jsonl",
        reviews=data / "reviews.jsonl",
    )
    samples = [sample(0, 1.0), sample(1, 0.0)]
    with pytest.raises(AnalysisError, match="expected 3"):
        write_outputs(
            tmp_path / "out",
            data_root=data,
            pairs=[pair],
            samples=samples,
            summaries=aggregate_samples(samples),
        )
    assert not (tmp_path / "out").exists()
