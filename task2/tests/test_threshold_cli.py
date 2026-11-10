"""The threshold-decision command end to end on simulated LiveCodeBench and AA-LCR models."""

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference import threshold_policy
from benchmark_reference.threshold_benchmarks import AA_LCR as AA_LCR_NAME
from benchmark_reference.threshold_benchmarks import LIVE_CODE_BENCH
from benchmark_reference.threshold_cli import main

TASK2 = Path(__file__).parents[1]
DRAFT = TASK2 / "policies" / "threshold-draft.json"
PANELS = TASK2 / "data"
LCB, AA_LCR = LIVE_CODE_BENCH, AA_LCR_NAME
# The four tables of the earlier studies keep their names, columns, and rows.
EARLIER_FILES = {"decisions.csv", "coverage.csv", "cost.csv", "question_tokens.csv"}
BENCHMARK_FILES = EARLIER_FILES | {
    "error_rate.csv",
    "error_rate_settings.csv",
    "error_rate_combined.csv",
}
OUTPUTS = {"summary.json", "report.html", "manifest.json", LCB, AA_LCR}
METHODS = (
    "pooled_exact_hypergeometric",
    "stratified_bonferroni_hypergeometric",
    "stratified_wilson",
    "stratified_bootstrap_percentile",
)
JUDGE_NOISE = 'class="judge-noise"'


def _small_policy(tmp_path: Path, **changes: object) -> Path:
    value: dict[str, Any] = json.loads(DRAFT.read_text(encoding="utf-8"))
    lcb, aa_lcr = value["benchmarks"][LCB], value["benchmarks"][AA_LCR]
    lcb["seeds"] = aa_lcr["seeds"] = [0, 1]
    lcb["simulation"] = {"seed": 56, "true_scores": [0.5, 0.7, 0.9], "models_per_seed": 5}
    lcb["coverage"] = {"subsets": 20, "stage_sizes": [32, 63]}
    lcb["cost"] = {"stage_sizes": [32, 63], "bands": [[0.5, 0.5], [0.7, 0.9]]}
    lcb["error_rate"] = {
        "draws": 20,
        "stage_sizes": [32, 63],
        "true_scores": {"start": 0.5, "stop": 0.9, "step": 0.1},
    }
    aa_lcr["simulation"] = {"seed": 56, "true_scores": [0.4, 0.6, 0.8], "models_per_seed": 5}
    aa_lcr["coverage"] = {"subsets": 20, "stage_sizes": [12, 20]}
    aa_lcr["cost"] = {"stage_sizes": [12, 20], "bands": [[0.4, 0.4], [0.6, 0.8]]}
    aa_lcr["error_rate"] = {
        "draws": 20,
        "stage_sizes": [12, 20],
        "true_scores": {"start": 0.4, "stop": 0.8, "step": 0.1},
    }
    value.update(changes)
    path = tmp_path / "policy.json"
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def _run(policy: Path, output: Path, *extra: str, panels: Path = PANELS) -> None:
    main(["--policy", str(policy), "--panel-dir", str(panels), "--output-dir", str(output), *extra])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _section(html: str, benchmark: str) -> str:
    found = re.search(rf'<section data-benchmark="{benchmark}"[^>]*>(.*?)</section>', html, re.S)
    assert found is not None, benchmark
    return found.group(1)


def test_command_writes_decision_table_manifest_and_report(tmp_path: Path) -> None:
    policy = _small_policy(tmp_path)
    output = tmp_path / "out"
    _run(policy, output)
    assert {p.name for p in output.iterdir()} == OUTPUTS
    for benchmark in (LCB, AA_LCR):
        assert {p.name for p in (output / benchmark).iterdir()} == BENCHMARK_FILES

    rows = _rows(output / LCB / "decisions.csv")
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
    for benchmark, panel in ((LCB, "lcb"), (AA_LCR, "aa-lcr")):
        inputs = manifest["inputs"]["benchmarks"][benchmark]
        assert inputs["reference_panel"]["sha256"] == _sha(PANELS / f"{panel}-reference-panel.json")
        for name in BENCHMARK_FILES:
            path = f"{benchmark}/{name}"
            assert manifest["output_sha256"][path] == _sha(output / benchmark / name)
    for name in ("summary.json", "report.html"):
        assert manifest["output_sha256"][name] == _sha(output / name)
    code = TASK2 / "src" / "benchmark_reference"
    for name, digest in manifest["implementation_sha256"].items():
        source = (code / name).read_bytes().replace(b"\r\n", b"\n")
        assert digest == hashlib.sha256(source).hexdigest()
    assert {
        "two_stage.py",
        "threshold_policy.py",
        "threshold_benchmarks.py",
        "long_context.py",
        "uncertainty.py",
        "threshold_intervals.py",
        "threshold_coverage.py",
    } <= set(manifest["implementation_sha256"])


