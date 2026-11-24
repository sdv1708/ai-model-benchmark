"""The 300 saved AA-LCR answers, with the question and the reference answer of each.

The saved reviews hold the question, the model answer, the recorded grade, and the
name of the recorded judge. They do not hold the reference answer. That comes from
the pinned public AA-LCR v1.0 file. This module checks each file against the hash
that the committed reference panel records.
"""

import csv
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark_reference.inputs import index_rows, read_jsonl
from benchmark_reference.judge_prompt import prompt_sha256, render_prompt
from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import question_fingerprint
from benchmark_reference.threshold_benchmarks import AA_LCR, load_reference_panel

SOURCE_URL = (
    "https://huggingface.co/datasets/ArtificialAnalysis/AA-LCR/resolve/"
    "bdae010bbce259820c0e34c1d7cce210d966fb75/AA-LCR_Dataset.csv"
)


@dataclass(frozen=True, slots=True)
class JudgeItem:
    """One saved answer. ``saved_judge`` is None when the review names no judge model."""

    model: str
    index: int
    question: str
    reference: str
    answer: str
    saved_grade: int
    saved_judge: str | None

    @property
    def key(self) -> tuple[str, int]:
        return self.model, self.index

    @property
    def prompt(self) -> str:
        return render_prompt(question=self.question, reference=self.reference, answer=self.answer)


@dataclass(frozen=True, slots=True)
class JudgeInputs:
    """Every saved answer in model and question order, and the hash of each input file."""

    items: tuple[JudgeItem, ...]
    panel_sha256: str
    files: Mapping[str, str]

    @property
    def prompts_sha256(self) -> str:
        """One hash for all prompts, so a run and its estimate use the same text."""
        lines = [f"{i.model}:{i.index}:{prompt_sha256(i.prompt)}\n" for i in self.items]
        return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()

    @property
    def original_judge(self) -> str | None:
        """The judge model of the saved reviews, or None when they do not name one."""
        names = {item.saved_judge for item in self.items}
        return names.pop() if len(names) == 1 else None


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnalysisError(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{name} must be a nonempty string")
    return value


def _pinned_bytes(path: Path, expected: object) -> bytes:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise AnalysisError(f"{path} has SHA-256 {digest}, not the recorded {expected}")
    return data


def _references(path: Path, expected: object) -> dict[str, tuple[str, str]]:
    """Question fingerprint to the official question and the official answer."""
    text = _pinned_bytes(path, expected).decode("utf-8-sig")
    found: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text, newline="")):
        question = _text(row.get("question"), f"{path} question")
        key = question_fingerprint(question)
        if key in found:
            raise AnalysisError(f"{path} repeats the question with fingerprint {key}")
        found[key] = (question, _text(row.get("answer"), f"{path} answer"))
    return found


def load_judge_inputs(*, panel_path: Path, data_root: Path, source_csv: Path) -> JudgeInputs:
    """Load and check the panel, the saved reviews, and the pinned reference answers."""
    panel = load_reference_panel(panel_path, benchmark=AA_LCR)
    document = json.loads(panel_path.read_text(encoding="utf-8"))
    verification = _object(
        document["provenance"].get("source_verification"), f"{panel_path} source_verification"
    )
    csv_sha256 = verification.get("csv_sha256")
    references = _references(source_csv, csv_sha256)
    fingerprints = {t["index"]: t.get("question_sha256") for t in document["tasks"]}
    missing = sorted(i for i, f in fingerprints.items() if f not in references)
    if missing:
        raise AnalysisError(f"{source_csv} has no question for the panel questions {missing[:10]}")
    files = {panel_path.name: panel.sha256, source_csv.name: str(csv_sha256)}
    items: list[JudgeItem] = []
    for model in sorted(panel.references):
        name = f"Part 1/reviews/aa_lcr__{model}.jsonl"
        path = data_root / name
        _pinned_bytes(path, panel.source_sha256.get(name))
        files[name] = panel.source_sha256[name]
        rows = index_rows(list(read_jsonl(path)), expected_samples=len(fingerprints))
        if set(rows) != set(fingerprints):
            raise AnalysisError(f"{path} does not hold exactly the panel questions")
        for index, row in rows.items():
            where = f"{path} question {index}"
            sample = _object(row.value.get("sample_score"), where)
            score = _object(sample.get("score"), where)
            grade = panel.references[model][index]
            if _object(score.get("value"), where).get("acc") != grade:
                raise AnalysisError(f"{where}: the saved grade differs from the panel grade")
            judge = _object(score.get("metadata") or {}, where).get("model")
            question, reference = references[str(fingerprints[index])]
            items.append(
                JudgeItem(
                    model=model,
                    index=index,
                    question=question,
                    reference=reference,
                    # The adapter sends the filtered prediction, not the raw one.
                    answer=_text(score.get("extracted_prediction"), where),
                    saved_grade=int(grade),
                    saved_judge=judge if isinstance(judge, str) and judge else None,
                )
            )
    return JudgeInputs(tuple(items), panel.sha256, files)
