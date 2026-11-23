"""The aa-lcr-judge command end to end on loopback, and the values of its report."""

import csv
import hashlib
import io
import json
import shutil
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from judge_fixtures import MODELS, QUESTIONS, Data, Judge, scripted_judge, verdict, write_data

from benchmark_reference.judge_cli import main
from benchmark_reference.judge_items import load_judge_inputs
from benchmark_reference.judge_report import (
    OUTPUT_NAMES,
    interval_widths,
    load_run,
    majority,
    pass_scores,
)
from benchmark_reference.judge_statement import RECORD_FILE, load_judge_noise
from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import AA_LCR, load_reference_panel
from benchmark_reference.threshold_policy import load_policy
from benchmark_reference.threshold_replay import hold_out_references

TASK2 = Path(__file__).parents[1]
V1 = TASK2 / "policies" / "threshold-v1.json"
QWEN = "Qwen/Qwen3-235B-A22B-Instruct-2507"
ANSWERS = len(MODELS) * QUESTIONS


def _index(prompt: str) -> int:
    return int(prompt.split("value of item ")[1].split(",")[0])


def _model(prompt: str) -> str:
    return next(m for m in MODELS if f" of {m}." in prompt)


def _script(prompt: str, number: int) -> Any:
    """model-a has 24 of 40 in odd passes and 23 in even passes. The others do not change.

    The threshold 0.60 is 24 of 40. The call count of a prompt is its pass number only
    when one worker sends every request.
    """
    index, model = _index(prompt), _model(prompt)
    if model == "model-a":
        return verdict(index < 23 or (index == 23 and number % 2 == 1))
    return verdict(index < (30 if model == "model-b" else 10))


def _command(data: Data, name: str, *arguments: str) -> None:
    main([name, *data.arguments, *arguments])


def _estimate(data: Data, judge: Judge, path: Path, *extra: str) -> None:
    _command(
        data,
        "estimate",
        *("--base-url", judge.url, "--judge-model", QWEN),
        *("--input-price", "0.09", "--output-price", "0.55"),
        *("--price-source", "test prices", "--price-date", "2026-11-23"),
        *("--limit-usd", "10", "--output", str(path)),
        *extra,
    )


@pytest.fixture(scope="module")
def finished(tmp_path_factory: pytest.TempPathFactory) -> tuple[Data, Path]:
    """The data and the folder of one complete loopback run, through the command line."""
    folder = tmp_path_factory.mktemp("judge")
    data = write_data(folder)
    with pytest.MonkeyPatch.context() as patch, scripted_judge(_script) as judge:
        patch.setenv("JUDGE_API_KEY", "must-not-be-read-on-loopback")
        _estimate(data, judge, folder / "estimate.json")
        _command(
            data,
            "run",
            *("--estimate", str(folder / "estimate.json")),
            *("--run-dir", str(folder / "run"), "--workers", "1"),
        )
        assert len(judge.bodies) == ANSWERS * 5
        assert not any("Authorization" in h for h in judge.headers)
    return data, folder


def _report(
    finished: tuple[Data, Path], output: Path, *extra: str, run: Path | None = None
) -> None:
    data, folder = finished
    _command(
        data,
        "report",
        *("--run-dir", str(run or folder / "run"), "--output-dir", str(output)),
        *extra,
    )


