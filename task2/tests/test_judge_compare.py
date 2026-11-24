"""The control run of #88 end to end on loopback, and the fixed decision rule."""

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from judge_fixtures import (
    MODELS,
    QUESTIONS,
    Data,
    Judge,
    Scripted,
    saved_grade,
    scripted_judge,
    verdict,
    write_data,
)

from benchmark_reference.judge_cli import main
from benchmark_reference.judge_compare import (
    CHANGED_ANSWERS,
    OUTPUT_NAMES,
    changed_answers,
    conclusion,
    reference_group,
)
from benchmark_reference.judge_items import load_judge_inputs
from benchmark_reference.judge_report import Verdicts
from benchmark_reference.models import AnalysisError

QWEN = "Qwen/Qwen3-235B-A22B-Instruct-2507"
ANSWERS = len(MODELS) * QUESTIONS
type Key = tuple[str, int]
KEYS: list[Key] = [(m, i) for m in MODELS for i in range(QUESTIONS)]
# The answers that the JSON prompt changes from INCORRECT to CORRECT. All are of model-a.
CHANGED = [key for key in KEYS if not saved_grade(*key)][:13]
# The one-word prompt gives INCORRECT again for the first 11 of them.
AGAIN = CHANGED[:11]
# The one-word prompt changes this saved CORRECT answer, which the JSON prompt does not.
NEW_CHANGE: Key = ("model-c", 0)
# The one-word judgments of this answer are not all equal.
SPLIT: Key = ("model-b", 0)
REFERENCES = {0: "0.1", 3: "45444", 6: "1. a\\n2. b"}


def _key(prompt: str) -> Key:
    model = next(m for m in MODELS if f" of {m}." in prompt)
    return model, int(prompt.split("value of item ")[1].split(",")[0])


def _script(prompt: str, number: int) -> Scripted:
    """The call count of a prompt is its pass number, because one worker sends every request."""
    key = _key(prompt)
    saved = bool(saved_grade(*key))
    if "single JSON object" in prompt:
        return verdict(saved or key in CHANGED)
    correct = (saved or key in CHANGED) and key not in AGAIN and key != NEW_CHANGE
    if key == SPLIT:
        correct = number % 2 == 1
    if key == NEW_CHANGE:
        return Scripted("It is wrong.")
    return Scripted("CORRECT" if correct else "INCORRECT")


def _estimate(data: Data, judge: Judge, path: Path, *extra: str, model: str = QWEN) -> None:
    main(
        [
            "estimate",
            *data.arguments,
            *("--base-url", judge.url, "--judge-model", model),
            *("--input-price", "0.09", "--output-price", "0.55"),
            *("--price-source", "test prices", "--price-date", "2026-11-23"),
            *("--limit-usd", "10", "--output", str(path)),
            *extra,
        ]
    )


@pytest.fixture(scope="module")
def finished(tmp_path_factory: pytest.TempPathFactory) -> tuple[Data, Path]:
    """A complete run of each prompt against one scripted judge, through the command line."""
    folder = tmp_path_factory.mktemp("compare")
    data = write_data(folder, references=REFERENCES)
    with pytest.MonkeyPatch.context() as patch, scripted_judge(_script) as judge:
        patch.setenv("JUDGE_API_KEY", "must-not-be-read-on-loopback")
        one_word = ("--prompt", "one-word", "--baseline-run", str(folder / "json"))
        for name, extra in (("json", ()), ("one-word", one_word)):
            estimate = folder / f"{name}.json"
            _estimate(data, judge, estimate, *extra)
            run = ("--run-dir", str(folder / name), "--workers", "1")
            baseline = extra[2:]
            main(["run", *data.arguments, "--estimate", str(estimate), *run, *baseline])
        assert len(judge.bodies) == ANSWERS * 10
        assert not any("authorization" in {k.lower() for k in h} for h in judge.headers)
    return data, folder


def _compare(finished: tuple[Data, Path], output: Path, *, run: str = "one-word") -> None:
    data, folder = finished
    main(
        [
            "compare",
            *data.arguments,
            *("--run-dir", str(folder / run), "--baseline-run", str(folder / "json")),
            *("--output-dir", str(output)),
        ]
    )


@pytest.fixture(scope="module")
def output(finished: tuple[Data, Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("output") / "out"
    _compare(finished, folder)
    return folder


@pytest.fixture(scope="module")
def summary(output: Path) -> Any:
    return json.loads((output / "summary.json").read_text(encoding="utf-8"))


# The fixed decision rule


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (13, "explains most of the shift"),
        (10, "explains most of the shift"),
        (9, "explains a part of the shift"),
        (4, "explains a part of the shift"),
        (3, "does not explain the shift"),
        (0, "does not explain the shift"),
    ],
)
def test_the_decision_rule_has_the_bounds_of_the_issue(count: int, text: str) -> None:
    assert conclusion(count) == f"The prompt {text}"


