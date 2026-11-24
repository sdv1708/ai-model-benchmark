"""The reference-panel study command end to end, on synthetic grades only."""

import json
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from policy_fixtures import TASK2, write_policy
from replay_fixtures import SEEDS, SUBSETS, THRESHOLDS, World, build_world, read_rows, sha

from benchmark_reference import (
    threshold_panel_study_run,
    threshold_policy,
    threshold_replay_run,
)
from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_cli import main as replay_main
from benchmark_reference.threshold_panel_study import (
    Variant,
    full_panel_policy,
    study_variants,
    unit_costs,
)
from benchmark_reference.threshold_panel_study_cli import main
from benchmark_reference.threshold_panel_study_report import (
    OUTPUT_NAMES,
    panel_text,
    random_comparisons,
    random_distance_text,
    random_text,
    variant_text,
    verdict_text,
)
from benchmark_reference.threshold_policy import load_policy
from benchmark_reference.threshold_replay import ReplayCell
from benchmark_reference.threshold_replay_report import CRITERION_TITLES

ARMS = ("315", "1055")
# The variants of the policy: the result, the secondary group count, the secondary grade rule.
VARIANTS = (("primary", "4"), ("primary", "8"), ("secondary", "4"))


def _argv(world: World, record: Path, output: Path, *extra: str) -> list[str]:
    return [
        *("--policy", str(world.policy), "--panel-dir", str(world.folder)),
        *("--public-file", str(world.public), "--mapping", str(world.mapping)),
        *("--replay-record", str(record), "--output-dir", str(output)),
        *("--workers", "1", *extra),
    ]


def _open_gates(monkeypatch: pytest.MonkeyPatch, lock: str, recorded: str | None = None) -> None:
    monkeypatch.setattr(threshold_policy, "committed_lock_text", lambda: lock)
    monkeypatch.setattr(threshold_panel_study_run, "clean_commit", lambda *folder: "c" * 40)
    monkeypatch.setattr(threshold_panel_study_run, "recorded_study", lambda: recorded)
    # Each test starts without a marker of an earlier run.
    markers = Path(tempfile.mkdtemp(prefix="study-markers-"))
    monkeypatch.setattr(threshold_panel_study_run, "MARKER_DIR", markers)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    return build_world(tmp_path_factory.mktemp("world"))


