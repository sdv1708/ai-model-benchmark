"""AA-LCR selectors using benchmark metadata and historical outcomes only."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from benchmark_reference.models import AnalysisError, SampleResult
from benchmark_reference.pruning import (
    ReferenceScores,
    SelectedSample,
    select_baseline,
    select_strata,
)

CANDIDATES = ("metadata_stratified", "length_difficulty_stratified")


@dataclass(frozen=True, slots=True)
class TaskMetadata:
    """Benchmark token count, not model usage; canonical document URLs."""

    input_tokens: int
    source_urls: tuple[str, ...]


def extract_metadata(samples: Sequence[SampleResult]) -> dict[int, TaskMetadata]:
    """Require benchmark fields to agree across models; ignore usage and model output.

    Question text is checked for identity but not used as a learned semantic label.
    Extra model-specific metadata is deliberately excluded from selector inputs.
    """
    result: dict[int, TaskMetadata] = {}
    questions: dict[int, str] = {}
    for sample in samples:
        if sample.benchmark != "aa_lcr":
            raise AnalysisError("Expected AA-LCR samples")
        metadata = sample.metadata.get("sample_metadata")
        if not isinstance(metadata, dict):
            raise AnalysisError(f"Missing AA-LCR metadata for {sample.model}#{sample.index}")
        tokens, urls, question = (
            metadata.get("input_tokens"),
            metadata.get("data_source_urls"),
            metadata.get("question"),
        )
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise AnalysisError(f"Invalid input_tokens for index {sample.index}")
        if not isinstance(urls, str) or not urls.strip():
            raise AnalysisError(f"Missing data_source_urls for index {sample.index}")
        if not isinstance(question, str) or not question.strip():
            raise AnalysisError(f"Missing question for index {sample.index}")
        sources = tuple(sorted({url.strip() for url in urls.split(";") if url.strip()}))
        if not sources:
            raise AnalysisError(f"Empty document set for index {sample.index}")
        task = TaskMetadata(tokens, sources)
        if result.setdefault(sample.index, task) != task:
            raise AnalysisError(f"Cross-model benchmark metadata conflict at index {sample.index}")
        if questions.setdefault(sample.index, question) != question:
            raise AnalysisError(f"Cross-model question conflict at index {sample.index}")
    if not result:
        raise AnalysisError("No AA-LCR metadata")
    return dict(sorted(result.items()))


def _bands(values: Mapping[int, int]) -> dict[int, int]:
    """Empirical midrank thirds; equal feature values never split by sample ID."""
    ordered = sorted(values.values())
    return {
        index: min(
            2,
            3 * (bisect_left(ordered, value) + bisect_right(ordered, value)) // (2 * len(ordered)),
        )
        for index, value in values.items()
    }


def select_long_context(
    references: ReferenceScores,
    *,
    metadata: Mapping[int, TaskMetadata],
    strategy: str,
    keep_ratio: float,
    seed: int,
) -> tuple[SelectedSample, ...]:
    """Cover length x document-count or length x historical pass-count groups.

    At most nine occupied groups for either candidate with two references. No
    target grade, model usage, generated answer, or manually chosen ID is used.
    Below-coverage budgets fail. Metadata-only selection needs no reference labels
    for its features; the reference table supplies validated sample identities.
    """
    if strategy not in CANDIDATES:
        raise AnalysisError(f"Unknown AA-LCR candidate {strategy!r}")
    validated = select_baseline(
        references, strategy="uniform_random", keep_ratio=keep_ratio, seed=seed
    )
    ids = set(next(iter(references.values())))
    if set(metadata) != ids:
        raise AnalysisError("Metadata and reference sample identities differ")
    for task in metadata.values():
        if (
            isinstance(task.input_tokens, bool)
            or not isinstance(task.input_tokens, int)
            or task.input_tokens <= 0
            or not task.source_urls
            or any(not isinstance(url, str) or not url.strip() for url in task.source_urls)
            or len(set(task.source_urls)) != len(task.source_urls)
        ):
            raise AnalysisError("Invalid task metadata")
    lengths = _bands({i: metadata[i].input_tokens for i in ids})
    documents = _bands({i: len(metadata[i].source_urls) for i in ids})
    groups: dict[str, list[int]] = defaultdict(list)
    for index in sorted(ids):
        second = (
            f"documents:{documents[index]}"
            if strategy == "metadata_stratified"
            else f"passes:{sum(int(values[index]) for values in references.values())}"
        )
        groups[f"length:{lengths[index]}|{second}"].append(index)
    return select_strata(groups, budget=len(validated), seed=seed)
