"""CLI tests: help, an end-to-end run on a synthetic inventory, and failure paths."""

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