@pytest.mark.parametrize("count", [-1, 14])
def test_the_decision_rule_covers_13_answers_only(count: int) -> None:
    with pytest.raises(AnalysisError):
        conclusion(count)


def test_the_rule_needs_exactly_the_13_changes_of_76(finished: tuple[Data, Path]) -> None:
    data, _folder = finished
    inputs = load_judge_inputs(panel_path=data.panel, data_root=data.root, source_csv=data.csv)
    votes: Verdicts = {
        key: (1,) * 5 if saved_grade(*key) or key in CHANGED else (0,) * 5 for key in sorted(KEYS)
    }
    assert changed_answers(votes, inputs) == CHANGED
    assert CHANGED_ANSWERS == len(CHANGED) == 13
    with pytest.raises(AnalysisError, match="12 answers"):
        changed_answers({**votes, CHANGED[0]: (0,) * 5}, inputs)
    with pytest.raises(AnalysisError, match="from CORRECT to INCORRECT"):
        changed_answers({**votes, CHANGED[0]: (0,) * 5, NEW_CHANGE: (0,) * 5}, inputs)


@pytest.mark.parametrize(
    ("reference", "group"),
    [
        ("0.1", "decimal"),
        ("0.0016", "decimal"),
        ("20.8", "other"),
        ("45444", "date"),
        ("91366", "other"),
        ("5000", "other"),
        ("1. H1 2024, \\n2. H1 2022", "list"),
        ("1. a\n2. b", "other"),
        ("$204 million", "other"),
    ],
)
def test_the_reference_groups(reference: str, group: str) -> None:
    assert reference_group(reference) == group


# The comparison


def test_the_summary_applies_the_rule_to_the_changed_answers(summary: Any) -> None:
    assert summary["loopback_test"] is True
    rule = summary["decision_rule"]
    assert (rule["answers"], rule["incorrect_again"]) == (13, 11)
    assert rule["conclusion"] == "The prompt explains most of the shift"
    rows = rule["changed_answers"]
    assert [(r["model"], r["index"]) for r in rows] == CHANGED
    assert [r["one_word_votes"] for r in rows] == [0] * 11 + [5] * 2
    assert {(r["saved_grade"], r["json_votes"]) for r in rows} == {(0, 5)}


def test_the_summary_compares_the_three_sets_of_grades(summary: Any) -> None:
    assert {name: value["agree"] for name, value in summary["agreement"].items()} == {
        "saved_and_one_word": ANSWERS - 2 - 1,
        "saved_and_json": ANSWERS - 13,
        "json_and_one_word": ANSWERS - 11 - 1,
    }
    both = summary["agreement"]["saved_and_one_word"]
    assert (both["incorrect_to_correct"], both["correct_to_incorrect"]) == (2, 1)
    a, b, c = summary["models"]
    assert (a["saved"]["score"], a["saved"]["decision"]) == (0.65, "GO")
    assert (a["json"]["score"], a["one_word"]["score"]) == (39 / 40, 28 / 40)
    assert (a["one_word"]["agree_with_saved"], a["json"]["agree_with_saved"]) == (38, 27)
    assert (b["one_word"]["unequal"], b["json"]["unequal"]) == (1, 0)
    # The split answer is CORRECT in passes 1, 3, and 5.
    assert b["one_word"]["pass_correct"] == [27, 26, 27, 26, 27]
    assert (c["saved"]["score"], c["one_word"]["score"]) == (27 / 40, 26 / 40)
    assert summary["decisions"]["threshold"] == 0.6


def test_the_summary_gives_each_reference_group(summary: Any) -> None:
    groups = {g["group"]: g for g in summary["reference_groups"]}
    assert list(groups) == ["decimal", "date", "list", "other"]
    assert [g["answers"] for g in groups.values()] == [3, 3, 3, 111]
    assert [g["changed"] for g in groups.values()] == [1, 1, 1, 10]
    assert [g["incorrect_again"] for g in groups.values()] == [1, 1, 1, 8]
    # Question 0 is in the decimal group: one change again, one new change, and one split.
    decimal = groups["decimal"]
    assert (decimal["saved_correct"], decimal["json_correct"]) == (2, 3)
    assert (decimal["one_word_correct"], decimal["one_word_unequal"]) == (1, 1)
    assert (decimal["one_word_agree_with_saved"], decimal["json_agree_with_saved"]) == (2, 2)


