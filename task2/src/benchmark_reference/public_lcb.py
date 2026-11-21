"""Public LiveCodeBench results as a panel of unseen real models.

LiveCodeBench publishes one ``pass@1`` value for each model and question in one
JSON file. The source repository states no license, so the raw file is never
committed. The fetch step downloads it to a Git-ignored location and stops when
its SHA-256 differs from the pinned value.

The grades stay locked until a frozen policy exists. ``load_public_results``
gives question metadata and model names only. ``load_public_grades`` gives the
raw ``pass@1`` values, and only after the frozen-policy check of the real-grade
replay passes. The grade rule, for example "pass at 50 or more", belongs to the
policy, not to this module.
"""

import hashlib
import importlib
import json
import math
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import write_atomic
from benchmark_reference.threshold_policy import LoadedPolicy, authorize_real_replay


@dataclass(frozen=True, slots=True)
class PublicSource:
    """The location, the SHA-256, and the size in bytes of one public file."""

    url: str
    sha256: str
    size: int


TASK2 = Path(__file__).resolve().parents[2]

# Read on 10 November 2026 (issue #75).
PINNED_SOURCE = PublicSource(
    url="https://livecodebench.github.io/performances_generation.json",
    sha256="17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1",
    size=6_950_346,
)

type Download = Callable[[str, int], bytes]


@dataclass(frozen=True, slots=True)
class PublicShape:
    """The number of models and questions that the public file must have."""

    models: int
    questions: int


# Read on 10 November 2026: 28 models x 1,055 questions = 29,540 rows, no missing cell.
RECORDED_SHAPE = PublicShape(models=28, questions=1055)
DEFAULT_SOURCE_PATH = TASK2 / "external" / "livecodebench" / "performances_generation.json"
_ROW_KEYS = {"question_id", "model", "date", "difficulty", "pass@1", "platform"}
DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True, slots=True)
class PublicQuestion:
    """One public question. ``date`` is the published value: Unix time in milliseconds."""

    question_id: str
    date: int
    difficulty: str
    platform: str


@dataclass(frozen=True, slots=True)
class PublicResults:
    """The public file without its grades: question metadata and model names.

    ``models`` is sorted. ``questions`` maps each question identifier to its
    metadata, in identifier order. The model ``release_date`` field is not
    given: 19 of 28 models share one placeholder value.
    """

    sha256: str
    models: tuple[str, ...]
    questions: Mapping[str, PublicQuestion]


def download_url(url: str, limit: int) -> bytes:
    """The bytes at ``url``, up to ``limit`` bytes; the read stops at the limit or the end."""
    chunks: list[bytes] = []
    received = 0
    with urllib.request.urlopen(url, timeout=120) as response:
        while received < limit:
            chunk: bytes = response.read(min(1 << 20, limit - received))
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
    return b"".join(chunks)


