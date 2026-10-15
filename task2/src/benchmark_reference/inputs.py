"""Discover the supplied inventory, parse JSONL, and validate sample joins."""

import json
import math
from collections.abc import Iterator, Sequence
from pathlib import Path

from benchmark_reference.models import AnalysisError, FilePair, JsonlRow, JsonValue, Metric, Source

LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1"

PART_A_MODELS = ("gpt-oss-120b", "kimi-k2.5", "minimax-m2.5")
# (benchmark, metric, expected samples per model)
PART_A_BENCHMARKS: tuple[tuple[str, Metric, int], ...] = (
    ("aa_lcr", "acc", 100),
    ("live_code_bench_v5", "pass", 315),
)

MMMU_MODEL = "glm-4.5v-fp8"
MMMU_SAMPLES_PER_SUBJECT = 30
MMMU_SUBJECTS = (
    "Accounting", "Agriculture", "Architecture_and_Engineering", "Art", "Art_Theory",
    "Basic_Medical_Science", "Biology", "Chemistry", "Clinical_Medicine", "Computer_Science",
    "Design", "Diagnostics_and_Laboratory_Medicine", "Economics", "Electronics",
    "Energy_and_Power", "Finance", "Geography", "History", "Literature", "Manage",
    "Marketing", "Materials",
)  # fmt: skip


def format_source(source: Source) -> str:
    """Render a location as path:line for error messages."""
    return f"{source.path}:{source.line}"


def _check_directory(directory: Path, expected_names: set[str]) -> None:
    """Fail on a missing directory, missing files, or files nobody asked for."""
    if not directory.is_dir():
        raise AnalysisError(f"Missing input directory: {directory}")
    found = {entry.name for entry in directory.iterdir()}
    problems: list[str] = []
    if missing := sorted(expected_names - found):
        problems.append(f"missing files {missing}")
    if unexpected := sorted(found - expected_names):
        problems.append(f"unexpected entries {unexpected}")
    if problems:
        raise AnalysisError(f"Input inventory mismatch in {directory}: {'; '.join(problems)}")


def discover_pairs(data_root: Path) -> tuple[FilePair, ...]:
    """Inventory every shipped prediction/review file as a sorted tuple of FilePairs.

    Part A is 2 benchmarks x 3 models (subset ``default``); MMMU is 22 subject pairs of
    30 samples with ``include_in_reference=False``. Raises AnalysisError for missing
    directories, missing partners, or unexpected files, never an empty inventory.
    """
    _check_directory(data_root, {"Part 1", "MMMU"})
    _check_directory(data_root / "Part 1", {"predictions", "reviews"})
    _check_directory(data_root / "MMMU", {"predictions", "reviews"})
    part1 = data_root / "Part 1"
    mmmu = data_root / "MMMU"
    pairs: list[FilePair] = []

    part_a_names = {
        f"{benchmark}__{model}.jsonl"
        for benchmark, _, _ in PART_A_BENCHMARKS
        for model in PART_A_MODELS
    }
    _check_directory(part1 / "predictions", part_a_names)
    _check_directory(part1 / "reviews", part_a_names)
    for benchmark, metric, expected in PART_A_BENCHMARKS:
        for model in PART_A_MODELS:
            name = f"{benchmark}__{model}.jsonl"
            pairs.append(
                FilePair(
                    benchmark=benchmark,
                    model=model,
                    subset="default",
                    metric=metric,
                    expected_samples=expected,
                    predictions=part1 / "predictions" / name,
                    reviews=part1 / "reviews" / name,
                )
            )

    mmmu_names = {f"mmmu_{subject}.jsonl" for subject in MMMU_SUBJECTS}
    for kind in ("predictions", "reviews"):
        _check_directory(mmmu / kind, {MMMU_MODEL})  # no stray model folders
        _check_directory(mmmu / kind / MMMU_MODEL, mmmu_names)
    for subject in MMMU_SUBJECTS:
        name = f"mmmu_{subject}.jsonl"
        pairs.append(
            FilePair(
                benchmark="mmmu",
                model=MMMU_MODEL,
                subset=subject,
                metric="acc",
                expected_samples=MMMU_SAMPLES_PER_SUBJECT,
                predictions=mmmu / "predictions" / MMMU_MODEL / name,
                reviews=mmmu / "reviews" / MMMU_MODEL / name,
                include_in_reference=False,
            )
        )

    return tuple(sorted(pairs, key=lambda p: (p.benchmark, p.model, p.subset)))


def _reject_constant(token: str) -> JsonValue:
    """json.loads hook: refuse the non-standard NaN/Infinity/-Infinity literals."""
    raise ValueError(f"non-standard JSON constant {token}")


def _finite_float(token: str) -> float:
    """Reject overflow such as 1e999, which json.loads otherwise turns into inf."""
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number {token}")
    return value