def test_aa_lcr_runs_on_its_own_questions_policy_and_probe(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    rows = _rows(output / AA_LCR / "decisions.csv")
    assert len(rows) == 30
    for row in rows:
        graded = "100" if row["stage1_result"] == "ESCALATE" else "20"
        assert (row["stage1_size"], row["questions_graded"]) == ("20", graded)
    # 60 of 100 is exactly the threshold 0.60.
    assert {(r["full_passes"], r["truth"]) for r in rows if r["true_score"] == "0.60"} == {
        ("60", "GO")
    }
    coverage = _rows(output / AA_LCR / "coverage.csv")
    assert {row["stratifier"] for row in coverage} == {
        "metadata_stratified",
        "length_difficulty_stratified",
    }
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert [b["benchmark"] for b in summary["benchmarks"]] == [LCB, AA_LCR]
    aa_lcr = summary["benchmarks"][1]
    assert (aa_lcr["threshold"], aa_lcr["stage1_size"], aa_lcr["population"]) == (0.6, 20, 100)
    assert aa_lcr["stratifier"] == "length_difficulty_stratified"
    assert "not measured" in aa_lcr["judge_noise"]
    assert summary["benchmarks"][0]["judge_noise"] is None
    full = aa_lcr["cost"]["full_run"]
    # Input tokens dominate the AA-LCR cost, and they depend on the document: across
    # the three reference models, the input count of one question differs by at most 3%.
    assert full["input_tokens_mean"] / full["tokens"]["mean"] > 0.95
    assert full["input_tokens_max_model_ratio"] == pytest.approx(1.029757, abs=1e-6)


def test_report_shows_both_benchmarks_in_matching_sections_with_the_same_charts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    lcb, aa_lcr = _section(html, LCB), _section(html, AA_LCR)
    assert html.index(f'data-benchmark="{LCB}"') < html.index(f'data-benchmark="{AA_LCR}"')

    def charts(section: str) -> list[str]:
        return re.findall(r'<svg[^>]*data-chart="([^"]+)"', section)

    def headings(section: str) -> list[str]:
        return re.findall(r"<h([34])>", section)

    assert (
        charts(lcb)
        == charts(aa_lcr)
        == ["decisive", "wrong", "cost", *["coverage"] * 4, *["error"] * 4, *["distance"] * 2]
    )
    assert headings(lcb) == headings(aa_lcr)
    # Element ids must stay unique when both sections are on one page.
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    for document in summary["benchmarks"]:
        benchmark, overall = document["benchmark"], document["overall"]

        def overview(name: str, key: str = benchmark) -> str:
            cell = re.search(rf'<td data-overview="{key}-{name}">([^<]+)</td>', html)
            assert cell is not None, (key, name)
            return cell.group(1)

        assert overview("threshold") == f"{document['threshold']:.2f}"
        decided = overall["decided_at_stage1"] / overall["draws"]
        assert overview("decided") == f"{decided:.3f}"
        costs = [r["expected_cost_fraction"]["mean"] for r in document["true_scores"]]
        assert overview("mean-cost") == f"{sum(costs) / len(costs):.3f}"


def test_judge_noise_limit_appears_next_to_every_aa_lcr_result(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    section = _section(html, AA_LCR)
    # A result is a chart or a table. Each one has the note under the same heading.
    blocks = [b for b in re.split(r"<h[34]>", section) if "<svg" in b or "<table" in b]
    assert len(blocks) >= 7
    for block in blocks:
        assert JUDGE_NOISE in block
        assert "not measured" in block
    assert JUDGE_NOISE not in _section(html, LCB)
    overview = re.search(r'<td data-overview="aa_lcr-judge-noise">([^<]+)</td>', html)
    assert overview is not None and "not measured" in overview.group(1)
    # The AA-LCR column of the side-by-side table points to the judge-noise note under it.
    assert "<th>AA-LCR *</th>" in html and "<th>LiveCodeBench</th>" in html
    note = re.search(r'<p class="judge-noise" data-overview-note>([^<]+)</p>', html)
    assert note is not None and note.group(1).startswith("* AA-LCR: Judge noise is not measured")


def test_report_shows_decisive_fraction_and_wrong_rate_for_each_true_score(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    html = (output / "report.html").read_text(encoding="utf-8")
    for document in summary["benchmarks"]:
        section = _section(html, document["benchmark"])
        for row in document["true_scores"]:
            assert row["draws"] == 10
            if row["wrong_decisions"] == 0:
                # Closed form for 0 of n: the bound p solves (1 - p) ** n = 0.05.
                assert abs(row["wrong_rate_upper95"] - (1 - 0.05 ** (1 / 10))) < 1e-6
            assert row["decisive_fraction"] == row["decided_at_stage1"] / 10
            assert row["wrong_decision_rate"] == row["wrong_decisions"] / 10
            pattern = rf'<tr data-true-score="{row["true_score"]}">(.*?)</tr>'
            cells = re.search(pattern, section, re.S)
            assert cells is not None
            assert f"{row['decisive_fraction']:.3f}" in cells.group(1)
            assert f"{row['wrong_decision_rate']:.3f}" in cells.group(1)


def test_a_policy_with_one_benchmark_reports_only_that_benchmark(tmp_path: Path) -> None:
    value = json.loads(_small_policy(tmp_path).read_text(encoding="utf-8"))
    del value["benchmarks"][LCB]
    policy = tmp_path / "aa-only.json"
    policy.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "out"
    _run(policy, output)
    assert {p.name for p in output.iterdir()} == OUTPUTS - {LCB}
    html = (output / "report.html").read_text(encoding="utf-8")
    assert 'data-benchmark="aa_lcr"' in html
    assert f'data-benchmark="{LCB}"' not in html


def test_report_is_self_contained_and_supports_light_and_dark(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    assert not re.search(r"<(script|link|img|iframe|object)\b", html, re.I)
    assert not re.search(r"\b(src|href)\s*=\s*\"(?!#)", html, re.I)
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
    lock = json.dumps({"schema_version": 1, "policies": {"threshold-policy@draft-1": "0" * 64}})
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
    panels = tmp_path / "panels"
    panels.mkdir()
    shutil.copy(PANELS / "aa-lcr-reference-panel.json", panels / "aa-lcr-reference-panel.json")
    # The LiveCodeBench file name holds the AA-LCR panel.
    shutil.copy(PANELS / "aa-lcr-reference-panel.json", panels / "lcb-reference-panel.json")
    with pytest.raises(SystemExit) as stopped:
        _run(_small_policy(tmp_path), tmp_path / "out", panels=panels)
    assert stopped.value.code == 2
    assert "not for policy benchmark" in capsys.readouterr().err


def test_wrong_rate_chart_marks_the_one_tail_bound_alpha_over_two(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    html = (output / "report.html").read_text(encoding="utf-8")
    for benchmark in (LCB, AA_LCR):
        assert "one-tail bound 0.025" in _section(html, benchmark)
    assert "policy alpha 0.05" not in html


def test_draft_warning_appears_only_for_a_draft_policy(tmp_path: Path) -> None:
    draft, frozen = tmp_path / "draft", tmp_path / "frozen"
    _run(_small_policy(tmp_path), draft)
    _run(_small_policy(tmp_path, frozen=True), frozen)
    warning = "The policy is a draft"
    assert warning in (draft / "report.html").read_text(encoding="utf-8")
    assert warning not in (frozen / "report.html").read_text(encoding="utf-8")
    assert warning not in (frozen / "summary.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("benchmark", "stratifiers", "sizes"),
    [
        (LCB, {"difficulty_stratified", "response_stratified"}, {"32", "63"}),
        (AA_LCR, {"metadata_stratified", "length_difficulty_stratified"}, {"12", "20"}),
    ],
)
def test_coverage_table_has_every_cell_and_method(
    tmp_path: Path, benchmark: str, stratifiers: set[str], sizes: set[str]
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output, "--workers", "1")
    rows = _rows(output / benchmark / "coverage.csv")
    # 2 stratifiers x 2 stage sizes x 3 true scores x 4 methods.
    assert len(rows) == 48
    assert {row["method"] for row in rows} == set(METHODS)
    assert {row["stratifier"] for row in rows} == stratifiers
    assert {row["stage_size"] for row in rows} == sizes
    for row in rows:
        assert row["subsets"] == "20"
        misses = int(row["truth_below_interval"]) + int(row["truth_above_interval"])
        assert int(row["covered"]) + misses == 20
        assert row["passes"] == str(int(int(row["covered"]) / 20 >= 0.804))


def test_report_has_a_coverage_chart_for_each_setting_and_a_width_table(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    html = (output / "report.html").read_text(encoding="utf-8")
    expected = {
        LCB: [
            f"{s}-{n}" for s in ("difficulty_stratified", "response_stratified") for n in (32, 63)
        ],
        AA_LCR: [
            f"{s}-{n}"
            for s in ("metadata_stratified", "length_difficulty_stratified")
            for n in (12, 20)
        ],
    }
    for document in summary["benchmarks"]:
        section = _section(html, document["benchmark"])
        coverage = document["coverage"]
        # 0.95 - 3 * sqrt(0.95 * 0.05 / 20) = 0.80379.
        assert coverage["pass_line"] == 0.804
        assert coverage["subsets_per_cell"] == 20
        charts = re.findall(r'<svg[^>]*data-coverage="([^"]+)"(.*?)</svg>', section, re.S)
        assert [name for name, _ in charts] == expected[document["benchmark"]]
        for _, chart in charts:
            lines = re.findall(r'<polyline class="method-(\d) series"', chart)
            assert lines == ["1", "2", "3", "4"]
            assert "pass line 0.804" in chart
            assert "<title" in chart and "<desc" in chart
        for group in coverage["groups"]:
            key = f"{group['stratifier']}-{group['stage_size']}-{group['method']}"
            cell = re.search(rf'<td data-width="{key}">([^<]+)</td>', section)
            assert cell is not None
            assert cell.group(1) == f"{group['mean_width']:.3f}"
            verdict = re.search(rf'<td data-coverage-pass="{key}"[^>]*>([^<]+)</td>', section)
            assert verdict is not None
            assert verdict.group(1).startswith("pass" if group["passes"] else "fail")
        assert [m["method"] for m in coverage["methods"]] == list(METHODS)


def test_worker_count_does_not_change_the_outputs(tmp_path: Path) -> None:
    policy = _small_policy(tmp_path)
    _run(policy, tmp_path / "one", "--workers", "1")
    _run(policy, tmp_path / "two", "--workers", "2")
    for name in ("summary.json", "report.html", "manifest.json"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    for benchmark in (LCB, AA_LCR):
        for name in BENCHMARK_FILES:
            one = (tmp_path / "one" / benchmark / name).read_bytes()
            assert one == (tmp_path / "two" / benchmark / name).read_bytes()


# Each benchmark: its stratifiers, its error-rate stage sizes, and its count of true scores.
ERROR_SETTINGS = {
    LCB: (("difficulty_stratified", "response_stratified"), (32, 63), 5),
    AA_LCR: (("metadata_stratified", "length_difficulty_stratified"), (12, 20), 5),
}


@pytest.mark.parametrize("benchmark", [LCB, AA_LCR])
def test_error_rate_tables_hold_every_generator_setting_true_score_and_method(
    tmp_path: Path, benchmark: str
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    stratifiers, sizes, scores = ERROR_SETTINGS[benchmark]
    rows = _rows(output / benchmark / "error_rate.csv")
    # 2 generators x 2 stratifiers x 2 stage sizes x 5 true scores x 4 methods.
    assert len(rows) == 2 * 2 * 2 * scores * 4
    assert {r["generator"] for r in rows} == {"rasch", "reference_flip"}
    assert {r["stratifier"] for r in rows} == set(stratifiers)
    assert {r["stage_size"] for r in rows} == {str(n) for n in sizes}
    assert {r["method"] for r in rows} == set(METHODS)
    for row in rows:
        assert row["draws"] == "20"
        counts = int(row["stage1_go"]) + int(row["stage1_no_go"]) + int(row["escalated"])
        assert counts == 20
        wrong = row["stage1_no_go"] if row["truth"] == "GO" else row["stage1_go"]
        assert row["wrong"] == wrong
        # 0.05 + 3 * sqrt(0.05 * 0.95 / 20) = 0.1962, stated as 0.196.
        assert row["passes"] == str(int(int(row["wrong"]) / 20 <= 0.196))
        assert row["expected_cost_fraction_mean"] != ""
    settings = _rows(output / benchmark / "error_rate_settings.csv")
    assert len(settings) == 2 * 2 * 2 * 4
    for setting in settings:
        mine = [
            r
            for r in rows
            if all(r[k] == setting[k] for k in ("generator", "stratifier", "stage_size", "method"))
        ]
        assert setting["passes"] == str(int(all(r["passes"] == "1" for r in mine)))
        assert setting["max_wrong_rate"] == f"{max(int(r['wrong']) for r in mine) / 20:.6f}"
    combined = _rows(output / benchmark / "error_rate_combined.csv")
    assert len(combined) == 2 * 2 * 4
    for row in combined:
        mine = [
            s
            for s in settings
            if all(s[k] == row[k] for k in ("stratifier", "stage_size", "method"))
        ]
        assert {s["generator"] for s in mine} == {"rasch", "reference_flip"}
        assert row["passes_both_generators"] == str(int(all(s["passes"] == "1" for s in mine)))
        by_generator = {s["generator"]: s["d95"] for s in mine}
        assert (row["d95_rasch"], row["d95_reference_flip"]) == (
            by_generator["rasch"],
            by_generator["reference_flip"],
        )


def test_summary_and_report_give_the_d95_sentence_for_each_benchmark(tmp_path: Path) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    html = (output / "report.html").read_text(encoding="utf-8")
    for document in summary["benchmarks"]:
        error = document["error_rate"]
        assert error["pass_line"] == 0.196
        assert error["draws_per_cell"] == 20
        assert error["generators"] == ["rasch", "reference_flip"]
        assert "cells" not in error
        claim = error["claim"]
        assert claim["stage_size"] == document["stage1_size"]
        assert claim["stratifier"] == document["stratifier"]
        assert claim["method"] == document["interval_method"]
        assert f"{document['stage1_size']}-question probe" in claim["sentence"]
        section = _section(html, document["benchmark"])
        found = re.search(r'<p class="claim" data-d95-claim>(.*?)</p>', section, re.S)
        assert found is not None
        assert claim["sentence"] in " ".join(found.group(1).split())


def test_report_has_an_error_rate_chart_for_each_method_and_a_distance_chart(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    _run(_small_policy(tmp_path), output)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    html = (output / "report.html").read_text(encoding="utf-8")
    for document in summary["benchmarks"]:
        stratifiers, sizes, _ = ERROR_SETTINGS[document["benchmark"]]
        section = _section(html, document["benchmark"])
        errors = re.findall(r'<svg[^>]*data-error="([^"]+)"(.*?)</svg>', section, re.S)
        assert [name for name, _ in errors] == list(METHODS)
        for _, chart in errors:
            # One line for each generator, a line at alpha 0.05, and the pass line.
            assert re.findall(r'<polyline class="method-(\d) series"', chart) == ["1", "2"]
            assert "alpha 0.05" in chart and "pass line 0.196" in chart
        distances = re.findall(r'<svg[^>]*data-distance="([^"]+)"(.*?)</svg>', section, re.S)
        assert [name for name, _ in distances] == list(stratifiers)
        for _, chart in distances:
            assert "stage-1 size" in chart and "d95" in chart
        for setting in document["error_rate"]["combined"]:
            key = f"{setting['stratifier']}-{setting['stage_size']}-{setting['method']}"
            verdict = re.search(rf'<td data-error-pass="{key}"[^>]*>([^<]+)</td>', section)
            assert verdict is not None
            word = "pass" if setting["passes_both_generators"] else "fail"
            assert verdict.group(1).startswith(word)
            d95 = re.search(rf'<td data-d95="{key}"[^>]*>([^<]+)', section)
            assert d95 is not None
            expected = "not reached" if setting["d95"] is None else f"{setting['d95'] * 100:.0f}"
            assert d95.group(1) == expected
        sizes_seen = {setting["stage_size"] for setting in document["error_rate"]["combined"]}
        assert sizes_seen == set(sizes)
