"""Token counts for each saved reference answer and the cost of each question.

The loader reads only the ``usage`` record of each saved prediction. It never
reads a grade. Each prediction file must have the SHA-256 that the reference
panel records, so the counts come from the same run as the reference grades.

The loader reports each missing count and never treats it as zero. A count is
missing when the file has no row for the question, when ``model_output`` or
``usage`` is absent or null, or when ``input_tokens`` or ``output_tokens`` is
absent or null. The estimate uses an answer only when the answer has both
counts. Any other value, such as a negative count, stops the load.

An unseen model has no counts. The estimate for each question comes from the
reference models that have a count: the low, mean, and high total (input plus
output) across those models. Summed over a question set, low and high are the
envelope of the reference models.
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal

from benchmark_reference.inputs import LFS_POINTER_PREFIX, format_source, read_jsonl, row_index
from benchmark_reference.models import AnalysisError, JsonValue

type MissingField = Literal["input_tokens", "output_tokens", "answer"]
_FIELDS: tuple[MissingField, MissingField] = ("input_tokens", "output_tokens")


@dataclass(frozen=True, slots=True)
class TokenCount:
    """Input and output tokens of one saved answer."""

    input: int
    output: int

    @property
    def total(self) -> int:
        return self.input + self.output


@dataclass(frozen=True, slots=True, order=True)
class MissingCount:
    """One count that the saved predictions do not hold.

    ``field`` is ``answer`` when the file has no row for the question.
    """

    model: str
    index: int
    field: MissingField


@dataclass(frozen=True, slots=True)
class TokenTable:
    """Counts for each reference model and question, the missing counts, and file hashes."""

    benchmark: str
    questions: tuple[int, ...]
    counts: Mapping[str, Mapping[int, TokenCount]]
    missing: tuple[MissingCount, ...]
    files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class QuestionCost:
    """Estimated tokens of one question for an unseen model, from ``models`` reference models."""

    low: int
    mean: Fraction
    high: int
    input_mean: Fraction
    output_mean: Fraction
    models: int


def predictions_name(benchmark: str, model: str) -> str:
    """The predictions file of one model, relative to the data root."""
    return f"Part 1/predictions/{benchmark}__{model}.jsonl"


def _count(value: JsonValue, field: str, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalysisError(f"{where}: {field} must be a nonnegative integer, got {value!r}")
    return value


def _read_model(
    path: Path, *, model: str, questions: set[int]
) -> tuple[dict[int, TokenCount], list[MissingCount]]:
    counts: dict[int, TokenCount] = {}
    missing: list[MissingCount] = []
    seen: set[int] = set()
    for row in read_jsonl(path):
        where = format_source(row.source)
        index = row_index(row)
        if index not in questions:
            raise AnalysisError(f"{where}: question {index} is not in the reference panel")
        if index in seen:
            raise AnalysisError(f"{where}: the file repeats question {index}")
        seen.add(index)
        if row.value.get("model") != model:
            found = row.value.get("model")
            raise AnalysisError(f"{where}: prediction model {found!r} != {model!r}")
        output = row.value.get("model_output")
        if output is not None and not isinstance(output, dict):
            raise AnalysisError(f"{where}: model_output must be an object or null")
        usage = None if output is None else output.get("usage")
        if usage is None:
            missing.extend(MissingCount(model, index, field) for field in _FIELDS)
            continue
        if not isinstance(usage, dict):
            raise AnalysisError(f"{where}: usage must be an object or null")
        values = [_count(usage.get(field), field, where) for field in _FIELDS]
        absent = [field for field, value in zip(_FIELDS, values, strict=True) if value is None]
        missing.extend(MissingCount(model, index, field) for field in absent)
        input_tokens, output_tokens = values
        if input_tokens is None or output_tokens is None:
            continue
        total = usage.get("total_tokens")
        if total is not None and total != input_tokens + output_tokens:
            raise AnalysisError(
                f"{where}: total_tokens {total!r} is not input plus output tokens "
                f"({input_tokens + output_tokens})"
            )
        counts[index] = TokenCount(input_tokens, output_tokens)
    missing.extend(MissingCount(model, index, "answer") for index in sorted(questions - seen))
    return counts, missing


def load_token_counts(
    data_root: Path,
    *,
    benchmark: str,
    models: Sequence[str],
    questions: Sequence[int],
    source_sha256: Mapping[str, str],
) -> TokenTable:
    """Read the counts of every reference answer; check each file against the panel hash."""
    wanted = set(questions)
    counts: dict[str, dict[int, TokenCount]] = {}
    missing: list[MissingCount] = []
    files: dict[str, str] = {}
    for model in models:
        name = predictions_name(benchmark, model)
        expected = source_sha256.get(name)
        if expected is None:
            raise AnalysisError(f"The reference panel does not record the SHA-256 of {name}")
        path = data_root / name
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AnalysisError(f"Cannot read predictions {path}: {exc}") from exc
        if data.startswith(LFS_POINTER_PREFIX.encode("ascii")):
            raise AnalysisError(
                f"{path}: Git LFS pointer, not data; run `git lfs pull` from the repo root"
            )
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise AnalysisError(
                f"{path}: SHA-256 {actual} differs from the reference panel source {expected}"
            )
        counts[model], model_missing = _read_model(path, model=model, questions=wanted)
        missing.extend(model_missing)
        files[name] = actual
    return TokenTable(
        benchmark=benchmark,
        questions=tuple(sorted(wanted)),
        counts=counts,
        missing=tuple(sorted(missing)),
        files=files,
    )


def estimate_question_costs(table: TokenTable) -> dict[int, QuestionCost]:
    """Low, mean, and high tokens of each question across the models with a count."""
    costs: dict[int, QuestionCost] = {}
    for index in table.questions:
        found = [c[index] for c in table.counts.values() if index in c]
        if not found:
            raise AnalysisError(
                f"No reference model has token counts for question {index}; "
                "its cost cannot be estimated"
            )
        totals = [count.total for count in found]
        costs[index] = QuestionCost(
            low=min(totals),
            mean=Fraction(sum(totals), len(found)),
            high=max(totals),
            input_mean=Fraction(sum(c.input for c in found), len(found)),
            output_mean=Fraction(sum(c.output for c in found), len(found)),
            models=len(found),
        )
    return costs
