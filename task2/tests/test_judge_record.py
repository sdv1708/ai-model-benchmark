"""The recorded judge run of #76: its hashes, its approval, and its measured values."""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_reference.judge_prompt import parse_reply
from benchmark_reference.judge_report import OUTPUT_NAMES
from benchmark_reference.judge_statement import RECORD_FILE, load_judge_noise
from benchmark_reference.threshold_benchmarks import AA_LCR, load_reference_panel

TASK2 = Path(__file__).parents[1]
DATA = TASK2.parent / "docs" / "data"
RECORD = DATA / "task2-aa-lcr-judge-rerun"
PANEL = TASK2 / "data" / "aa-lcr-reference-panel.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(name: str) -> Any:
    return json.loads((RECORD / name).read_text(encoding="utf-8"))


def _attempts() -> list[dict[str, Any]]:
    text = (RECORD / "judgments.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.split("\n")[:-1]]


def test_the_record_holds_every_output_with_its_recorded_hash() -> None:
    assert {p.name for p in RECORD.iterdir()} == set(OUTPUT_NAMES)
    hashes = _json("manifest.json")["output_sha256"]
    assert hashes == {n: _sha(RECORD / n) for n in OUTPUT_NAMES if n != "manifest.json"}


def test_the_run_used_the_approved_estimate_and_the_original_judge() -> None:
    settings = _json("run.json")
    assert settings["estimate_sha256"] == _sha(DATA / "task2-aa-lcr-judge-estimate.json")
    assert settings["approval_url"].endswith("/issues/76#issuecomment-7115460027")
    judge = _json("summary.json")["judge"]
    assert judge["same_judge"] is True
    assert judge["response_models"] == [judge["model"]]


def test_the_record_holds_five_independent_judgments_for_each_answer() -> None:
    grades: dict[tuple[str, int], list[int]] = defaultdict(list)
    attempts = _attempts()
    for attempt in attempts:
        if attempt["status"] == "success":
            assert parse_reply(attempt["reply"]).verdict == attempt["verdict"]
            key = (attempt["model"], attempt["index"])
            grades[key].append(int(attempt["verdict"] == "CORRECT"))
    assert len(grades) == 300 and {len(g) for g in grades.values()} == {5}
    assert len({a["response_id"] for a in attempts}) == len(attempts)
    summary = _json("summary.json")
    split = sum(len(set(g)) > 1 for g in grades.values())
    assert summary["disagreement"]["not_unanimous"] == split == 8
    with (RECORD / "answers.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        votes = sum(grades[row["model"], int(row["index"])])
        assert (int(row["correct_votes"]), int(row["majority"])) == (votes, int(votes >= 3))


def test_the_saved_grades_of_the_record_are_the_panel_grades() -> None:
    panel = load_reference_panel(PANEL, benchmark=AA_LCR)
    with (RECORD / "answers.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            assert panel.references[row["model"]][int(row["index"])] == int(row["saved_grade"])


def test_the_threshold_report_uses_the_recorded_values() -> None:
    assert (TASK2 / "data" / RECORD_FILE).read_bytes() == (RECORD / RECORD_FILE).read_bytes()
    noise = load_judge_noise(TASK2 / "data" / RECORD_FILE, panel_sha256=_sha(PANEL))
    assert noise is not None
    assert "not all equal for 8 answers (2.7%)" in noise.statement
    assert "The policy interval excludes judge noise" in noise.statement
