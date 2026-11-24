"""The recorded one-word run of #88: its hashes, its approval, and its conclusion."""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_reference.judge_compare import OUTPUT_NAMES, conclusion
from benchmark_reference.judge_prompt import ONE_WORD

DATA = Path(__file__).parents[2] / "docs" / "data"
RECORD = DATA / "task2-aa-lcr-judge-one-word"
JSON_RECORD = DATA / "task2-aa-lcr-judge-rerun"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(name: str) -> Any:
    return json.loads((RECORD / name).read_text(encoding="utf-8"))


def _attempts(folder: Path) -> list[dict[str, Any]]:
    text = (folder / "judgments.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.split("\n")[:-1]]


def _grades(folder: Path) -> dict[tuple[str, int], list[int]]:
    grades: dict[tuple[str, int], list[int]] = defaultdict(list)
    for attempt in _attempts(folder):
        if attempt["status"] == "success":
            key = (attempt["model"], attempt["index"])
            grades[key].append(int(attempt["verdict"] == "CORRECT"))
    return grades


def test_the_record_holds_every_output_with_its_recorded_hash() -> None:
    assert {p.name for p in RECORD.iterdir()} == set(OUTPUT_NAMES)
    manifest = _json("manifest.json")
    assert manifest["output_sha256"] == {
        n: _sha(RECORD / n) for n in OUTPUT_NAMES if n != "manifest.json"
    }
    assert manifest["baseline_run"] == {
        n: _sha(JSON_RECORD / n) for n in ("judgments.jsonl", "run.json")
    }


def test_the_run_used_the_approved_estimate_and_the_judge_of_76() -> None:
    settings = _json("run.json")
    assert settings["estimate_sha256"] == _sha(DATA / "task2-aa-lcr-judge-one-word-estimate.json")
    assert settings["approval_url"].endswith("/issues/88#issuecomment-7119429423")
    json_settings = json.loads((JSON_RECORD / "run.json").read_bytes())
    for name in ("model", "base_url", "temperature"):
        assert settings["estimate"]["judge"][name] == json_settings["estimate"]["judge"][name]
    assert settings["estimate"]["prompt"]["variant"] == ONE_WORD.name


def test_the_record_holds_five_independent_judgments_for_each_answer() -> None:
    attempts = _attempts(RECORD)
    for attempt in attempts:
        assert ONE_WORD.parse(attempt["reply"]).verdict == attempt["verdict"]
    grades = _grades(RECORD)
    assert len(grades) == 300 and {len(g) for g in grades.values()} == {5}
    assert len({a["response_id"] for a in attempts}) == len(attempts) == 1500


def test_the_conclusion_follows_from_the_recorded_judgments() -> None:
    """A second count of the changed answers, with no code of the report."""
    with (JSON_RECORD / "answers.csv").open(encoding="utf-8", newline="") as handle:
        saved = {
            (r["model"], int(r["index"])): int(r["saved_grade"]) for r in csv.DictReader(handle)
        }
    old, new = _grades(RECORD), _grades(JSON_RECORD)
    changed = [key for key in saved if int(sum(new[key]) >= 3) != saved[key]]
    again = sum(sum(old[key]) < 3 for key in changed)
    rule = _json("summary.json")["decision_rule"]
    assert (len(changed), again) == (13, 10) == (rule["answers"], rule["incorrect_again"])
    assert rule["conclusion"] == conclusion(again) == "The prompt explains most of the shift"
    agree = sum(int(sum(old[key]) >= 3) == saved[key] for key in saved)
    assert agree == _json("summary.json")["agreement"]["saved_and_one_word"]["agree"] == 296
    # The single passes are at the boundary of the rule.
    assert [sum(old[key][n] == 0 for key in changed) for n in range(5)] == [10, 9, 9, 10, 10]
