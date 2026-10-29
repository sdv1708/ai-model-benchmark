"""The threshold-decision command end to end on simulated LiveCodeBench models."""

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from benchmark_reference import threshold_policy
from benchmark_reference.threshold_cli import main

TASK2 = Path(__file__).parents[1]
DRAFT = TASK2 / "policies" / "lcb-threshold-draft.json"
PANEL = TASK2 / "data" / "lcb-reference-panel.json"
OUTPUTS = {"decisions.csv", "summary.json", "report.html", "manifest.json"}


def _small_policy(tmp_path: Path, **changes: object) -> Path:
    value = json.loads(DRAFT.read_text(encoding="utf-8"))
    value["seeds"] = [0, 1]
    value["simulation"] = {"seed": 56, "true_scores": [0.5, 0.7, 0.9], "models_per_seed": 5}
    value.update(changes)
    path = tmp_path / "policy.json"
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def _run(policy: Path, output: Path, *extra: str) -> None:
    main(["--policy", str(policy), "--panel", str(PANEL), "--output-dir", str(output), *extra])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_command_writes_decision_table_manifest_and_report(tmp_path: Path) -> None:
    policy = _small_policy(tmp_path)
    output = tmp_path / "out"
    _run(policy, output)
    assert {p.name for p in output.iterdir()} == OUTPUTS

    with (output / "decisions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    # 3 true scores x 2 seeds x 5 simulated models per seed.
    assert len(rows) == 30
    assert {"true_score", "decision", "decided_stage", "stage1_result", "wrong"} <= set(rows[0])
    assert {row["true_score"] for row in rows} == {"0.50", "0.70", "0.90"}
    for row in rows:
        assert row["stage1_result"] in {"GO", "NO GO", "ESCALATE"}
        assert row["decision"] in {"GO", "NO GO"}
        if row["stage1_result"] == "ESCALATE":
            assert (row["decided_stage"], row["questions_graded"], row["wrong"]) == (
                "2",
                "315",
                "0",
            )
        else:
            assert (row["decided_stage"], row["questions_graded"]) == ("1", "63")
            assert row["decision"] == row["stage1_result"]
        assert row["wrong"] == str(int(row["decision"] != row["truth"]))
    # 221 of 315 is the smallest full-set score at or above 0.70.
    assert {row["full_passes"] for row in rows if row["true_score"] == "0.70"} == {"221"}

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "simulated"
    assert manifest["real_grades_used"] is False
    assert manifest["policy"]["sha256"] == _sha(policy)
    assert manifest["inputs"]["reference_panel"]["sha256"] == _sha(PANEL)
    for name in OUTPUTS - {"manifest.json"}:
        assert manifest["output_sha256"][name] == _sha(output / name)
    code = TASK2 / "src" / "benchmark_reference"
    for name, digest in manifest["implementation_sha256"].items():
        source = (code / name).read_bytes().replace(b"\r\n", b"\n")
        assert digest == hashlib.sha256(source).hexdigest()
    assert {"two_stage.py", "threshold_policy.py", "uncertainty.py"} <= set(
        manifest["implementation_sha256"]
    )


def test_report_shows_decisive_fraction_and_wrong_rate_for_each_true_score(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    html = (output / "report.html").read_text(encoding="utf-8")
    assert [row["true_score"] for row in summary["true_scores"]] == ["0.50", "0.70", "0.90"]
    for row in summary["true_scores"]:
        assert row["draws"] == 10
        if row["wrong_decisions"] == 0:
            # Closed form for 0 of n: the bound p solves (1 - p) ** n = 0.05.
            assert abs(row["wrong_rate_upper95"] - (1 - 0.05 ** (1 / 10))) < 1e-6
        assert row["decisive_fraction"] == row["decided_at_stage1"] / 10
        assert row["wrong_decision_rate"] == row["wrong_decisions"] / 10
        cells = re.search(rf'<tr data-true-score="{row["true_score"]}">(.*?)</tr>', html, re.S)
        assert cells is not None
        assert f"{row['decisive_fraction']:.3f}" in cells.group(1)
        assert f"{row['wrong_decision_rate']:.3f}" in cells.group(1)


def test_report_is_self_contained_and_supports_light_and_dark(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    assert not re.search(r"<(script|link|img|iframe|object)\b", html, re.I)
    assert not re.search(r"\b(src|href)\s*=", html, re.I)
    assert "@import" not in html and "url(" not in html
    assert "prefers-color-scheme: dark" in html
    assert "color-scheme: light dark" in html
    assert "<svg" in html and 'role="img"' in html


def test_two_runs_with_the_same_policy_give_identical_manifest_hashes(tmp_path: Path) -> None:
    policy = _small_policy(tmp_path)
    _run(policy, tmp_path / "first")
    _run(policy, tmp_path / "second")
    first = (tmp_path / "first" / "manifest.json").read_bytes()
    second = (tmp_path / "second" / "manifest.json").read_bytes()
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_real_grade_replay_is_refused_for_the_draft_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out"
    with pytest.raises(SystemExit) as stopped:
        _run(DRAFT, output, "--real-grades")
    assert stopped.value.code == 2
    assert "not marked frozen" in capsys.readouterr().err
    assert not output.exists()


def test_hash_mismatch_stops_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = _small_policy(tmp_path, frozen=True)
    lock = json.dumps({"schema_version": 1, "policies": {"lcb-threshold@draft-1": "0" * 64}})
    monkeypatch.setattr(threshold_policy, "committed_lock_text", lambda: lock)
    output = tmp_path / "out"
    with pytest.raises(SystemExit) as stopped:
        _run(policy, output, "--real-grades")
    assert stopped.value.code == 2
    assert "hash mismatch" in capsys.readouterr().err
    assert not output.exists()


def test_panel_for_another_benchmark_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        _run(_small_policy(tmp_path, benchmark="aa_lcr"), tmp_path / "out")
    assert stopped.value.code == 2
    assert "benchmark" in capsys.readouterr().err


def test_wrong_rate_chart_marks_the_one_tail_bound_alpha_over_two(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "one-tail bound 0.025" in html
    assert "policy alpha 0.05" not in html


def test_draft_warning_appears_only_for_a_draft_policy(tmp_path: Path) -> None:
    draft, frozen = tmp_path / "draft", tmp_path / "frozen"
    _run(_small_policy(tmp_path), draft)
    _run(_small_policy(tmp_path, frozen=True), frozen)
    warning = "The policy is a draft"
    assert warning in (draft / "report.html").read_text(encoding="utf-8")
    assert warning not in (frozen / "report.html").read_text(encoding="utf-8")
    assert warning not in (frozen / "summary.json").read_text(encoding="utf-8")