def fetch_source(
    destination: Path, *, source: PublicSource = PINNED_SOURCE, download: Download = download_url
) -> str:
    """Download ``source`` to ``destination`` and give its SHA-256.

    The download reads one byte more than the pinned size, so a larger file also
    gives a hash mismatch. On a mismatch, the function writes nothing and an
    existing file stays as it is.
    """
    data = download(source.url, source.size + 1)
    digest = hashlib.sha256(data).hexdigest()
    if digest != source.sha256:
        raise AnalysisError(
            f"The file at {source.url} has SHA-256 {digest} ({len(data):,} bytes), which "
            f"differs from the pinned SHA-256 {source.sha256} ({source.size:,} bytes). "
            "Nothing was written."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(destination, data)
    return digest


def _text(row: Mapping[str, object], key: str, where: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{where}: {key} must be nonempty text")
    return value


def _parse(
    path: Path, *, sha256: str, shape: PublicShape
) -> tuple[PublicResults, dict[str, dict[str, float]]]:
    """Validate the whole file; give the metadata and the raw ``pass@1`` cells.

    Error messages name the model and the question, never a ``pass@1`` value.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AnalysisError(f"Cannot read the public LiveCodeBench file {path}: {exc}") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise AnalysisError(
            f"The public LiveCodeBench file {path} has SHA-256 {digest}, not the pinned {sha256}"
        )
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"The public LiveCodeBench file {path} is not JSON: {exc}") from exc
    rows = raw.get("performances") if isinstance(raw, dict) else None
    listed = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not isinstance(listed, list):
        raise AnalysisError(f"{path}: the file must have 'performances' and 'models' lists")
    names: list[str] = []
    for position, entry in enumerate(listed):
        if not isinstance(entry, dict) or "model_repr" not in entry:
            raise AnalysisError(f"{path}: model entry {position} has no model_repr")
        names.append(_text(entry, "model_repr", f"{path}: model entry {position}"))
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise AnalysisError(f"{path}: duplicate model {repeated[0]!r} in the model list")
    cells: dict[str, dict[str, float]] = {name: {} for name in names}
    questions: dict[str, PublicQuestion] = {}
    for position, row in enumerate(rows):
        where = f"{path}: row {position}"
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise AnalysisError(f"{where}: keys must be exactly {sorted(_ROW_KEYS)}")
        model = _text(row, "model", where)
        question = PublicQuestion(
            _text(row, "question_id", where),
            row["date"] if type(row["date"]) is int else -1,
            _text(row, "difficulty", where),
            _text(row, "platform", where),
        )
        where = f"{where} (model {model!r}, question {question.question_id!r})"
        if question.date < 0:
            raise AnalysisError(f"{where}: date must be a nonnegative integer")
        if question.difficulty not in DIFFICULTIES:
            raise AnalysisError(f"{where}: difficulty must be one of {DIFFICULTIES}")
        grade = row["pass@1"]
        if (
            isinstance(grade, bool)
            or not isinstance(grade, int | float)
            or not math.isfinite(grade)
            or not 0 <= grade <= 100
        ):
            raise AnalysisError(f"{where}: pass@1 must be a number from 0 to 100")
        if model not in cells:
            raise AnalysisError(f"{where}: the model is not in the model list")
        if question.question_id in cells[model]:
            raise AnalysisError(f"{where}: duplicate model and question pair")
        known = questions.setdefault(question.question_id, question)
        if known != question:
            raise AnalysisError(f"{where}: date, difficulty, or platform differs between rows")
        cells[model][question.question_id] = float(grade)
    if len(names) != shape.models:
        raise AnalysisError(
            f"{path}: {len(names)} models, but the recorded shape has {shape.models}"
        )
    if len(questions) != shape.questions:
        raise AnalysisError(
            f"{path}: {len(questions)} questions, but the recorded shape has {shape.questions}"
        )
    for model in sorted(names):
        missing = sorted(set(questions) - set(cells[model]))
        if missing:
            raise AnalysisError(
                f"{path}: missing cell: model {model!r} has no row for question {missing[0]!r} "
                f"({len(missing)} missing for this model)"
            )
    results = PublicResults(
        digest, tuple(sorted(names)), {key: questions[key] for key in sorted(questions)}
    )
    return results, cells


def load_public_results(
    path: Path = DEFAULT_SOURCE_PATH,
    *,
    sha256: str = PINNED_SOURCE.sha256,
    shape: PublicShape = RECORDED_SHAPE,
) -> PublicResults:
    """Question identifiers, dates, difficulty labels, platforms, and model names.

    The loader validates every row, the ``pass@1`` range included, but it gives
    no grade. It rejects another SHA-256, a missing cell, a duplicate model and
    question pair, and a model or question count that differs from ``shape``.
    """
    results, _ = _parse(path, sha256=sha256, shape=shape)
    return results


def load_public_grades(
    path: Path,
    policy: LoadedPolicy,
    *,
    lock_text: str | None = None,
    sha256: str = PINNED_SOURCE.sha256,
    shape: PublicShape = RECORDED_SHAPE,
) -> dict[str, dict[str, float]]:
    """The raw ``pass@1`` value, 0 to 100, for each model and question.

    The frozen-policy check runs first, before the file is opened. It refuses a
    policy that is not frozen or whose hash differs from the committed lock.
    ``lock_text`` replaces the committed lock file in tests only. The file then
    passes the same validation as ``load_public_results``.
    """
    authorize_real_replay(policy, lock_text=lock_text)
    _, cells = _parse(path, sha256=sha256, shape=shape)
    return {model: dict(sorted(cells[model].items())) for model in sorted(cells)}


# The pinned public dataset of the existing source verification (issue #19).
DATASET = "marianna13/livecodebench_code_generation_lite_parquet"
DATASET_REVISION = "e70df9620dd54c12afac5e2881355de6f9ece2e9"
DATASET_SUBSET = "release_v5"
REFERENCE_QUESTIONS = 315


def question_fingerprint(text: str) -> str:
    """SHA-256 of the question text with LF line ends and no outer white space.

    The reference panel export and the source verification use the same rule.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetQuestion:
    """One question of the pinned dataset: its identifier, platform, and fingerprint."""

    question_id: str
    platform: str
    question_sha256: str


@dataclass(frozen=True, slots=True)
class MappedQuestion:
    """One reference-panel question and its public question identifier."""

    index: int
    question_sha256: str
    question_id: str


def map_panel_questions(
    panel: Mapping[int, str],
    dataset: Iterable[DatasetQuestion],
    public: PublicResults,
    *,
    expected: int = REFERENCE_QUESTIONS,
) -> tuple[MappedQuestion, ...]:
    """Join each panel question, by fingerprint, to one public question identifier.

    ``panel`` maps each panel index to its question fingerprint. The join must
    give ``expected`` unique matches, and every match must be in the public
    results with the same platform. Otherwise the function stops and names each
    question that fails. It uses no grade.
    """
    if len(panel) != expected:
        raise AnalysisError(f"The panel has {len(panel)} reference questions, expected {expected}")
    owners: dict[str, list[int]] = {}
    for index in sorted(panel):
        owners.setdefault(panel[index], []).append(index)
    shared = [indexes for indexes in owners.values() if len(indexes) > 1]
    if shared:
        raise AnalysisError(
            "Panel indexes "
            + "; ".join(" and ".join(map(str, indexes)) for indexes in shared)
            + " share one fingerprint"
        )
    candidates: dict[str, list[DatasetQuestion]] = {}
    for row in dataset:
        if row.question_sha256 in owners:
            candidates.setdefault(row.question_sha256, []).append(row)
    unmatched: list[str] = []
    problems: list[str] = []
    mapped: list[MappedQuestion] = []
    for index in sorted(panel):
        fingerprint = panel[index]
        rows = candidates.get(fingerprint, [])
        if not rows:
            unmatched.append(f"index {index} (fingerprint {fingerprint})")
            continue
        if len(rows) > 1:
            ids = ", ".join(row.question_id for row in rows)
            problems.append(
                f"index {index} (fingerprint {fingerprint}) matches {len(rows)} dataset "
                f"questions ({ids})"
            )
            continue
        row = rows[0]
        known = public.questions.get(row.question_id)
        if known is None:
            problems.append(
                f"index {index} (question {row.question_id}) is not in the public results"
            )
            continue
        if known.platform != row.platform:
            problems.append(
                f"index {index} (question {row.question_id}) has platform {row.platform} in the "
                f"dataset and {known.platform} in the public results"
            )
            continue
        mapped.append(MappedQuestion(index, fingerprint, row.question_id))
    if unmatched:
        problems.insert(
            0,
            f"{len(unmatched)} of {len(panel)} reference questions have no match in "
            f"{DATASET}@{DATASET_REVISION}: " + "; ".join(unmatched),
        )
    by_id: dict[str, list[int]] = {}
    for item in mapped:
        by_id.setdefault(item.question_id, []).append(item.index)
    problems.extend(
        f"question {question} matches indexes {' and '.join(map(str, indexes))}"
        for question, indexes in by_id.items()
        if len(indexes) > 1
    )
    if problems:
        raise AnalysisError("The question mapping failed: " + "; ".join(problems))
    return tuple(mapped)


def read_dataset_rows() -> list[dict[str, Any]]:
    """The identity columns of the pinned dataset, read over HTTP byte ranges.

    The function needs the ``public-source`` extra (fsspec, aiohttp, pyarrow)
    and internet access, but no credential. It reads no hidden-test column, no
    model answer, and no grade. ``contest_date`` is a datetime; the other
    columns are text.
    """
    fsspec = importlib.import_module("fsspec")
    parquet = importlib.import_module("pyarrow.parquet")
    root = f"https://huggingface.co/datasets/{DATASET}/resolve/{DATASET_REVISION}"

    def shard(index: int) -> list[dict[str, str]]:
        url = f"{root}/{DATASET_SUBSET}/test-{index:05d}-of-00009.parquet?download=true"
        with fsspec.open(url, "rb", block_size=256 * 1024).open() as stream:
            table = parquet.ParquetFile(stream).read(
                columns=["question_content", "question_id", "platform", "contest_date"]
            )
        rows: list[dict[str, Any]] = table.to_pylist()
        return rows

    with ThreadPoolExecutor(max_workers=3) as pool:
        return [row for rows in pool.map(shard, range(9)) for row in rows]


def dataset_questions(rows: Iterable[Mapping[str, object]]) -> list[DatasetQuestion]:
    """The identifier, platform, and fingerprint of each dataset row."""
    questions: list[DatasetQuestion] = []
    for row in rows:
        question, platform, content = row["question_id"], row["platform"], row["question_content"]
        if not all(isinstance(value, str) for value in (question, platform, content)):
            raise AnalysisError("A pinned dataset row has a question field that is not text")
        questions.append(
            DatasetQuestion(str(question), str(platform), question_fingerprint(str(content)))
        )
    return questions


DEFAULT_PANEL_PATH = TASK2 / "data" / "lcb-reference-panel.json"
DEFAULT_MAPPING_PATH = TASK2 / "data" / "lcb-public-mapping.json"
_MAPPING_KEYS = {
    "schema_version",
    "dataset",
    "dataset_revision",
    "dataset_subset",
    "panel_sha256",
    "public_sha256",
    "questions",
}
_ENTRY_KEYS = {"index", "question_id", "question_sha256"}


def panel_fingerprints(path: Path = DEFAULT_PANEL_PATH) -> dict[int, str]:
    """The question fingerprint of each index of the LiveCodeBench reference panel."""
    try:
        panel = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read reference panel {path}: {exc}") from exc
    tasks = panel.get("tasks") if isinstance(panel, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise AnalysisError(f"Reference panel {path} has no tasks")
    fingerprints: dict[int, str] = {}
    for task in tasks:
        index = task.get("index") if isinstance(task, dict) else None
        fingerprint = task.get("question_sha256") if isinstance(task, dict) else None
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not isinstance(fingerprint, str)
            or index in fingerprints
        ):
            raise AnalysisError(f"Reference panel {path} has an invalid or repeated task")
        fingerprints[index] = fingerprint
    return fingerprints


def mapping_document(mapped: Iterable[MappedQuestion], *, panel_sha256: str) -> bytes:
    """The mapping file bytes: sorted JSON with LF line ends.

    Each entry holds the panel index, the fingerprint, and the question
    identifier only. The header binds the entries to the pinned dataset, the
    panel file, and the pinned public file.
    """
    document = {
        "schema_version": 1,
        "dataset": DATASET,
        "dataset_revision": DATASET_REVISION,
        "dataset_subset": DATASET_SUBSET,
        "panel_sha256": panel_sha256,
        "public_sha256": PINNED_SOURCE.sha256,
        "questions": [
            {"index": m.index, "question_id": m.question_id, "question_sha256": m.question_sha256}
            for m in sorted(mapped, key=lambda m: m.index)
        ],
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_mapping(
    path: Path = DEFAULT_MAPPING_PATH,
    *,
    panel_path: Path = DEFAULT_PANEL_PATH,
    expected: int = REFERENCE_QUESTIONS,
) -> tuple[MappedQuestion, ...]:
    """Read the committed mapping and check it against the reference panel.

    The mapping must name the pinned dataset and the pinned public file, and the
    SHA-256 of ``panel_path``. It must hold each panel index once, with the panel
    fingerprint, and ``expected`` unique question identifiers.
    """
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
        panel_sha256 = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read the question mapping {path}: {exc}") from exc
    if not isinstance(document, dict) or set(document) != _MAPPING_KEYS:
        raise AnalysisError(f"Mapping {path} keys must be exactly {sorted(_MAPPING_KEYS)}")
    if document["schema_version"] != 1:
        raise AnalysisError(f"Mapping {path} schema_version must be 1")
    if (document["dataset"], document["dataset_revision"], document["dataset_subset"]) != (
        DATASET,
        DATASET_REVISION,
        DATASET_SUBSET,
    ):
        raise AnalysisError(f"Mapping {path} must name the pinned dataset {DATASET}")
    if document["public_sha256"] != PINNED_SOURCE.sha256:
        raise AnalysisError(f"Mapping {path} must name the pinned public SHA-256")
    if document["panel_sha256"] != panel_sha256:
        raise AnalysisError(
            f"Mapping {path} records panel SHA-256 {document['panel_sha256']}, "
            f"but {panel_path} has {panel_sha256}"
        )
    entries = document["questions"]
    if not isinstance(entries, list):
        raise AnalysisError(f"Mapping {path} questions must be a list")
    panel = panel_fingerprints(panel_path)
    mapped: list[MappedQuestion] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise AnalysisError(f"Mapping {path} entry keys must be exactly {sorted(_ENTRY_KEYS)}")
        index, question, fingerprint = (
            entry["index"],
            entry["question_id"],
            entry["question_sha256"],
        )
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not isinstance(question, str)
            or not question
            or not isinstance(fingerprint, str)
        ):
            raise AnalysisError(f"Mapping {path} has an invalid entry")
        if panel.get(index) != fingerprint:
            raise AnalysisError(
                f"Mapping {path}: index {index} has another fingerprint than the panel"
            )
        mapped.append(MappedQuestion(index, fingerprint, question))
    indexes = [item.index for item in mapped]
    if len(mapped) != expected or sorted(indexes) != sorted(panel) or len(set(indexes)) != expected:
        raise AnalysisError(
            f"Mapping {path} must hold each of the {expected} panel indexes once; "
            f"it holds {len(mapped)} entries"
        )
    questions = [item.question_id for item in mapped]
    for question in sorted(set(questions)):
        if questions.count(question) > 1:
            raise AnalysisError(
                f"Mapping {path}: question {question} appears {questions.count(question)} times"
            )
    return tuple(sorted(mapped, key=lambda item: item.index))
