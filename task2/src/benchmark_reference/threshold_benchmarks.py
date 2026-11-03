"""The benchmarks of the threshold-decision command, their panels, and their strata.

Each benchmark has its own reference panel and its own stratifiers. The
registry order is the report order: LiveCodeBench, then AA-LCR.

A LiveCodeBench stratum comes from the reference grades only. An AA-LCR stratum
also uses the panel metadata: the benchmark input length and the source
document set of each question. These are benchmark fields, not model usage.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from benchmark_reference import long_context, pruning
from benchmark_reference.long_context import TaskMetadata, long_context_strata
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import ReferenceScores, reference_strata, validate_references

LIVE_CODE_BENCH = "live_code_bench_v5"
AA_LCR = "aa_lcr"


@dataclass(frozen=True, slots=True)
class Benchmark:
    """One benchmark: its report title, panel file, stratifiers, and grader.

    ``metadata`` is true when the panel holds question metadata: the input
    length and the source documents of each question. The strata then use it.
    ``judge_graded`` is true when an LLM judge gives the grades. The saved data
    has one judgment for each answer, so nobody can measure the judge noise.
    """

    name: str
    title: str
    panel_file: str
    stratifiers: tuple[str, ...]
    metadata: bool
    judge_graded: bool


BENCHMARKS = {
    item.name: item
    for item in (
        Benchmark(
            LIVE_CODE_BENCH,
            "LiveCodeBench",
            "lcb-reference-panel.json",
            pruning.CANDIDATES,
            metadata=False,
            judge_graded=False,
        ),
        Benchmark(
            AA_LCR,
            "AA-LCR",
            "aa-lcr-reference-panel.json",
            long_context.CANDIDATES,
            metadata=True,
            judge_graded=True,
        ),
    )
}


@dataclass(frozen=True, slots=True)
class ReferencePanel:
    """Reference grades and metadata of one benchmark, with the hashes of the panel file.

    ``metadata`` is empty for LiveCodeBench and covers every question for AA-LCR.
    ``sha256`` is the SHA-256 of the panel bytes. ``source_sha256`` maps each
    source file, relative to the data root, to the SHA-256 that the panel export
    recorded. A panel built in memory, as in a test, has empty hashes.

    The panel keeps plain-dict copies of its mappings, so worker processes can
    receive it by pickle.
    """

    benchmark: str
    references: ReferenceScores
    metadata: Mapping[int, TaskMetadata] = field(default_factory=dict)
    sha256: str = ""
    source_sha256: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.benchmark not in BENCHMARKS:
            raise AnalysisError(
                f"Unknown benchmark {self.benchmark!r}; choose one of {tuple(BENCHMARKS)}"
            )
        ids = validate_references(self.references)
        if BENCHMARKS[self.benchmark].metadata:
            if set(self.metadata) != set(ids):
                raise AnalysisError(
                    f"{self.benchmark} panel metadata must cover exactly the reference questions"
                )
        elif self.metadata:
            raise AnalysisError(f"A {self.benchmark} panel must not have question metadata")
        plain = {model: dict(scores) for model, scores in self.references.items()}
        object.__setattr__(self, "references", plain)
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "source_sha256", dict(self.source_sha256))

    @property
    def questions(self) -> tuple[int, ...]:
        return tuple(validate_references(self.references))

    @property
    def stratifiers(self) -> tuple[str, ...]:
        return BENCHMARKS[self.benchmark].stratifiers

    def strata(self, stratifier: str) -> dict[str, list[int]]:
        """The occupied strata of one stratifier of this benchmark."""
        if stratifier not in self.stratifiers:
            raise AnalysisError(
                f"{stratifier!r} is not a {self.benchmark} stratifier; choose {self.stratifiers}"
            )
        if BENCHMARKS[self.benchmark].metadata:
            return long_context_strata(self.references, metadata=self.metadata, strategy=stratifier)
        return reference_strata(self.references, strategy=stratifier)


def _task_metadata(task: Mapping[str, object], path: Path) -> TaskMetadata:
    tokens, urls = task.get("input_tokens"), task.get("source_urls")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
        raise AnalysisError(f"Reference panel {path} has invalid input_tokens at {task['index']}")
    if not isinstance(urls, list) or not urls or not all(isinstance(u, str) for u in urls):
        raise AnalysisError(f"Reference panel {path} has invalid source_urls at {task['index']}")
    return TaskMetadata(tokens, tuple(urls))


def load_reference_panel(path: Path, *, benchmark: str) -> ReferencePanel:
    """Read the committed reference panel; reject another benchmark or bad grades."""
    if benchmark not in BENCHMARKS:
        raise AnalysisError(f"Unknown benchmark {benchmark!r}; choose one of {tuple(BENCHMARKS)}")
    try:
        data = path.read_bytes()
        panel = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read reference panel {path}: {exc}") from exc
    if not isinstance(panel, dict) or panel.get("schema_version") != 1:
        raise AnalysisError(f"Reference panel {path} must have schema_version 1")
    provenance = panel.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("benchmark") != benchmark:
        raise AnalysisError(f"Reference panel {path} is not for policy benchmark {benchmark!r}")
    sources = provenance.get("source_sha256", {})
    if not isinstance(sources, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in sources.items()
    ):
        raise AnalysisError(f"Reference panel {path} has invalid source hashes")
    tasks = panel.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise AnalysisError(f"Reference panel {path} has no tasks")
    references: dict[str, dict[int, float]] = {}
    metadata: dict[int, TaskMetadata] = {}
    for task in tasks:
        index = task.get("index") if isinstance(task, dict) else None
        scores = task.get("scores") if isinstance(task, dict) else None
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(scores, dict):
            raise AnalysisError(f"Reference panel {path} has an invalid task")
        for model, score in scores.items():
            if index in references.setdefault(model, {}):
                raise AnalysisError(f"Reference panel {path} repeats task {index}")
            references[model][index] = score
        if BENCHMARKS[benchmark].metadata:
            metadata[index] = _task_metadata(task, path)
    validate_references(references)
    grades = {
        model: {i: float(s) for i, s in scores.items()} for model, scores in references.items()
    }
    return ReferencePanel(
        benchmark, grades, metadata, hashlib.sha256(data).hexdigest(), dict(sources)
    )