def _summary(output: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    return value


def test_command_measures_the_scripted_noise(finished: tuple[Data, Path], tmp_path: Path) -> None:
    output = tmp_path / "out"
    _report(finished, output)
    assert {p.name for p in output.iterdir()} == set(OUTPUT_NAMES)
    summary = _summary(output)
    assert summary["loopback_test"] is True
    assert summary["disagreement"] == {
        "answers": ANSWERS,
        "not_unanimous": 1,
        "share": round(1 / ANSWERS, 6),
        "correct_votes": {"0": 56, "3": 1, "5": 63},
    }
    a, b, c = summary["models"]
    assert a["pass_correct"] == [24, 23, 24, 23, 24]
    assert (a["lowest_score"], a["highest_score"], a["score_range"]) == (0.575, 0.6, 0.025)
    assert a["pass_decisions"] == ["GO", "NO GO", "GO", "NO GO", "GO"]
    # 3 GO passes and 2 NO GO passes give 6 pairs that differ.
    assert (a["decision_changes"], a["pass_pairs_that_differ"]) == (True, 6)
    assert a["score_standard_deviation"] == pytest.approx(0.013693, abs=1e-6)
    assert (b["score_range"], set(b["pass_decisions"])) == (0.0, {"GO"})
    assert (c["score_range"], set(c["pass_decisions"])) == (0.0, {"NO GO"})
    assert summary["decisions"] == {
        "threshold": 0.6,
        "models": 3,
        "models_that_change": 1,
        "pass_pairs_that_differ": 6,
        "pass_pairs": 30,
    }
    assert summary["full_set_score"] == {"largest_range": 0.025}


def test_agreement_compares_the_majority_with_the_saved_judgment(
    finished: tuple[Data, Path], tmp_path: Path
) -> None:
    output = tmp_path / "out"
    _report(finished, output)
    rows = list(csv.DictReader(io.StringIO((output / "answers.csv").read_text(encoding="utf-8"))))
    assert len(rows) == ANSWERS
    agree = sum(r["majority"] == r["saved_grade"] for r in rows)
    agreement = _summary(output)["agreement_with_saved_judgment"]
    assert agreement["agree"] == agree == sum(int(r["agrees_with_saved"]) for r in rows)
    assert agreement["share"] == round(agree / ANSWERS, 6)
    changed = (
        agreement["saved_correct_majority_incorrect"]
        + agreement["saved_incorrect_majority_correct"]
    )
    assert agree + changed == ANSWERS


def test_outputs_keep_every_judgment_and_the_manifest_hashes_them(
    finished: tuple[Data, Path], tmp_path: Path
) -> None:
    _report(finished, tmp_path / "one")
    _report(finished, tmp_path / "two")
    for name in OUTPUT_NAMES:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    lines = (tmp_path / "one" / "judgments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == ANSWERS * 5
    manifest = json.loads((tmp_path / "one" / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["output_sha256"].items():
        data = (tmp_path / "one" / name).read_bytes()
        assert digest == hashlib.sha256(data).hexdigest()
    assert set(manifest["output_sha256"]) == set(OUTPUT_NAMES) - {"manifest.json"}


def test_report_names_the_judge_its_settings_and_the_exclusion(
    finished: tuple[Data, Path], tmp_path: Path
) -> None:
    _report(finished, tmp_path / "out")
    text = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "This run uses the same model" in text
    assert "The judgments are not all equal for 1 of 120 answers (0.8%)." in text
    assert "1 of 3 full-set decisions change between passes" in text
    assert "It excludes judge noise." in text
    assert "It measures nothing." in text
    for setting in (QWEN, "Temperature | 0.0", "no change", "Run dates (UTC)"):
        assert setting in text


def test_stage1_width_is_the_width_of_the_policy_decision(finished: tuple[Data, Path]) -> None:
    data, _folder = finished
    panel = load_reference_panel(data.panel, benchmark=AA_LCR)
    policy = load_policy(V1).benchmarks[AA_LCR]
    widths = interval_widths(panel, policy)

    class NoCosts:
        full = None

        def tokens(self, _questions: object) -> None:
            return None

    costs: Any = NoCosts()
    for row in hold_out_references(panel, policy, costs):
        width = row.result.stage1_upper - row.result.stage1_lower
        assert widths[row.model][policy.seeds.index(row.seed)] == width
    assert {len(w) for w in widths.values()} == {len(policy.seeds)}


def test_the_real_panel_gives_the_v1_interval_width() -> None:
    panel = load_reference_panel(TASK2 / "data" / "aa-lcr-reference-panel.json", benchmark=AA_LCR)
    widths = interval_widths(panel, load_policy(V1).benchmarks[AA_LCR])
    values = [w for model in widths.values() for w in model]
    assert len(values) == 60
    assert sum(values, Fraction(0)) / len(values) == Fraction(223, 750)
    assert (min(values), max(values)) == (Fraction(27, 100), Fraction(31, 100))


def test_report_refuses_an_incomplete_or_changed_run(
    finished: tuple[Data, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _data, folder = finished
    lines = (folder / "run" / "judgments.jsonl").read_text(encoding="utf-8").splitlines(True)
    first = json.loads(lines[0])
    flipped = {**first, "verdict": "INCORRECT" if first["verdict"] == "CORRECT" else "CORRECT"}
    cases = {
        "holds 599 of 600 judgments": lines[1:],
        "repeats attempt": [*lines, lines[0]],
        "two judgments": [*lines, json.dumps({**first, "attempt": 2}) + "\n"],
        "differs from its reply": [json.dumps(flipped) + "\n", *lines[1:]],
        "another answer": [*lines, json.dumps({**first, "pass": 6}) + "\n"],
        "prompt of": [json.dumps({**first, "prompt_sha256": "0"}) + "\n", *lines[1:]],
    }
    for number, (message, changed) in enumerate(cases.items()):
        run = tmp_path / f"run-{number}"
        shutil.copytree(folder / "run", run)
        (run / "judgments.jsonl").write_text("".join(changed), encoding="utf-8", newline="\n")
        with pytest.raises(SystemExit) as stop:
            _report(finished, tmp_path / "out", run=run)
        assert stop.value.code == 2
        assert message in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_a_loopback_run_cannot_write_the_measured_record(
    finished: tuple[Data, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        _report(finished, tmp_path / "out", "--record", str(tmp_path / RECORD_FILE))
    assert "measures nothing" in capsys.readouterr().err
    _report(finished, tmp_path / "out")
    with pytest.raises(AnalysisError, match="loopback test"):
        data, _folder = finished
        panel = load_reference_panel(data.panel, benchmark=AA_LCR)
        load_judge_noise(tmp_path / "out" / RECORD_FILE, panel_sha256=panel.sha256)


def test_an_estimate_file_is_never_replaced(
    finished: tuple[Data, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    data, folder = finished
    with scripted_judge(_script) as judge, pytest.raises(SystemExit):
        _estimate(data, judge, folder / "estimate.json")
    assert "must not change" in capsys.readouterr().err


def test_majority_and_pass_scores() -> None:
    assert [majority(g) for g in ((1, 1, 1, 0, 0), (1, 1, 0, 0, 0))] == [1, 0]
    verdicts: Mapping[tuple[str, int], tuple[int, ...]] = {
        ("m", 0): (1, 0, 1, 1, 1),
        ("m", 1): (1, 1, 0, 0, 0),
    }
    assert pass_scores(dict(verdicts)) == {"m": (2, 1, 1, 1, 1)}


def test_load_run_gives_the_grades_in_pass_order(finished: tuple[Data, Path]) -> None:
    data, folder = finished
    inputs = load_judge_inputs(panel_path=data.panel, data_root=data.root, source_csv=data.csv)
    record = load_run(folder / "run", inputs)
    assert record.verdicts["model-a", 23] == (1, 0, 1, 0, 1)