def _unique_object(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Repeated object keys are ambiguous, even when their values agree."""
    value: dict[str, JsonValue] = {}
    for key, item in items:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def read_jsonl(path: Path) -> Iterator[JsonlRow]:
    """Stream JSONL objects as JsonlRow(source, value) with one-based line numbers.

    Raises AnalysisError (with path:line) for LFS pointers, blank lines, malformed
    JSON, non-object records, NaN/Infinity, bad UTF-8, or unreadable files.
    """
    line_number = 0
    try:
        with path.open("rb") as handle:
            for line_number, raw in enumerate(handle, start=1):
                where = f"{path}:{line_number}"
                try:
                    text = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError as exc:
                    raise AnalysisError(f"{where}: not valid UTF-8 ({exc.reason})") from exc
                if line_number == 1 and text.startswith(LFS_POINTER_PREFIX):
                    raise AnalysisError(
                        f"{where}: Git LFS pointer, not data; run `git lfs pull` from the repo root"
                    )
                if not text.strip():
                    raise AnalysisError(f"{where}: blank line in JSONL")
                try:
                    value = json.loads(
                        text,
                        parse_constant=_reject_constant,
                        parse_float=_finite_float,
                        object_pairs_hook=_unique_object,
                    )
                except json.JSONDecodeError as exc:
                    raise AnalysisError(
                        f"{where}: malformed JSON ({exc.msg}, col {exc.colno})"
                    ) from exc
                except ValueError as exc:  # raised by _reject_constant (NaN/Infinity)
                    raise AnalysisError(f"{where}: {exc}") from exc
                if not isinstance(value, dict):
                    raise AnalysisError(
                        f"{where}: expected a JSON object, got {type(value).__name__}"
                    )
                yield JsonlRow(source=Source(path, line_number), value=value)
    except OSError as exc:
        raise AnalysisError(f"Cannot read {path}: {exc.strerror or exc}") from exc


def row_index(row: JsonlRow) -> int:
    """Return the row's sample index, rejecting booleans and negative values."""
    value = row.value.get("index")
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisError(
            f"{format_source(row.source)}: 'index' must be an integer, got {value!r}"
        )
    if value < 0:
        raise AnalysisError(f"{format_source(row.source)}: 'index' must be >= 0, got {value}")
    return value


def index_rows(rows: Sequence[JsonlRow], *, expected_samples: int) -> dict[int, JsonlRow]:
    """Index rows by sample index, returned in ascending index order.

    Rejects non-integer/boolean/negative indices, duplicates (before any overwrite),
    and a row count different from ``expected_samples``.
    """
    if isinstance(expected_samples, bool) or expected_samples <= 0:
        raise AnalysisError("Expected sample count must be positive")
    indexed: dict[int, JsonlRow] = {}
    for row in rows:
        index = row_index(row)
        if index in indexed:  # check BEFORE inserting so nothing is overwritten
            raise AnalysisError(
                f"Duplicate index {index} at {format_source(indexed[index].source)} "
                f"and {format_source(row.source)}"
            )
        indexed[index] = row
    if len(indexed) != expected_samples:
        location = rows[0].source.path if rows else "input"
        raise AnalysisError(
            f"{location}: expected {expected_samples} samples, found {len(indexed)}"
        )
    return dict(sorted(indexed.items()))


def _load(path: Path, role: str, expected_samples: int) -> dict[int, JsonlRow]:
    """Read and index one file, prefixing errors with its role (predictions/reviews)."""
    try:
        return index_rows(list(read_jsonl(path)), expected_samples=expected_samples)
    except AnalysisError as exc:
        raise AnalysisError(f"{role} file invalid: {exc}") from exc


def join_rows(pair: FilePair) -> tuple[tuple[JsonlRow, JsonlRow], ...]:
    """Join a pair's prediction and review rows by index, never by line position.

    Requires identical index sets (reporting which side is missing) and that every
    prediction names ``pair.model``. Returns (prediction, review) tuples sorted by index.
    """
    predictions = _load(pair.predictions, "predictions", pair.expected_samples)
    reviews = _load(pair.reviews, "reviews", pair.expected_samples)

    identity = f"{pair.benchmark}/{pair.model}/{pair.subset}"
    missing_reviews = sorted(predictions.keys() - reviews.keys())
    missing_predictions = sorted(reviews.keys() - predictions.keys())
    if missing_reviews or missing_predictions:
        raise AnalysisError(
            f"{identity}: index sets differ; "
            f"predictions with no review: {missing_reviews[:10]}; "
            f"reviews with no prediction: {missing_predictions[:10]}"
        )

    for row in predictions.values():
        if row.value.get("model") != pair.model:
            raise AnalysisError(
                f"{format_source(row.source)}: prediction model {row.value.get('model')!r} "
                f"!= expected {pair.model!r}"
            )

    return tuple((predictions[i], reviews[i]) for i in sorted(predictions))
