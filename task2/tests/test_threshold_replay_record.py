"""The reader of the recorded #63 replay."""

import csv
import hashlib
import json
import shutil
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from policy_fixtures import TASK2

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_policy import LoadedPolicy, load_policy
from benchmark_reference.threshold_replay import RANDOM, STRATIFIED
from benchmark_reference.threshold_replay_record import load_replay_record

RECORD = TASK2.parent / "docs" / "data" / "task2-real-replay"


@pytest.fixture(scope="module")
def v1() -> LoadedPolicy:
    return load_policy(TASK2 / "policies" / "threshold-v1.json")


def test_the_record_gives_the_published_numbers_of_63(v1: LoadedPolicy) -> None:
    record = load_replay_record(RECORD, v1)
    # The numbers come from the published report of #63.
    assert record.manifest_sha256 == (
        "ed3c5bacb4b6b62695ee3b5e87d0b3f44e1b4deb4204f4f76da831b7fdc808d0"
    )
    primary = record.rules["primary"]
    assert (primary.minimum, record.rules["secondary"].minimum) == (50, 100)
    for probe, decided, wrong in ((STRATIFIED, "0.406", 28), (RANDOM, "0.423", 84)):
        at = [c for c in primary.of(probe) if c.threshold == "0.70"]
        assert len(at) == 28
        share = Fraction(sum(c.decided for c in at), sum(c.draws for c in at))
        assert f"{float(share):.3f}" == decided
        assert sum(c.wrong for c in at) == wrong
    assert sum(c.wrong for c in primary.of(STRATIFIED)) == 601
    assert min(float(r.coverage) for r in primary.coverage) == 0.95
    assert {c.questions for c in primary.cells if c.escalated == 0} == {Fraction(63)}


def test_a_record_of_another_policy_is_refused(v1: LoadedPolicy) -> None:
    with pytest.raises(AnalysisError, match="is of policy SHA-256"):
        load_replay_record(RECORD, replace(v1, sha256="0" * 64, version="v2"))


def test_a_record_of_another_public_file_is_refused(v1: LoadedPolicy) -> None:
    assert v1.protocol is not None
    public = {**v1.protocol["public_panel"], "sha256": "0" * 64}
    with pytest.raises(AnalysisError, match="another public file"):
        load_replay_record(RECORD, replace(v1, protocol={**v1.protocol, "public_panel": public}))


def test_a_changed_table_is_refused(v1: LoadedPolicy, tmp_path: Path) -> None:
    folder = tmp_path / "record"
    shutil.copytree(RECORD, folder)
    with (folder / "coverage.csv").open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(AnalysisError, match=r"coverage\.csv differs from its hash"):
        load_replay_record(folder, v1)


def test_a_row_that_disagrees_with_its_counts_is_refused(v1: LoadedPolicy, tmp_path: Path) -> None:
    folder = tmp_path / "record"
    shutil.copytree(RECORD, folder)
    path = folder / "cells.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["wrong"] = "999"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["output_sha256"]["cells.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AnalysisError, match="invalid row"):
        load_replay_record(folder, v1)


def test_a_missing_record_names_its_file(v1: LoadedPolicy, tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match=r"manifest\.json"):
        load_replay_record(tmp_path, v1)