@pytest.fixture(scope="module")
def record(world: World, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real replay of the synthetic policy: the record that the study reads."""
    folder = tmp_path_factory.mktemp("record") / "task2-real-replay"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(threshold_policy, "committed_lock_text", lambda: world.lock)
        patch.setattr(threshold_replay_run, "clean_commit", lambda: "c" * 40)
        patch.setattr(threshold_replay_run, "recorded_replay", lambda: None)
        patch.setattr(threshold_replay_run, "MARKER_DIR", folder.parent / "markers")
        replay_main(world.argv(folder))
    return folder


@pytest.fixture(scope="module")
def output(world: World, record: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("study") / "out"
    with pytest.MonkeyPatch.context() as patch:
        _open_gates(patch, world.lock)
        main(_argv(world, record, folder))
    return folder


def _summary(output: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    return value


def _report(output: Path) -> str:
    return (output / "report.md").read_text(encoding="utf-8")


# The settings come from the policy.


def test_every_study_value_comes_from_the_frozen_policy() -> None:
    loaded = load_policy(TASK2 / "policies" / "threshold-v1.json")
    assert study_variants(loaded) == (
        Variant("primary", 50, 4),
        Variant("primary", 50, 8),
        Variant("secondary", 100, 4),
    )
    section = loaded.benchmarks["live_code_bench_v5"]
    assert full_panel_policy(loaded) == replace(section, stage1_size=211)
    assert section.stage1_size == 63


# The outputs.


def test_the_run_writes_every_output_and_its_hash(output: Path, world: World, record: Path) -> None:
    assert {p.name for p in output.iterdir()} == set(OUTPUT_NAMES)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name in set(OUTPUT_NAMES) - {"manifest.json"}:
        assert manifest["output_sha256"][name] == sha(output / name)
    assert manifest["command_line"].startswith("threshold-panel-study --policy")
    assert (manifest["commit"], manifest["rerun_reason"]) == ("c" * 40, None)
    assert manifest["policy"]["sha256"] == sha(world.policy)
    assert manifest["inputs"][world.public.name] == sha(world.public)
    assert manifest["inputs"]["replay manifest.json"] == sha(record / "manifest.json")
    assert manifest["public_source"]["committed"] is False


def test_each_arm_model_and_threshold_has_one_decision_for_each_seed(output: Path) -> None:
    rows = read_rows(output / "cells.csv")
    fields = ("arm", "grade_rule", "groups", "probe", "model", "threshold")
    keys = {tuple(r[f] for f in fields) for r in rows}
    # 3 variants and the random probe of 2 grade rules, in each of 2 arms.
    assert len(keys) == len(rows) == 2 * (3 + 2) * 28 * len(THRESHOLDS)
    for row in rows:
        outcomes = [int(row[k]) for k in ("stage1_go", "stage1_no_go", "escalate")]
        assert sum(outcomes) == int(row["decisions"]) == SEEDS
        assert int(row["wrong"]) == outcomes[1 if row["truth"] == "GO" else 0]
        decided = sum(outcomes[:2])
        assert float(row["stage1_share"]) == pytest.approx(decided / SEEDS)
        questions, size = {"315": (315, 63), "1055": (1055, 211)}[row["arm"]]
        expected = (decided * size + outcomes[2] * questions) / SEEDS
        assert float(row["expected_questions"]) == pytest.approx(expected, abs=1e-3)
        assert (row["expected_tokens_mean"] == "") == (row["arm"] == "1055")
        assert (row["coverage"] == "") == (row["probe"] == "random")


def test_the_full_score_uses_every_question_of_the_arm(output: Path, world: World) -> None:
    public = json.loads(world.public.read_text(encoding="utf-8"))["performances"]
    mapping = json.loads(world.mapping.read_text(encoding="utf-8"))["questions"]
    mapped = {entry["question_id"] for entry in mapping}
    passes: dict[tuple[str, str, str], int] = {}
    for r in public:
        for rule, minimum in (("primary", 50), ("secondary", 100)):
            good = int(r["pass@1"] >= minimum)
            full = ("1055", rule, r["model"])
            passes[full] = passes.get(full, 0) + good
            if r["question_id"] in mapped:
                part = ("315", rule, r["model"])
                passes[part] = passes.get(part, 0) + good
    for row in read_rows(output / "cells.csv"):
        key = (row["arm"], row["grade_rule"], row["model"])
        assert int(row["full_passes"]) == passes[key]


def test_each_variant_has_one_coverage_row_for_each_model(output: Path) -> None:
    rows = read_rows(output / "coverage.csv")
    assert len(rows) == 2 * 3 * 28
    assert {int(r["subsets"]) for r in rows} == {SUBSETS}
    assert {(r["grade_rule"], r["groups"]) for r in rows} == set(VARIANTS)


def test_the_strata_table_names_the_outside_models_and_near_equal_sizes(output: Path) -> None:
    rows = read_rows(output / "strata.csv")
    # 9 developer groups, with 4, 8, and 4 strata, in each of 2 arms.
    assert len(rows) == 2 * 9 * (4 + 8 + 4)
    by_developer = {r["target_developer"]: int(r["reference_models"]) for r in rows}
    assert by_developer["OpenAI"] == 18
    assert by_developer["xAI"] == 27
    for arm, questions in (("315", 315), ("1055", 1055)):
        for rule, groups in VARIANTS:
            mine = [
                int(r["questions"])
                for r in rows
                if (r["arm"], r["grade_rule"], r["groups"], r["target_developer"])
                == (arm, rule, groups, "OpenAI")
            ]
            assert sum(mine) == questions
            assert max(mine) - min(mine) <= 1


def test_the_distance_table_counts_every_primary_cell_once(output: Path) -> None:
    rows = read_rows(output / "distance.csv")
    for arm, probes in (
        ("315", ("three_model", "public_panel", "random")),
        ("1055", ("public_panel", "random")),
    ):
        assert {r["probe"] for r in rows if r["arm"] == arm} == set(probes)
        for probe in probes:
            mine = [r for r in rows if (r["arm"], r["probe"]) == (arm, probe)]
            assert sum(int(r["cells"]) for r in mine) == 28 * len(THRESHOLDS)
            assert sum(int(r["decisions"]) for r in mine) == 28 * len(THRESHOLDS) * SEEDS


def test_the_model_table_has_one_row_for_each_arm_and_model(output: Path) -> None:
    rows = read_rows(output / "models.csv")
    assert len({(r["arm"], r["model"]) for r in rows}) == len(rows) == 2 * 28
    for row in rows:
        three = row["three_model_stage1_share_at_primary"]
        assert (three == "") == (row["arm"] == "1055")


def test_no_output_holds_a_question_identifier(output: Path, world: World) -> None:
    mapping = json.loads(world.mapping.read_text(encoding="utf-8"))["questions"]
    # Identifiers of only digits could be equal to a count by chance.
    names = [e["question_id"] for e in mapping if not e["question_id"].isdigit()]
    for path in output.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not [name for name in [*names, "other-1"] if name in text]


def test_the_random_probe_and_the_targets_agree_with_the_recorded_replay(
    output: Path, record: Path
) -> None:
    fields = ("full_passes", "stage1_go", "stage1_no_go", "escalate", "wrong")

    def facts(path: Path, arm: str | None) -> dict[tuple[str, ...], list[str]]:
        return {
            (r["grade_rule"], r["model"], r["threshold"]): [r[f] for f in fields]
            for r in read_rows(path)
            if r["probe"] == "random" and r.get("arm") == arm
        }

    assert facts(output / "cells.csv", "315") == facts(record / "cells.csv", None)
    assert _summary(output)["arms"]["315"]["random_probe_equals_record"] is True


def test_the_three_model_result_is_the_recorded_result(output: Path, record: Path) -> None:
    recorded = json.loads((record / "summary.json").read_text(encoding="utf-8"))
    expected = recorded["grade_rules"]["primary"]["probes"]["stratified"]
    found = _summary(output)["arms"]["315"]["probes"]["three_model"]
    for scope in ("primary_threshold", "all_thresholds"):
        for key in ("stage1_decisions", "stage1_share", "wrong", "max_wrong_rate"):
            if key == "stage1_decisions":
                value = found[scope]["go"] + found[scope]["no_go"]
            else:
                value = found[scope][key]
            assert value == expected[scope][key]
        mean = expected[scope]["mean_cost_fraction"]["mean"]
        assert found[scope]["mean_token_fraction"] == pytest.approx(mean, abs=1e-5)
    assert found["min_coverage"] == recorded["grade_rules"]["primary"]["min_coverage"]


@pytest.mark.parametrize("arm", ARMS)
def test_the_marks_of_each_arm_agree_with_the_tables(output: Path, arm: str) -> None:
    criteria = _summary(output)["arms"][arm]["criteria"]
    cells = [
        r
        for r in read_rows(output / "cells.csv")
        if (r["arm"], r["grade_rule"], r["groups"], r["probe"])
        == (arm, "primary", "4", "public_panel")
    ]
    coverage = [
        r
        for r in read_rows(output / "coverage.csv")
        if (r["arm"], r["grade_rule"], r["groups"]) == (arm, "primary", "4")
    ]
    worst = max(float(r["wrong_rate"]) for r in cells)
    assert criteria["wrong_decision_rate"]["value"] == pytest.approx(worst)
    assert criteria["wrong_decision_rate"]["passed"] == (worst <= 0.071)
    lowest = min(float(r["coverage"]) for r in coverage)
    assert criteria["coverage"]["value"] == pytest.approx(lowest)
    assert criteria["coverage"]["passed"] == (lowest >= 0.935)
    cost = criteria["mean_cost_at_primary_threshold"]
    at = [float(r["expected_question_fraction"]) for r in cells if r["threshold"] == "0.70"]
    if arm == "1055":
        assert cost["value"] == pytest.approx(sum(at) / 28, abs=1e-5)
    assert cost["passed"] == (sum(at) / 28 < 1)


# The report.


def test_the_report_states_each_mark_each_arm_and_each_limit(output: Path) -> None:
    report, doc = _report(output), _summary(output)
    marks = [line for line in report.splitlines() if line.endswith(("| PASS |", "| FAIL |"))]
    assert len(marks) == 6
    for arm in doc["arms"].values():
        assert verdict_text(arm) in report
        for text in (random_text(doc, arm), variant_text(doc, arm), random_distance_text(arm)):
            for line in text.splitlines():
                assert line in report
    for text in (
        "The public file has no token counts, so the cost of this arm is in questions.",
        "3-model strata (#63)",
        "outside the developer group of the target",
        "come from 9 developer groups, and they are not independent",
        "reuse the same grades",
        "The policy leaves two points open, and this code chooses them.",
        "Simulated (#60), 315 questions, threshold 0.70",
        "315 questions, public-panel strata, threshold 0.70",
        "states no license",
        "git HEAD and the start marker recorded no earlier run of this study.",
    ):
        assert text in report
    for disclosure in doc["disclosures"].values():
        assert disclosure["policy_text"] in report


def test_the_side_by_side_table_has_three_results_and_the_full_arm_two(output: Path) -> None:
    report = _report(output)
    mapped = report.split("## The 315-question arm")[1].split("## The 1,055-question arm")[0]
    full = report.split("## The 1,055-question arm")[1].split("## Share decided")[0]
    for title in ("3-model strata (#63)", "public-panel strata", "random probe"):
        assert f"| Threshold 0.70 | {title} |" in mapped
    assert "| Threshold 0.70 | 3-model strata (#63) |" not in full
    assert "Cost, tokens" in mapped
    assert "Cost, tokens" not in full


def test_the_distance_section_has_both_arms(output: Path) -> None:
    section = _report(output).split("## Share decided at stage 1 by distance")[1]
    head = section.split("| Distance from the threshold |")[1].splitlines()[0]
    for text in ("315: cells", "315: public-panel strata", "1,055: cells", "1,055: random probe"):
        assert text in head


@pytest.mark.parametrize("failed", [None, "coverage"])
def test_the_verdict_names_each_failed_criterion(output: Path, failed: str | None) -> None:
    arm = _summary(output)["arms"]["1055"]
    for key, criterion in arm["criteria"].items():
        criterion["passed"] = key != failed
    text = verdict_text(arm)
    if failed is None:
        assert text == "**The 1,055-question arm passed all 3 pass criteria of the policy.**"
    else:
        assert f"failed 1 of 3 pass criteria: {CRITERION_TITLES[failed]}." in text


def _cell(probe: str, decided: int, wrong: int) -> ReplayCell:
    return ReplayCell(
        model="m",
        probe=probe,
        threshold="0.70",
        full_passes=30,
        population=60,
        truth="NO GO",
        draws=100,
        go=wrong,
        no_go=decided - wrong,
        escalated=100 - decided,
        questions=Fraction(1),
        tokens=unit_costs([0]).full,
    )


@pytest.mark.parametrize(
    ("random", "share", "wrong", "flag"),
    [
        ((50, 3), "better", "worse", "equal or better on decided share."),
        ((40, 2), "equal", "equal", "equal or better on decided share and wrong decisions."),
        ((30, 1), "worse", "better", "equal or better on wrong decisions."),
        ((30, 3), "worse", "worse", "The random probe is worse on both measures."),
    ],
)
def test_the_report_says_where_the_random_probe_is_equal_or_better(
    random: tuple[int, int], share: str, wrong: str, flag: str
) -> None:
    probes: dict[str, Sequence[ReplayCell]] = {
        "public_panel": [_cell("stratified", 40, 2)],
        "random": [_cell("random", *random)],
    }
    records = random_comparisons(probes, "0.70")
    assert [r["scope"] for r in records] == ["primary_threshold", "all_thresholds"]
    for r in records:
        assert (r["stage1_share_verdict"], r["wrong_verdict"]) == (share, wrong)
    text = random_text({"primary_threshold": "0.70"}, {"random_comparisons": records})
    assert text.count(flag) == 2


# The run happens one time, with the pinned inputs only.


def test_the_workers_do_not_change_the_tables(
    output: Path, world: World, record: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_gates(monkeypatch, world.lock)
    second = tmp_path / "out"
    main([*_argv(world, record, second)[:-2], "--workers", "3"])
    for name in ("cells.csv", "coverage.csv", "models.csv", "strata.csv", "distance.csv"):
        assert (second / name).read_bytes() == (output / name).read_bytes()


def _stop(
    world: World, record: Path, output: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> str:
    with pytest.raises(SystemExit) as stopped:
        main(_argv(world, record, output, *extra))
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_the_draft_policy_is_refused(
    world: World, record: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = replace(world, policy=TASK2 / "policies" / "threshold-draft.json")
    assert "not marked frozen" in _stop(draft, record, tmp_path / "out", capsys)


def test_a_frozen_policy_with_another_hash_is_refused(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(
        monkeypatch,
        json.dumps({"schema_version": 1, "policies": {"threshold-policy@v1": "0" * 64}}),
    )
    assert "hash mismatch" in _stop(world, record, tmp_path / "out", capsys)


def test_a_later_frozen_policy_is_refused_because_the_replay_record_is_of_v1(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = json.loads(world.policy.read_text(encoding="utf-8")) | {"version": "v2"}
    policy = write_policy(tmp_path / "v2.json", value)
    lock = json.dumps({"schema_version": 1, "policies": {"threshold-policy@v2": sha(policy)}})
    _open_gates(monkeypatch, lock)
    later = replace(world, policy=policy)
    assert "is of policy SHA-256" in _stop(later, record, tmp_path / "out", capsys)
    assert not list(threshold_panel_study_run.MARKER_DIR.iterdir())


def test_a_recorded_study_is_not_run_again(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock, recorded="threshold-policy@v1")
    error = _stop(world, record, tmp_path / "out", capsys)
    assert "already records the reference-panel study" in error
    assert not (tmp_path / "out").exists()


def test_a_started_run_needs_a_reason_and_the_report_states_it(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def crash(*args: object, **kwargs: object) -> None:
        raise AnalysisError("a fault after the grades are open")

    with monkeypatch.context() as patch:
        patch.setattr(threshold_panel_study_run, "run_variant", crash)
        assert "a fault after the grades are open" in _stop(world, record, tmp_path / "one", capsys)
    assert "already started" in _stop(world, record, tmp_path / "two", capsys)
    main(_argv(world, record, tmp_path / "two", "--rerun-reason", "A fault in X stopped it."))
    assert "A fault in X stopped it." in _report(tmp_path / "two")
    markers = list(threshold_panel_study_run.MARKER_DIR.iterdir())
    lines = [json.loads(line) for line in markers[0].read_text("utf-8").splitlines()]
    assert [line["rerun_reason"] for line in lines] == [None, "A fault in X stopped it."]


def test_the_grades_stay_closed_until_every_other_input_passes(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("the public grades were read")

    monkeypatch.setattr(threshold_panel_study_run, "load_public_grades", opened)
    missing = ("--data-root", str(tmp_path / "no-data"))
    assert "Cannot read predictions" in _stop(world, record, tmp_path / "out", capsys, *missing)
    assert not list(threshold_panel_study_run.MARKER_DIR.iterdir())


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
    record: Path,
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
    assert message in _stop(changed, record, tmp_path / "out", capsys)


def test_an_uncommitted_change_stops_the_run(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)

    def dirty(*folder: Path) -> str:
        raise AnalysisError("the folder has uncommitted changes")

    monkeypatch.setattr(threshold_panel_study_run, "clean_commit", dirty)
    assert "uncommitted changes" in _stop(world, record, tmp_path / "out", capsys)


def test_existing_results_are_never_overwritten(
    output: Path,
    world: World,
    record: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)
    before = sha(output / "manifest.json")
    assert "never overwrites" in _stop(world, record, output, capsys)
    assert sha(output / "manifest.json") == before


def test_the_study_never_writes_into_the_replay_record(
    world: World,
    record: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _open_gates(monkeypatch, world.lock)
    before = {p.name: sha(p) for p in record.iterdir()}
    assert "inside the input data" in _stop(world, record, record / "study", capsys)
    assert {p.name: sha(p) for p in record.iterdir()} == before


@pytest.mark.parametrize("workers", ["0", "62"])
def test_a_worker_count_that_no_pool_can_have_stops_before_the_run(
    world: World,
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    workers: str,
) -> None:
    _open_gates(monkeypatch, world.lock)
    error = _stop(world, record, tmp_path / "out", capsys, "--workers", workers)
    assert "--workers must be from 1 to 61" in error
    assert not list(threshold_panel_study_run.MARKER_DIR.iterdir())


def test_the_distance_text_names_the_ranges_in_which_the_random_probe_decides_as_much() -> None:
    def row(low: float, below: float | None, cells: int, share: float | None) -> dict[str, Any]:
        return {"from": low, "below": below, "cells": cells, "stage1_share": share}

    arm = {
        "questions": 1055,
        "by_distance": {
            "public_panel": [row(0.0, 0.1, 2, 0.5), row(0.1, 0.2, 0, None), row(0.2, None, 2, 1.0)],
            "random": [row(0.0, 0.1, 2, 0.4), row(0.1, 0.2, 0, None), row(0.2, None, 2, 1.0)],
        },
    }
    expected = "- 1,055 questions, against the public-panel strata: 0.20 or more."
    assert random_distance_text(arm) == expected


@pytest.mark.parametrize(
    ("new", "text"),
    [
        (0.40, "the same to 0.1 percentage points"),
        (0.3999, "the same to 0.1 percentage points"),
        (0.42, "2.0 percentage points higher"),
        (0.39, "1.0 percentage points lower"),
    ],
)
def test_the_panel_text_gives_the_change_of_the_decided_share(new: float, text: str) -> None:
    def scope(share: float) -> dict[str, Any]:
        part = {"stage1_share": share, "wrong": 1, "decisions": 9, "mean_question_fraction": 0.5}
        return {"primary_threshold": part, "all_thresholds": part}

    arm = {"probes": {"three_model": scope(0.40), "public_panel": scope(new)}}
    assert panel_text({"primary_threshold": "0.70"}, arm).count(text) == 2
