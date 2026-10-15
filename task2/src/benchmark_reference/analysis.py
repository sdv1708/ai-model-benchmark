"""Normalize validated samples and aggregate complete recorded scores."""

import math
from collections.abc import Sequence

from benchmark_reference.inputs import format_source, join_rows, row_index
from benchmark_reference.models import (
    AnalysisError,
    BenchmarkSummary,
    FilePair,
    JsonlRow,
    JsonValue,
    Metric,
    SampleResult,
)


def _object(value: JsonValue | None, what: str, row: JsonlRow) -> dict[str, JsonValue]:
    """Return ``value`` if it is a JSON object, else raise AnalysisError naming ``what``."""
    if not isinstance(value, dict):
        raise AnalysisError(f"{format_source(row.source)}: '{what}' must be an object")
    return value


def _validate_score(raw: object, where: str) -> float:
    """Binary scores only: reject bool, non-numbers, NaN/inf, and anything but 0 or 1."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise AnalysisError(f"{where}: score must be a number, got {raw!r}")
    if raw not in (0, 1) or not math.isfinite(raw):
        raise AnalysisError(f"{where}: score must be exactly 0 or 1, got {raw!r}")
    return float(raw)


def _optional_object(value: JsonValue | None, what: str, row: JsonlRow) -> dict[str, JsonValue]:
    """Absent/null metadata is empty; other non-object values are invalid."""
    return {} if value is None else _object(value, what, row)


def normalize_sample(pair: FilePair, prediction: JsonlRow, review: JsonlRow) -> SampleResult:
    """Turn one joined prediction/review row pair into a validated SampleResult.

    Checks identity (matching index, expected model), surfaces generation errors, and
    reads ``sample_score.score.value[pair.metric]`` as a finite binary 0/1 score
    (``main_score_name`` is checked only when set; MMMU leaves it null).

    Metadata policy (keys omitted when empty):
      "sample_metadata": prediction ``metadata`` merged with review
          ``sample_score.sample_metadata``; differing values for one key raise
          AnalysisError (the shipped data has no conflicts).
      "judge_metadata": ``sample_score.score.metadata`` (judge model/strategy).
    Nothing is invented: empty coding metadata stays empty.
    """
    pred_where = format_source(prediction.source)
    review_where = format_source(review.source)

    # Identity: both rows must be the same sample, and the prediction the right model.
    index = row_index(prediction)
    if row_index(review) != index:
        raise AnalysisError(f"{pred_where} / {review_where}: index mismatch")
    if prediction.value.get("model") != pair.model:
        raise AnalysisError(
            f"{pred_where}: prediction model {prediction.value.get('model')!r} != {pair.model!r}"
        )

    # Generation errors must never silently become a 0 (or a dropped row).
    model_output = _object(prediction.value.get("model_output"), "model_output", prediction)
    if error := model_output.get("error"):
        raise AnalysisError(f"{pred_where}: generation error for index {index}: {error!r}")

    # Review: sample_score -> score -> value -> {metric: 0/1}
    sample_score = _object(review.value.get("sample_score"), "sample_score", review)
    score_obj = _object(sample_score.get("score"), "sample_score.score", review)
    values = _object(score_obj.get("value"), "sample_score.score.value", review)

    # main_score_name is null in MMMU reviews, so only check it when set.
    main_name = score_obj.get("main_score_name")
    if main_name is not None and main_name != pair.metric:
        raise AnalysisError(
            f"{review_where}: main_score_name {main_name!r} != expected {pair.metric!r}"
        )
    if pair.metric not in values:
        raise AnalysisError(
            f"{review_where}: metric {pair.metric!r} missing from score values {sorted(values)}"
        )
    score = _validate_score(values[pair.metric], review_where)

    if "sample_id" in sample_score and str(sample_score["sample_id"]) != str(index):
        raise AnalysisError(
            f"{review_where}: sample_id {sample_score['sample_id']!r} != index {index}"
        )

    # Metadata: merge, refusing silent conflicts.
    sample_metadata: dict[str, JsonValue] = {}
    pred_meta = _optional_object(prediction.value.get("metadata"), "metadata", prediction)
    review_meta = _optional_object(sample_score.get("sample_metadata"), "sample_metadata", review)
    sample_metadata.update(pred_meta)
    for key, value in review_meta.items():
        if key in sample_metadata and sample_metadata[key] != value:
            raise AnalysisError(
                f"{pred_where} / {review_where}: metadata conflict on {key!r} for index {index}"
            )
        sample_metadata[key] = value

    metadata: dict[str, JsonValue] = {}
    if sample_metadata:
        metadata["sample_metadata"] = sample_metadata
    judge_metadata = _optional_object(score_obj.get("metadata"), "judge metadata", review)
    if judge_metadata:
        metadata["judge_metadata"] = judge_metadata

    return SampleResult(
        benchmark=pair.benchmark,
        model=pair.model,
        subset=pair.subset,
        index=index,
        metric=pair.metric,
        score=score,
        metadata=metadata,
        prediction_source=prediction.source,
        review_source=review.source,
    )


def analyze_pair(pair: FilePair) -> tuple[SampleResult, ...]:
    """Compose join_rows and normalize_sample; keep sorted identity."""
    return tuple(normalize_sample(pair, pred, review) for pred, review in join_rows(pair))


def aggregate_samples(samples: Sequence[SampleResult]) -> tuple[BenchmarkSummary, ...]:
    """Group samples by benchmark/model/subset and report count, sum and mean score.

    Every sample is weighted equally on a 0..1 scale. Rejects empty input, duplicate
    sample identities, inconsistent metrics and invalid scores (even for hand-built
    SampleResults). Summaries are sorted by identity; no pass@k or combined score.
    """
    if not samples:
        raise AnalysisError("Cannot aggregate: no samples")

    seen: set[tuple[str, str, str, int]] = set()
    metric_of: dict[tuple[str, str, str], Metric] = {}
    scores: dict[tuple[str, str, str], list[float]] = {}

    for sample in samples:
        group = (sample.benchmark, sample.model, sample.subset)
        identity = (*group, sample.index)
        where = f"{'/'.join(group)}#{sample.index}"
        if isinstance(sample.index, bool) or not isinstance(sample.index, int) or sample.index < 0:
            raise AnalysisError(f"{where}: invalid sample index {sample.index!r}")
        if identity in seen:
            raise AnalysisError(f"Duplicate sample identity {where}")
        seen.add(identity)
        if sample.metric not in ("pass", "acc"):
            raise AnalysisError(f"{where}: unsupported metric {sample.metric!r}")
        if metric_of.setdefault(group, sample.metric) != sample.metric:
            raise AnalysisError(
                f"{'/'.join(group)}: inconsistent metrics {metric_of[group]!r} vs {sample.metric!r}"
            )
        scores.setdefault(group, []).append(_validate_score(sample.score, where))

    return tuple(
        BenchmarkSummary(
            benchmark=group[0],
            model=group[1],
            subset=group[2],
            metric=metric_of[group],
            sample_count=len(values),
            score_sum=math.fsum(values),
            mean_score=math.fsum(values) / len(values),
        )
        for group, values in sorted(scores.items())
    )
