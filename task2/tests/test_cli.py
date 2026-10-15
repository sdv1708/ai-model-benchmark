"""CLI tests: help, an end-to-end run on a synthetic inventory, and failure paths."""

import hashlib
import json
from pathlib import Path

import pytest

from benchmark_reference.cli import main
from benchmark_reference.inputs import MMMU_MODEL, MMMU_SUBJECTS

PART_A = [
    (benchmark, metric, count, model)
    for benchmark, metric, count in (("aa_lcr", "acc", 100), ("live_code_bench_v5", "pass", 315))
    for model in ("gpt-oss-120b", "kimi-k2.5", "minimax-m2.5")
]


def write_pair(root: Path, rel: str, model: str, metric: str, count: int, *, named: bool) -> None:
    """Write shuffled predictions and ordered reviews scoring 1,0,1,0... (index 0 => 1).

    ``named`` sets ``main_score_name``; MMMU reviews leave it null.
    """
    pred_path, rev_path = root / "predictions" / rel, root / "reviews" / rel
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    rev_path.parent.mkdir(parents=True, exist_ok=True)
    pred_path.write_text(
        "".join(
            json.dumps(
                {"index": i, "model": model, "metadata": {}, "model_output": {"error": None}}
            )
            + "\n"
            for i in reversed(range(count))
        ),
        encoding="utf-8",
    )
    rev_path.write_text(
        "".join(
            json.dumps(
                {
                    "index": i,
                    "sample_score": {
                        "score": {
                            "value": {metric: float((i + 1) % 2)},
                            "main_score_name": metric if named else None,
                        }
                    },
                }
            )
            + "\n"
            for i in range(count)
        ),
        encoding="utf-8",
    )


@pytest.fixture
def evals(tmp_path: Path) -> Path:
    """Synthetic Evals/ tree with the shipped layout, names and sample counts."""
    root = tmp_path / "Evals"
    for benchmark, metric, count, model in PART_A:
        write_pair(root / "Part 1", f"{benchmark}__{model}.jsonl", model, metric, count, named=True)
    for subject in MMMU_SUBJECTS:
        write_pair(
            root / "MMMU", f"{MMMU_MODEL}/mmmu_{subject}.jsonl", MMMU_MODEL, "acc", 30, named=False
        )
    return root


