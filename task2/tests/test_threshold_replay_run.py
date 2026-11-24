"""The real-grade replay command end to end, on synthetic grades only.

The public file, the reference panels, and the question mapping are synthetic
copies. The model names are real, because the policy names them, but every
grade is made up. No test opens the downloaded public file.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from replay_fixtures import (
    SEEDS,
    SUBSETS,
    THRESHOLDS,
    World,
    build_world,
    public_models,
    read_rows,
    sha,
)

from benchmark_reference import threshold_policy, threshold_replay_run
from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH
from benchmark_reference.threshold_cli import main
from benchmark_reference.threshold_replay_report import OUTPUT_NAMES, result_section
from benchmark_reference.threshold_replay_run import clean_commit, recorded_replay


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    return build_world(tmp_path_factory.mktemp("world"))


def _open_gates(monkeypatch: pytest.MonkeyPatch, lock: str, recorded: str | None = None) -> None:
    monkeypatch.setattr(threshold_policy, "committed_lock_text", lambda: lock)
    monkeypatch.setattr(threshold_replay_run, "clean_commit", lambda: "c" * 40)
    monkeypatch.setattr(threshold_replay_run, "recorded_replay", lambda: recorded)
    # Each test starts without a marker of an earlier run.
    markers = Path(tempfile.mkdtemp(prefix="replay-markers-"))
    monkeypatch.setattr(threshold_replay_run, "MARKER_DIR", markers)


@pytest.fixture(scope="module")
def output(world: World, tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("replay") / "out"
    with pytest.MonkeyPatch.context() as patch:
        _open_gates(patch, world.lock)
        main(world.argv(folder))
    return folder


def _summary(output: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    return value


def test_the_run_writes_every_output_and_its_hash(output: Path, world: World) -> None:
    assert {p.name for p in output.iterdir()} == set(OUTPUT_NAMES)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name in set(OUTPUT_NAMES) - {"manifest.json"}:
        assert manifest["output_sha256"][name] == sha(output / name)
    assert (manifest["mode"], manifest["real_grades_used"]) == ("real", True)
    assert manifest["commit"] == "c" * 40
    assert manifest["policy"]["sha256"] == sha(world.policy)
    assert manifest["inputs"][world.public.name] == sha(world.public)
    assert manifest["inputs"][world.mapping.name] == sha(world.mapping)
    assert manifest["command_line"].startswith("threshold-decision --policy")
    assert manifest["public_source"]["committed"] is False


def test_each_model_and_threshold_has_one_decision_for_each_seed(output: Path) -> None:
    rows = read_rows(output / "cells.csv")
    keys = {(r["grade_rule"], r["probe"], r["model"], r["threshold"]) for r in rows}
    assert len(keys) == len(rows) == 2 * 2 * 28 * len(THRESHOLDS)
    assert {r["threshold"] for r in rows} == set(THRESHOLDS)
    for row in rows:
        outcomes = [int(row[k]) for k in ("stage1_go", "stage1_no_go", "escalate")]
        assert sum(outcomes) == int(row["decisions"]) == SEEDS
        assert int(row["wrong"]) == outcomes[1 if row["truth"] == "GO" else 0]
        assert float(row["stage1_share"]) == pytest.approx(sum(outcomes[:2]) / SEEDS)
        assert 63 <= float(row["expected_questions"]) <= 315


def test_each_model_has_one_coverage_row_for_each_grade_rule(output: Path) -> None:
    rows = read_rows(output / "coverage.csv")
    assert len(rows) == 2 * 28
    assert {int(r["subsets"]) for r in rows} == {SUBSETS}


def test_the_model_table_matches_the_public_values(output: Path, world: World) -> None:
    public = json.loads(world.public.read_text(encoding="utf-8"))["performances"]
    mapping = json.loads(world.mapping.read_text(encoding="utf-8"))["questions"]
    mapped = {entry["question_id"] for entry in mapping}
    rows = {r["model"]: r for r in read_rows(output / "models.csv")}
    assert len(rows) == 28
    for model, row in rows.items():
        values = [r["pass@1"] for r in public if r["model"] == model and r["question_id"] in mapped]
        assert len(values) == int(row["questions"]) == 315
        assert int(row["primary_full_passes"]) == sum(v >= 50 for v in values)
        assert int(row["secondary_full_passes"]) == sum(v == 100 for v in values)
        assert float(row["mean_pass_at_1"]) == pytest.approx(sum(values) / 315, abs=1e-4)
        assert int(row["neither_0_nor_100"]) == sum(v not in (0, 100) for v in values)


def test_no_output_holds_a_question_identifier(output: Path, world: World) -> None:
    mapping = json.loads(world.mapping.read_text(encoding="utf-8"))["questions"]
    # Identifiers of only digits could be equal to a count by chance.
    names = [e["question_id"] for e in mapping if not e["question_id"].isdigit()]
    for path in output.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not [name for name in names if name in text]


def test_the_hold_out_replays_both_benchmarks_at_the_primary_threshold(output: Path) -> None:
    rows = read_rows(output / "reference_holdout.csv")
    assert {r["benchmark"] for r in rows} == {LIVE_CODE_BENCH, AA_LCR}
    # 2 benchmarks x 3 models x 3 seeds.
    assert len(rows) == 18


def test_the_marks_agree_with_the_tables(output: Path) -> None:
    doc = _summary(output)
    cells = [
        r
        for r in read_rows(output / "cells.csv")
        if (r["grade_rule"], r["probe"]) == ("primary", "stratified")
    ]
    coverage = [r for r in read_rows(output / "coverage.csv") if r["grade_rule"] == "primary"]
    criteria = doc["criteria"]
    worst = max(float(r["wrong_rate"]) for r in cells)
    assert criteria["wrong_decision_rate"]["value"] == pytest.approx(worst)
    assert criteria["wrong_decision_rate"]["passed"] == (worst <= 0.071)
    lowest = min(float(r["coverage"]) for r in coverage)
    assert criteria["coverage"]["value"] == pytest.approx(lowest)
    assert criteria["coverage"]["passed"] == (lowest >= 0.935)
    at = [float(r["expected_cost_fraction"]) for r in cells if r["threshold"] == "0.70"]
    cost = criteria["mean_cost_at_primary_threshold"]
    assert cost["value"] == pytest.approx(sum(at) / 28, abs=1e-5)
    assert cost["passed"] == (sum(at) / 28 < 1)
    assert doc["all_criteria_pass"] == all(c["passed"] for c in criteria.values())


def test_the_report_states_each_mark_each_limit_and_each_disclosure(output: Path) -> None:
    report = (output / "report.md").read_text(encoding="utf-8")
    doc = _summary(output)
    for criterion in doc["criteria"].values():
        assert criterion["statement"] in report
    marks = [line for line in report.splitlines() if line.endswith(("| PASS |", "| FAIL |"))]
    assert len(marks) == 3
    if doc["all_criteria_pass"]:
        assert "passed all 3 pass criteria" in report
    else:
        assert '"full retention" result stays the published claim' in report
    for text in (
        "come from 9 developer groups, and they are not independent",
        "reuse the same grades",
        "It uses the saved answers of the 3 reference models",
        "There are only 3 models.",
        "before the freeze",
        "The models are not independent of each other",
        "The AA-LCR strata come from the question metadata.",
        "https://livecodebench.github.io/performances_generation.json",
        "states no license",
    ):
        assert text in report
    for disclosure in doc["disclosures"].values():
        assert disclosure["policy_text"] in report
        assert disclosure["note"] in report
    for model in public_models():
        assert f"| {model} |" in report
    table = report.split("## Stated comparisons")[1].split("## Results by distance")[0]
    assert "PASS" not in table
    assert "FAIL" not in table


@pytest.mark.parametrize("passed", [True, False])
def test_the_verdict_names_each_failed_criterion_and_the_claim_that_stays(
    output: Path, passed: bool
) -> None:
    doc = _summary(output)
    for criterion in doc["criteria"].values():
        criterion["passed"] = True
    doc["criteria"]["coverage"]["passed"] = passed
    text = result_section(doc)
    assert ("passed all 3 pass criteria" in text) == passed
    failure = "failed 1 of 3 pass criteria: Coverage."
    assert (failure in text) == (not passed)
    assert ('"full retention" result stays the published claim' in text) == (not passed)
    assert text.count("| FAIL |") == (0 if passed else 1)


def test_two_runs_give_the_same_tables(
    output: Path, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_gates(monkeypatch, world.lock)
    second = tmp_path / "out"
    main(world.argv(second))
    for name in ("cells.csv", "coverage.csv", "models.csv", "reference_holdout.csv"):
        assert (second / name).read_bytes() == (output / name).read_bytes()


def _stop(world: World, output: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> str:
    with pytest.raises(SystemExit) as stopped:
        main(world.argv(output, *extra))
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_a_recorded_replay_is_not_run_again(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock, recorded="threshold-policy@v1")
    assert "already records the replay" in _stop(world, tmp_path / "out", capsys)
    assert not (tmp_path / "out").exists()


def test_a_repeated_run_states_its_reason(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_gates(monkeypatch, world.lock, recorded="threshold-policy@v1")
    output = tmp_path / "out"
    main(world.argv(output, "--rerun-reason", "The first run had a code fault in X."))
    assert "The first run had a code fault in X." in (output / "report.md").read_text("utf-8")
    assert _summary(output)["rerun_reason"] == "The first run had a code fault in X."


def test_a_started_run_is_not_started_again_before_its_record(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def crash(*args: object, **kwargs: object) -> None:
        raise AnalysisError("a fault after the grades are open")

    with monkeypatch.context() as patch:
        patch.setattr(threshold_replay_run, "replay_rule", crash)
        assert "a fault after the grades are open" in _stop(world, tmp_path / "one", capsys)
    assert "already started" in _stop(world, tmp_path / "two", capsys)
    main(world.argv(tmp_path / "two", "--rerun-reason", "A fault stopped the first run."))
    markers = list(threshold_replay_run.MARKER_DIR.iterdir())
    lines = [json.loads(line) for line in markers[0].read_text("utf-8").splitlines()]
    assert [line["rerun_reason"] for line in lines] == [None, "A fault stopped the first run."]


def test_a_stop_before_the_grades_uses_no_run(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)
    _stop(world, tmp_path / "out", capsys, "--data-root", str(tmp_path / "no-data"))
    assert not list(threshold_replay_run.MARKER_DIR.iterdir())


def test_an_output_path_that_is_a_file_stops_before_the_run(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)
    (tmp_path / "out").write_text("x", encoding="utf-8")
    assert "is a file" in _stop(world, tmp_path / "out", capsys)
    assert not list(threshold_replay_run.MARKER_DIR.iterdir())


def test_an_uncommitted_change_stops_the_run(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def dirty() -> str:
        raise AnalysisError("the folder has uncommitted changes")

    monkeypatch.setattr(threshold_replay_run, "clean_commit", dirty)
    assert "uncommitted changes" in _stop(world, tmp_path / "out", capsys)


def test_existing_results_are_never_overwritten(
    output: Path, world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _open_gates(monkeypatch, world.lock)
    before = sha(output / "manifest.json")
    assert "never overwrites" in _stop(world, output, capsys)
    assert sha(output / "manifest.json") == before


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("lcb-reference-panel.json", "reference panel SHA-256"),
        ("lcb-public-mapping.json", "mapping SHA-256"),
        ("public.json", "not the pinned"),
    ],
)
def test_an_input_that_differs_from_its_pin_stops_the_run(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
    message: str,
) -> None:
    _open_gates(monkeypatch, world.lock)
    copy = tmp_path / "copy"
    shutil.copytree(world.folder, copy)
    with (copy / name).open("ab") as handle:
        handle.write(b"\n")
    changed = World(
        copy, world.policy, copy / world.public.name, copy / world.mapping.name, world.lock
    )
    assert message in _stop(changed, tmp_path / "out", capsys)
    assert not (tmp_path / "out").exists()


def test_the_grades_stay_closed_until_every_other_input_passes(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("the public grades were read")

    monkeypatch.setattr(threshold_replay_run, "load_public_grades", opened)
    missing = str(tmp_path / "no-data")
    assert "Cannot read predictions" in _stop(
        world, tmp_path / "out", capsys, "--data-root", missing
    )


# The git checks.


def _repository(folder: Path) -> Path:
    for arguments in (
        ("init", "-q"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", "-C", str(folder), *arguments], check=True)
    (folder / "code.py").write_text("x = 1\n", encoding="utf-8")
    _commit(folder)
    return folder


def _commit(folder: Path) -> None:
    subprocess.run(["git", "-C", str(folder), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(folder), "commit", "-q", "-m", "test"], check=True)


def test_clean_commit_gives_head_and_refuses_a_changed_file(tmp_path: Path) -> None:
    folder = _repository(tmp_path)
    assert len(clean_commit(folder)) == 40
    (folder / "code.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(AnalysisError, match="uncommitted changes"):
        clean_commit(folder)


def test_recorded_replay_reads_the_committed_manifest_only(tmp_path: Path) -> None:
    folder = _repository(tmp_path)
    record = folder / "docs" / "data" / "manifest.json"
    assert recorded_replay(record) is None
    record.parent.mkdir(parents=True)
    record.write_text('{"policy": {"key": "threshold-policy@v1"}}', encoding="utf-8")
    assert recorded_replay(record) is None
    _commit(folder)
    assert recorded_replay(record) == "threshold-policy@v1"
