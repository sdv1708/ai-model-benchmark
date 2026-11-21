"""The lcb-public command: fetch, check, and map. No command prints a grade."""

import hashlib
import json
from pathlib import Path

import pytest

from benchmark_reference import public_lcb
from benchmark_reference.public_lcb import PublicShape, PublicSource
from benchmark_reference.public_lcb_cli import main

CONTENT = {"abc301_a": "Print A.", "1873_A": "Sort B.", "3324": "Count C."}
PLATFORM = {"abc301_a": "atcoder", "1873_A": "codeforces", "3324": "leetcode"}


def _public_file(tmp_path: Path) -> tuple[Path, str]:
    rows = [
        {
            "question_id": question,
            "model": model,
            "date": 1682899200000,
            "difficulty": "easy",
            "pass@1": 37.5,
            "platform": PLATFORM[question],
        }
        for model in ("Model-A", "Model-B")
        for question in CONTENT
    ]
    models = [
        {
            "model_name": model.lower(),
            "model_repr": model,
            "model_style": "Synthetic",
            "release_date": 1719705600000,
            "link": "https://example.invalid",
        }
        for model in ("Model-A", "Model-B")
    ]
    value = {"performances": rows, "models": models, "date_marks": [1682899200000]}
    data = json.dumps(value).encode("utf-8")
    path = tmp_path / "external" / "performances_generation.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _panel(tmp_path: Path, texts: list[str]) -> Path:
    tasks = [
        {"index": index, "question_sha256": public_lcb.question_fingerprint(text), "scores": {}}
        for index, text in enumerate(texts)
    ]
    path = tmp_path / "panel.json"
    path.write_text(json.dumps({"schema_version": 1, "tasks": tasks}), encoding="utf-8")
    return path


@pytest.fixture
def synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the command at a synthetic 2-model, 3-question file and dataset."""
    path, digest = _public_file(tmp_path)
    monkeypatch.setattr(public_lcb, "PINNED_SOURCE", PublicSource("https://x.invalid", digest, 1))
    monkeypatch.setattr(public_lcb, "RECORDED_SHAPE", PublicShape(models=2, questions=3))
    monkeypatch.setattr(public_lcb, "REFERENCE_QUESTIONS", 3)
    rows = [
        {"question_id": q, "platform": PLATFORM[q], "question_content": text}
        for q, text in CONTENT.items()
    ]
    monkeypatch.setattr(public_lcb, "read_dataset_rows", lambda: rows)
    return path


def test_fetch_stops_on_a_hash_mismatch_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(public_lcb, "download_url", lambda url, limit: b"{}")
    output = tmp_path / "external" / "file.json"
    with pytest.raises(SystemExit) as stopped:
        main(["fetch", "--output", str(output)])
    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert "differs from the pinned SHA-256" in error
    assert public_lcb.PINNED_SOURCE.sha256 in error
    assert not output.exists()


def test_fetch_saves_a_file_whose_hash_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = b'{"performances": []}'
    digest = hashlib.sha256(data).hexdigest()
    source = PublicSource("https://x.invalid/file.json", digest, len(data))
    monkeypatch.setattr(public_lcb, "PINNED_SOURCE", source)
    monkeypatch.setattr(public_lcb, "download_url", lambda url, limit: data)
    output = tmp_path / "file.json"
    main(["fetch", "--output", str(output)])
    assert output.read_bytes() == data
    assert f"SHA-256 {digest} matches the pin" in capsys.readouterr().out


def test_check_prints_the_shape_and_no_grade(
    synthetic: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["check", "--source", str(synthetic)])
    out = capsys.readouterr().out
    assert "2 models, 3 questions, 6 cells, no missing cell" in out
    assert "37.5" not in out


def test_map_writes_the_mapping_and_prints_counts_only(
    synthetic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    panel = _panel(tmp_path, ["Count C.", "Print A.", "Sort B."])
    output = tmp_path / "mapping.json"
    main(["map", "--source", str(synthetic), "--panel", str(panel), "--output", str(output)])
    document = json.loads(output.read_text(encoding="utf-8"))
    assert [(e["index"], e["question_id"]) for e in document["questions"]] == [
        (0, "3324"),
        (1, "abc301_a"),
        (2, "1873_A"),
    ]
    assert document["panel_sha256"] == hashlib.sha256(panel.read_bytes()).hexdigest()
    out = capsys.readouterr().out
    assert "Mapped 3 of 3 reference questions uniquely" in out
    assert "37.5" not in out


def test_map_stops_and_names_each_question_without_a_match(
    synthetic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    panel = _panel(tmp_path, ["Count C.", "Lost.", "Sort B."])
    output = tmp_path / "mapping.json"
    with pytest.raises(SystemExit) as stopped:
        main(["map", "--source", str(synthetic), "--panel", str(panel), "--output", str(output)])
    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert "1 of 3 reference questions have no match" in error
    assert f"index 1 (fingerprint {public_lcb.question_fingerprint('Lost.')})" in error
    assert not output.exists()


def test_check_rejects_a_file_with_another_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = _public_file(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        main(["check", "--source", str(path)])
    assert stopped.value.code == 2
    assert "not the pinned" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["panel", "source"])
def test_map_refuses_an_output_that_would_overwrite_an_input(
    synthetic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], target: str
) -> None:
    panel = _panel(tmp_path, ["Count C.", "Print A.", "Sort B."])
    before = panel.read_bytes(), synthetic.read_bytes()
    output = panel if target == "panel" else synthetic
    with pytest.raises(SystemExit) as stopped:
        main(["map", "--source", str(synthetic), "--panel", str(panel), "--output", str(output)])
    assert stopped.value.code == 2
    assert "would overwrite" in capsys.readouterr().err
    assert (panel.read_bytes(), synthetic.read_bytes()) == before