def test_pruning_cli_reproduces_auditable_full_budget_results(evals: Path, tmp_path: Path) -> None:
    from benchmark_reference.pruning_cli import main as pruning_main

    for directory in ("pruned1", "pruned2"):
        pruning_main(
            [
                "--data-root",
                str(evals),
                "--output-dir",
                str(tmp_path / directory),
                "--keep-ratios",
                "1",
                "--seeds",
                "7",
            ]
        )
    first, second = tmp_path / "pruned1", tmp_path / "pruned2"
    for name in (
        "scores.json",
        "selections.jsonl",
        "pair_selections.jsonl",
        "fidelity.json",
        "summary.csv",
        "pair_summary.csv",
        "decisions.csv",
        "manifest.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    report = json.loads((first / "fidelity.json").read_text(encoding="utf-8"))
    assert len(report["runs"]) == 15  # 3 held-out models x (2 candidates + 3 baselines)
    for run in report["runs"]:
        assert run["held_out_absolute_error"] == 0
        assert run["ordering"]["pair_agreement"] == 1
        assert run["ordering"]["kendall_tau_b"] is None  # all model scores tie
    selection = json.loads((first / "selections.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert len(selection["samples"]) == 315
    assert len({item["index"] for item in selection["samples"]}) == 315
    assert selection["held_out_model"] not in selection["reference_models"]
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["inputs"]) == 6
    for name, digest in manifest["output_sha256"].items():
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == digest
    for source in manifest["inputs"]:
        assert hashlib.sha256((evals / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    implementation = Path(__file__).parents[1] / "src/benchmark_reference"
    for name, digest in manifest["implementation_sha256"].items():
        canonical_source = (implementation / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical_source).hexdigest() == digest


def test_pruning_cli_reports_uncertainty_transfer_and_threshold_abstentions(
    evals: Path,
    tmp_path: Path,
) -> None:
    from benchmark_reference.pruning_cli import main as pruning_main

    output = tmp_path / "uncertainty"
    pruning_main(
        [
            "--data-root",
            str(evals),
            "--output-dir",
            str(output),
            "--keep-ratios",
            "0.5",
            "1",
            "--seeds",
            "0",
            "--confidence",
            "0.95",
            "--thresholds",
            "0.5",
            "0.6",
        ]
    )
    report = json.loads((output / "fidelity.json").read_text(encoding="utf-8"))
    partial = next(
        run
        for run in report["runs"]
        if run["strategy"] == "response_stratified" and run["keep_ratio"] == 0.5
    )
    assert partial["score_intervals"][partial["held_out_model"]]["lower"] < 0.5
    assert partial["score_intervals"][partial["held_out_model"]]["upper"] > 0.5
    assert partial["threshold_decisions"][0]["decision"] == "inconclusive"
    census = next(
        run
        for run in report["runs"]
        if run["strategy"] == "response_stratified" and run["keep_ratio"] == 1
    )
    assert [decision["decision"] for decision in census["threshold_decisions"]] == ["go", "no_go"]
    assert len(report["pair_transfer_runs"]) == 30
    for run in report["pair_transfer_runs"]:
        assert not set(run["models"]) & set(run["reference_models"])
        if run["keep_ratio"] == 1:
            assert run["estimated_difference"] == run["full_difference"] == 0
            assert run["conclusion"] == "tie"


@pytest.mark.parametrize(
    "failure",
    [
        "grades",
        "ratio",
        "duplicate_seed",
        "budget",
        "destination",
        "confidence",
        "threshold",
        "duplicate_threshold",
    ],
)
def test_pruning_failure_preserves_prior_reports(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], failure: str
) -> None:
    from benchmark_reference.pruning_cli import main as pruning_main

    output_dir = tmp_path / "pruning"
    output_dir.mkdir()
    sentinel = output_dir / "manifest.json"
    sentinel.write_text("prior successful report", encoding="utf-8")
    extra = ["--keep-ratios", "1", "--seeds", "0"]
    if failure == "grades":
        path = evals / "Part 1/reviews/live_code_bench_v5__kimi-k2.5.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif failure == "ratio":
        extra = ["--keep-ratios", "nan"]
    elif failure == "duplicate_seed":
        extra = ["--seeds", "0", "0"]
    elif failure == "budget":
        extra = ["--keep-ratios", "0.001"]
    elif failure == "destination":
        output_dir = evals
    elif failure == "confidence":
        extra = ["--confidence", "1"]
    elif failure == "threshold":
        extra = ["--thresholds", "nan"]
    elif failure == "duplicate_threshold":
        extra = ["--thresholds", "0.5", "0.5"]
    with pytest.raises(SystemExit) as exc:
        pruning_main(["--data-root", str(evals), "--output-dir", str(output_dir), *extra])
    assert exc.value.code == 2
    assert "lcb-pruning:" in capsys.readouterr().err
    assert sentinel.read_text(encoding="utf-8") == "prior successful report"


def test_help_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    """--help exits 0 and documents both required options."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "--data-root" in output
    assert "--output-dir" in output


def test_successful_run_is_complete_and_byte_identical(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A full run writes 1,905 samples, 6 summaries and 56 hashed inputs, identically twice."""
    for name in ("out1", "out2"):
        main(["--data-root", str(evals), "--output-dir", str(tmp_path / name)])
    for name in ("samples.jsonl", "full_scores.json", "manifest.json"):
        assert (tmp_path / "out1" / name).read_bytes() == (tmp_path / "out2" / name).read_bytes()

    lines = (tmp_path / "out1" / "samples.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 * (315 + 100) + 22 * 30  # 1,245 Part A + 660 MMMU
    scores = json.loads((tmp_path / "out1" / "full_scores.json").read_text(encoding="utf-8"))
    assert len(scores["summaries"]) == 6
    assert {s["subset"] for s in scores["summaries"]} == {"default"}
    lcb = next(s for s in scores["summaries"] if s["benchmark"] == "live_code_bench_v5")
    assert (lcb["sample_count"], lcb["score_sum"]) == (315, 158.0)  # even indices score 1
    manifest = json.loads((tmp_path / "out1" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["inputs"]) == 56
    assert "Part A" in capsys.readouterr().out


def test_invalid_input_exits_2_without_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty data root exits 2 with a clear message and creates no output."""
    output_dir = tmp_path / "output"
    empty_root = tmp_path / "Evals"
    empty_root.mkdir()
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(empty_root), "--output-dir", str(output_dir)])
    assert exc.value.code == 2
    assert "missing files ['MMMU', 'Part 1']" in capsys.readouterr().err
    assert not output_dir.exists()


def test_corrupt_row_exits_2_without_output(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One bad line in one file aborts the whole run before any report is written."""
    victim = evals / "Part 1" / "reviews" / "aa_lcr__kimi-k2.5.jsonl"
    victim.write_text(victim.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # blank line
    output_dir = tmp_path / "output"
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(evals), "--output-dir", str(output_dir)])
    assert exc.value.code == 2
    assert "blank line" in capsys.readouterr().err
    assert not output_dir.exists()


def test_output_inside_input_is_refused(evals: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Writing reports inside the input data is refused to protect source files."""
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(evals), "--output-dir", str(evals / "Part 1")])
    assert exc.value.code == 2
    assert "inside the input data" in capsys.readouterr().err


def test_output_write_error_is_reported(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_file = tmp_path / "file-instead-of-directory"
    output_file.write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(evals), "--output-dir", str(output_file)])
    assert exc.value.code == 2
    assert "Cannot write reports" in capsys.readouterr().err
    assert output_file.read_text(encoding="utf-8") == "keep me"
