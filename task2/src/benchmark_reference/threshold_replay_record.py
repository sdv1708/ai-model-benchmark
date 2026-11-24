"""Read the recorded real replay (#63), so that a later study can set its result beside it.

The reader checks the record against its own manifest and against the frozen
policy. It changes nothing in the record and it decides nothing again: each cell
holds the recorded outcome counts.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_cost import Estimates
from benchmark_reference.threshold_policy import LoadedPolicy
from benchmark_reference.threshold_replay import CoverageResult, ReplayCell, RuleResults
from benchmark_reference.two_stage import FinalDecision


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    """The recorded decisions and coverage of each grade rule, and the manifest hash."""

    rules: dict[str, RuleResults]
    manifest_sha256: str


def _read(folder: Path, name: str) -> bytes:
    try:
        return (folder / name).read_bytes()
    except OSError as exc:
        raise AnalysisError(f"Cannot read the recorded replay file {folder / name}: {exc}") from exc


def _rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def _truth(text: str) -> FinalDecision:
    if text == "GO":
        return "GO"
    if text == "NO GO":
        return "NO GO"
    raise ValueError(text)


def _cell(row: dict[str, str], *, population: int, stage1_size: int) -> ReplayCell:
    """One recorded cell. The mean cost in questions comes from the counts, so it is exact."""
    draws, escalated = int(row["decisions"]), int(row["escalate"])
    go, no_go = int(row["stage1_go"]), int(row["stage1_no_go"])
    questions = Fraction((go + no_go) * stage1_size + escalated * population, draws)
    cell = ReplayCell(
        model=row["model"],
        probe=row["probe"],
        threshold=row["threshold"],
        full_passes=int(row["full_passes"]),
        population=population,
        truth=_truth(row["truth"]),
        draws=draws,
        go=go,
        no_go=no_go,
        escalated=escalated,
        questions=questions,
        tokens=Estimates(
            Fraction(row["expected_tokens_low"]),
            Fraction(row["expected_tokens_mean"]),
            Fraction(row["expected_tokens_high"]),
        ),
    )
    agrees = (
        go + no_go + escalated == draws
        and cell.wrong == int(row["wrong"])
        and round(float(questions), 3) == float(row["expected_questions"])
    )
    if not agrees:
        raise ValueError(f"model {cell.model!r}, threshold {cell.threshold}")
    return cell


def load_replay_record(folder: Path, loaded: LoadedPolicy) -> ReplayRecord:
    """The recorded replay of ``loaded``. Stop when the record is of another policy."""
    manifest_bytes = _read(folder, "manifest.json")
    try:
        manifest: Any = json.loads(manifest_bytes.decode("utf-8"))
        policy_sha256 = manifest["policy"]["sha256"]
        public_sha256 = manifest["public_source"]["sha256"]
        hashes = manifest["output_sha256"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnalysisError(f"The recorded replay manifest in {folder} is invalid") from exc
    if policy_sha256 != loaded.sha256:
        raise AnalysisError(
            f"The recorded replay in {folder} is of policy SHA-256 {policy_sha256}, "
            f"but {loaded.key} has {loaded.sha256}"
        )
    assert loaded.protocol is not None
    replay, public = loaded.protocol["unseen_model_replay"], loaded.protocol["public_panel"]
    if public_sha256 != public["sha256"]:
        raise AnalysisError(f"The recorded replay in {folder} is of another public file")
    tables = {name: _read(folder, name) for name in ("cells.csv", "coverage.csv")}
    for name, data in tables.items():
        if hashlib.sha256(data).hexdigest() != hashes.get(name):
            raise AnalysisError(f"The recorded replay file {folder / name} differs from its hash")
    section = loaded.benchmarks[replay["benchmark"]]
    rule_values = loaded.protocol["grade_rule"]
    rules: dict[str, RuleResults] = {}
    try:
        cells = [
            (
                row["grade_rule"],
                _cell(row, population=replay["questions"], stage1_size=section.stage1_size),
            )
            for row in _rows(tables["cells.csv"])
        ]
        coverage = [
            (
                row["grade_rule"],
                CoverageResult(
                    row["model"],
                    int(row["subsets"]),
                    int(row["covered"]),
                    int(row["truth_below_interval"]),
                    int(row["truth_above_interval"]),
                    float(row["mean_width"]),
                ),
            )
            for row in _rows(tables["coverage.csv"])
        ]
        for name in dict.fromkeys(rule for rule, _ in cells):
            rules[name] = RuleResults(
                name,
                rule_values[f"{name}_min_pass_at_1"],
                tuple(cell for rule, cell in cells if rule == name),
                tuple(result for rule, result in coverage if rule == name),
            )
    except (KeyError, ValueError) as exc:
        raise AnalysisError(f"The recorded replay in {folder} has an invalid row: {exc}") from exc
    return ReplayRecord(rules, hashlib.sha256(manifest_bytes).hexdigest())
