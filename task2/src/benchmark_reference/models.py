"""Typed contracts for inputs, normalized samples, provenance, and summaries."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type Metric = Literal["pass", "acc"]


class AnalysisError(ValueError):
    """Invalid evaluation data; include source path and line/index in messages."""


@dataclass(frozen=True, slots=True)
class Source:
    """A one-based JSONL line number, distinct from the sample's index."""

    path: Path
    line: int


@dataclass(frozen=True, slots=True)
class JsonlRow:
    """Parsed object plus its location; semantic validation still follows."""

    source: Source
    value: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class FilePair:
    """One benchmark/model/subset pair and its expected data contract."""

    benchmark: str
    model: str
    subset: str
    metric: Metric
    expected_samples: int
    predictions: Path
    reviews: Path
    include_in_reference: bool = True


@dataclass(frozen=True, slots=True)
class SampleResult:
    """Identity includes subset: MMMU indices restart for each subject."""

    benchmark: str
    model: str
    subset: str
    index: int
    metric: Metric
    score: float
    metadata: dict[str, JsonValue]
    prediction_source: Source
    review_source: Source


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """A mean on the recorded complete run, on a 0..1 scale."""

    benchmark: str
    model: str
    subset: str
    metric: Metric
    sample_count: int
    score_sum: float
    mean_score: float
