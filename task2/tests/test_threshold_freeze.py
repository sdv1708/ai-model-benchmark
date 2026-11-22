"""The freeze command applies the fixed rules to a simulated run and writes a new frozen policy."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from policy_fixtures import draft_value, simulated_document, write_policy

from benchmark_reference import reporting, threshold_freeze
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import PINNED_SOURCE
from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH
from benchmark_reference.threshold_freeze import (
    DEVELOPER_GROUPS,
    check_developer_groups,
    freeze,
    main,
    read_simulated_run,
)
from benchmark_reference.threshold_policy import authorize_real_replay, load_policy

TASK2 = Path(__file__).parents[1]
PANEL = TASK2 / "data" / "lcb-reference-panel.json"
MAPPING = TASK2 / "data" / "lcb-public-mapping.json"
LCB = LIVE_CODE_BENCH


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _setup(tmp_path: Path) -> dict[str, Path]:
    """A draft, a lock, and a simulated run of the draft whose rules choose new values."""
    draft = write_policy(tmp_path / "draft.json", draft_value())
    loaded = load_policy(draft)
    sections = draft_value()["benchmarks"]
    chosen = {
        LCB: {**sections[LCB], "interval_method": "stratified_wilson"},
        AA_LCR: {
            **sections[AA_LCR],
            "stratifier": "metadata_stratified",
            "stage1_size": 30,
        },
    }
    documents = []
    for name in (LCB, AA_LCR):
        document = simulated_document(name, chosen[name])
        document["reference_panel_sha256"] = _sha(PANEL.read_bytes())
        documents.append(document)
    summary = encode_json(
        {
            "analysis_version": "threshold-two-stage-v5",
            "mode": "simulated",
            "policy": {"key": loaded.key, "sha256": loaded.sha256, "frozen": False},
            "benchmarks": documents,
        }
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "summary.json").write_bytes(summary)
    manifest = {
        "command": "threshold-decision",
        "mode": "simulated",
        "real_grades_used": False,
        "policy": {"file": "draft.json", "key": loaded.key, "sha256": loaded.sha256},
        "output_sha256": {"summary.json": _sha(summary)},
    }
    (run / "manifest.json").write_bytes(encode_json(manifest))
    lock = tmp_path / "frozen-policies.json"
    lock.write_bytes(encode_json({"schema_version": 1, "policies": {}}))
    return {"draft": draft, "run": run, "lock": lock, "output": tmp_path / "v1.json"}


def _freeze(paths: dict[str, Path], version: str = "v1") -> threshold_freeze.Frozen:
    return freeze(
        draft_path=paths["draft"],
        run_dir=paths["run"],
        output=paths["output"],
        version=version,
        lock_path=paths["lock"],
        mapping_path=MAPPING,
        reference_panel_path=PANEL,
    )


def test_freeze_writes_a_frozen_policy_with_the_values_that_the_rules_choose(
    tmp_path: Path,
) -> None:
    paths = _setup(tmp_path)
    frozen = _freeze(paths)
    loaded = load_policy(paths["output"])
    assert (loaded.key, loaded.frozen, loaded.version) == ("threshold-policy@v1", True, "v1")
    assert frozen.sha256 == _sha(paths["output"].read_bytes()) == loaded.sha256
    lcb, aa_lcr = loaded.benchmarks[LCB], loaded.benchmarks[AA_LCR]
    assert (lcb.interval_method, lcb.stratifier, lcb.stage1_size) == (
        "stratified_wilson",
        "difficulty_stratified",
        63,
    )
    assert (aa_lcr.interval_method, aa_lcr.stratifier, aa_lcr.stage1_size) == (
        "pooled_exact_hypergeometric",
        "metadata_stratified",
        30,
    )
    # The lock records the hash of the new file, so the replay gate accepts it.
    lock = paths["lock"].read_text(encoding="utf-8")
    assert json.loads(lock) == {"schema_version": 1, "policies": {loaded.key: loaded.sha256}}
    authorize_real_replay(loaded, lock_text=lock)


def test_freeze_changes_only_the_three_chosen_values_of_each_section(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    _freeze(paths)
    draft = draft_value()
    frozen: dict[str, Any] = json.loads(paths["output"].read_text(encoding="utf-8"))
    assert set(frozen) == {*draft, "protocol", "selection"}
    assert (frozen["schema_version"], frozen["policy_id"]) == (6, draft["policy_id"])
    chosen = {"interval_method", "stratifier", "stage1_size"}
    for name, section in draft["benchmarks"].items():
        mine = frozen["benchmarks"][name]
        assert {k: v for k, v in mine.items() if k not in chosen} == {
            k: v for k, v in section.items() if k not in chosen
        }


def test_freeze_records_the_source_run_and_the_candidates(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    _freeze(paths)
    loaded = load_policy(paths["output"])
    assert loaded.selection is not None and loaded.protocol is not None
    source = loaded.selection["source"]
    draft = load_policy(paths["draft"])
    assert source["policy"] == draft.key
    assert source["policy_sha256"] == draft.sha256
    assert source["summary_sha256"] == _sha((paths["run"] / "summary.json").read_bytes())
    assert source["manifest_sha256"] == _sha((paths["run"] / "manifest.json").read_bytes())
    lcb = loaded.selection["benchmarks"][LCB]
    assert lcb["interval_method"]["chosen"] == "stratified_wilson"
    assert len(lcb["interval_method"]["candidates"]) == 4
    # Every stratifier and error-rate stage size of the chosen method is a candidate.
    assert len(lcb["probe"]["candidates"]) == 2 * 5
    assert loaded.protocol["public_panel"]["mapping_sha256"] == _sha(MAPPING.read_bytes())
    replay = loaded.protocol["unseen_model_replay"]
    assert replay["reference_panel_sha256"] == _sha(PANEL.read_bytes())


def test_the_output_is_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, second = _setup(tmp_path / "a"), _setup(tmp_path / "b")
    _freeze(first)
    _freeze(second)
    assert first["output"].read_bytes() == second["output"].read_bytes()


def test_freeze_never_overwrites_a_policy(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    paths["output"].write_text("{}", encoding="utf-8")
    with pytest.raises(AnalysisError, match="never overwrites a policy file"):
        _freeze(paths)
    assert paths["output"].read_text(encoding="utf-8") == "{}"


def test_freeze_refuses_a_version_that_the_lock_already_holds(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    _freeze(paths)
    paths["output"] = tmp_path / "v1-again.json"
    with pytest.raises(AnalysisError, match="a change needs a new policy version"):
        _freeze(paths)
    assert not paths["output"].exists()
    # A new version is accepted, and the lock keeps the first entry.
    paths["output"] = tmp_path / "v2.json"
    _freeze(paths, version="v2")
    lock = json.loads(paths["lock"].read_text(encoding="utf-8"))
    assert set(lock["policies"]) == {"threshold-policy@v1", "threshold-policy@v2"}


def test_freeze_refuses_the_version_of_the_draft(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="version of the draft"):
        _freeze(_setup(tmp_path), version="draft-1")


def test_freeze_needs_a_run_of_the_same_draft(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    value = draft_value()
    value["benchmarks"][LCB]["threshold"] = 0.65
    write_policy(paths["draft"], value)
    with pytest.raises(AnalysisError, match="not the draft"):
        _freeze(paths)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m.update(mode="real"), "not a simulated run"),
        (lambda m: m.update(real_grades_used=True), "not a simulated run"),
        (lambda m: m.update(command="lcb-pruning"), "not the output of threshold-decision"),
        (lambda m: m["output_sha256"].update({"summary.json": "0" * 64}), "manifest hash"),
    ],
)
def test_freeze_checks_the_manifest_of_the_run(tmp_path: Path, change: Any, message: str) -> None:
    paths = _setup(tmp_path)
    manifest_path = paths["run"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    change(manifest)
    manifest_path.write_bytes(encode_json(manifest))
    with pytest.raises(AnalysisError, match=message):
        _freeze(paths)
    assert not paths["output"].exists()


def test_a_summary_edit_after_the_run_stops_the_freeze(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    summary = paths["run"] / "summary.json"
    summary.write_bytes(summary.read_bytes().replace(b"0.1", b"0.3", 1))
    with pytest.raises(AnalysisError, match="does not match its manifest hash"):
        _freeze(paths)


def test_a_failed_lock_write_leaves_no_policy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _setup(tmp_path)
    real = reporting.write_atomic

    def write(path: Path, data: bytes) -> None:
        if path == paths["lock"]:
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(threshold_freeze, "write_atomic", write)
    with pytest.raises(OSError, match="disk full"):
        _freeze(paths)
    assert not paths["output"].exists()
    assert json.loads(paths["lock"].read_text(encoding="utf-8"))["policies"] == {}


def test_a_mapping_of_another_shape_stops_the_freeze(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    mapping = tmp_path / "mapping.json"
    mapping.write_text("[]", encoding="utf-8")
    with pytest.raises(AnalysisError, match="mapping"):
        freeze(
            draft_path=paths["draft"],
            run_dir=paths["run"],
            output=paths["output"],
            version="v1",
            lock_path=paths["lock"],
            mapping_path=mapping,
            reference_panel_path=PANEL,
        )


def test_a_run_on_another_reference_panel_stops_the_freeze(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    other = tmp_path / "panel.json"
    other.write_bytes(PANEL.read_bytes() + b"\n")
    with pytest.raises(AnalysisError, match="mapping"):
        freeze(
            draft_path=paths["draft"],
            run_dir=paths["run"],
            output=paths["output"],
            version="v1",
            lock_path=paths["lock"],
            mapping_path=MAPPING,
            reference_panel_path=other,
        )


def test_read_simulated_run_gives_each_benchmark_document(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    draft = load_policy(paths["draft"])
    run = read_simulated_run(paths["run"], policy_key=draft.key, policy_sha256=draft.sha256)
    assert tuple(run.benchmarks) == (LCB, AA_LCR)
    assert run.analysis_version == "threshold-two-stage-v5"


def test_the_developer_groups_name_the_28_public_models() -> None:
    names = [name for group in DEVELOPER_GROUPS.values() for name in group]
    assert len(names) == len(set(names)) == 28
    check_developer_groups(names)
    with pytest.raises(AnalysisError, match="missing \\['New-Model'\\]"):
        check_developer_groups([*names, "New-Model"])


def test_the_protocol_pin_is_the_pin_of_the_public_loader(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    _freeze(paths)
    protocol = load_policy(paths["output"]).protocol
    assert protocol is not None
    panel = protocol["public_panel"]
    assert (panel["url"], panel["sha256"]) == (PINNED_SOURCE.url, PINNED_SOURCE.sha256)
    assert PINNED_SOURCE.sha256 == (
        "17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1"
    )


def test_the_command_prints_the_choices_and_the_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _setup(tmp_path)
    monkeypatch.setattr(threshold_freeze, "DEFAULT_MAPPING", MAPPING)
    main(
        [
            "--draft",
            str(paths["draft"]),
            "--simulated-run",
            str(paths["run"]),
            "--output",
            str(paths["output"]),
            "--version",
            "v1",
            "--lock",
            str(paths["lock"]),
        ]
    )
    out = capsys.readouterr().out
    assert f"Policy SHA-256: {_sha(paths['output'].read_bytes())}" in out
    assert "live_code_bench_v5: interval_method stratified_wilson" in out
    assert "not checked against the public model names" in out


def test_the_command_exits_2_on_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _setup(tmp_path)
    paths["output"].write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        main(
            [
                "--draft",
                str(paths["draft"]),
                "--simulated-run",
                str(paths["run"]),
                "--output",
                str(paths["output"]),
                "--version",
                "v1",
                "--lock",
                str(paths["lock"]),
            ]
        )
    assert stopped.value.code == 2
    assert "never overwrites a policy file" in capsys.readouterr().err


def test_a_summary_without_study_results_stops_the_freeze(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    summary_path = paths["run"] / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["benchmarks"][0]["coverage"]
    data = encode_json(summary)
    summary_path.write_bytes(data)
    manifest_path = paths["run"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_sha256"]["summary.json"] = _sha(data)
    manifest_path.write_bytes(encode_json(manifest))
    with pytest.raises(AnalysisError, match="lacks a study result"):
        _freeze(paths)


def test_a_manifest_of_another_shape_stops_the_freeze(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    manifest_path = paths["run"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["policy"] = "draft.json"
    manifest_path.write_bytes(encode_json(manifest))
    with pytest.raises(AnalysisError, match="not the draft"):
        _freeze(paths)