def test_the_summary_counts_replies_that_are_not_one_word(summary: Any) -> None:
    assert summary["replies"]["judgments"] == ANSWERS * 5
    assert summary["replies"]["not_one_word"] == 5


def test_the_outputs_keep_every_judgment_and_the_manifest_hashes_them(
    finished: tuple[Data, Path], output: Path, tmp_path: Path
) -> None:
    _compare(finished, tmp_path / "again")
    assert {p.name for p in output.iterdir()} == set(OUTPUT_NAMES)
    for name in OUTPUT_NAMES:
        assert (output / name).read_bytes() == (tmp_path / "again" / name).read_bytes()
    lines = (output / "judgments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == ANSWERS * 5
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["output_sha256"] == {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in OUTPUT_NAMES
        if name != "manifest.json"
    }
    _data, folder = finished
    assert manifest["baseline_run"]["judgments.jsonl"] == (
        hashlib.sha256((folder / "json" / "judgments.jsonl").read_bytes()).hexdigest()
    )
    rows = list(csv.DictReader(io.StringIO((output / "answers.csv").read_text(encoding="utf-8"))))
    assert len(rows) == ANSWERS
    (split,) = [r for r in rows if (r["model"], r["index"]) == ("model-b", "0")]
    assert [split[f"one_word_pass_{n}"] for n in range(1, 6)] == ["1", "0", "1", "0", "1"]
    assert sum(int(r["changed_by_json_prompt"]) for r in rows) == 13


def test_the_report_gives_the_rule_the_settings_and_the_limit(output: Path) -> None:
    text = (output / "report.md").read_text(encoding="utf-8")
    for part in (
        "It measures nothing.",
        "11 of the 13 answers are INCORRECT again.",
        "**The prompt explains most of the shift.**",
        "| 10 to 13 | The prompt explains most of the shift |",
        "does not separate the prompt from the endpoint, the precision, and the date",
        QWEN,
        "Temperature | 0.0 | 0.0",
        "Maximum output tokens | 4096 | 1024",
        "https://github.com/modelscope/evalscope",
        "v1.4.2",
        "Run dates (UTC)",
    ):
        assert part in text


# Refused commands


def test_compare_and_report_refuse_the_other_prompt(
    finished: tuple[Data, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        _compare(finished, tmp_path / "out", run="json")
    assert stop.value.code == 2
    assert "one-word prompt" in capsys.readouterr().err
    data, folder = finished
    record = tmp_path / "record.json"
    arguments = ("--run-dir", str(folder / "one-word"), "--output-dir", str(tmp_path / "out"))
    with pytest.raises(SystemExit) as stop:
        main(["report", *data.arguments, *arguments, "--record", str(record)])
    assert stop.value.code == 2
    with pytest.raises(SystemExit):
        main(["report", *data.arguments, *arguments])
    assert "aa-lcr-judge compare" in capsys.readouterr().err
    assert not (tmp_path / "out").exists() and not record.exists()


def test_the_one_word_estimate_needs_the_judge_and_the_endpoint_of_the_json_run(
    finished: tuple[Data, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data, folder = finished
    path = tmp_path / "estimate.json"
    arguments = ("--prompt", "one-word", "--baseline-run", str(folder / "json"))
    settings = json.loads((folder / "json" / "run.json").read_bytes())
    same_endpoint = Judge(url=settings["estimate"]["judge"]["base_url"])
    cases = (
        (Judge(url="http://127.0.0.1:9/v1"), QWEN),
        (same_endpoint, "qwen-3-235b-a22b-instruct-2507"),
    )
    for judge, model in cases:
        with pytest.raises(SystemExit) as stop:
            _estimate(data, judge, path, *arguments, model=model)
        assert stop.value.code == 2
        assert "baseline run used" in capsys.readouterr().err
        assert not path.exists()
    _estimate(data, same_endpoint, path, *arguments)
    assert json.loads(path.read_bytes())["prompt"]["variant"] == "one-word"


def test_a_one_word_run_checks_the_baseline_before_its_first_request(
    finished: tuple[Data, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default baseline is the recorded run of #76, at another endpoint."""
    data, folder = finished
    estimate = ("--estimate", str(folder / "one-word.json"))
    with pytest.raises(SystemExit) as stop:
        main(["run", *data.arguments, *estimate, "--run-dir", str(tmp_path / "run")])
    assert stop.value.code == 2
    assert "baseline run used" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()
