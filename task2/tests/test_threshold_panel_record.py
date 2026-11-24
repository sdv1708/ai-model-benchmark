"""The recorded reference-panel study of policy v1: its hashes, its policy, and its one run."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference.threshold_panel_study_report import OUTPUT_NAMES

TASK2 = Path(__file__).parents[1]
DATA = TASK2.parent / "docs" / "data"
RECORD = DATA / "task2-panel-study"
V1 = TASK2 / "policies" / "threshold-v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(name: str) -> Any:
    return json.loads((RECORD / name).read_text(encoding="utf-8"))


def test_the_record_holds_every_output_with_its_recorded_hash() -> None:
    assert {p.name for p in RECORD.iterdir()} == set(OUTPUT_NAMES)
    hashes = _json("manifest.json")["output_sha256"]
    assert hashes == {n: _sha(RECORD / n) for n in OUTPUT_NAMES if n != "manifest.json"}


def test_the_record_is_the_first_run_of_frozen_v1_beside_the_recorded_replay() -> None:
    manifest = _json("manifest.json")
    assert manifest["policy"]["sha256"] == _sha(V1)
    assert (manifest["real_grades_used"], manifest["rerun_reason"]) == (True, None)
    replay = _sha(DATA / "task2-real-replay" / "manifest.json")
    assert manifest["inputs"]["replay manifest.json"] == replay
    assert _json("summary.json")["arms"]["315"]["random_probe_equals_record"] is True


@pytest.mark.parametrize("arm", ["315", "1055"])
def test_each_mark_of_the_record_agrees_with_its_value_and_the_policy_limit(arm: str) -> None:
    criteria = _json("summary.json")["arms"][arm]["criteria"]
    policy = json.loads(V1.read_text(encoding="utf-8"))["protocol"]["unseen_model_replay"]
    limits = policy["pass_criteria"]
    wrong, coverage = criteria["wrong_decision_rate"], criteria["coverage"]
    cost = criteria["mean_cost_at_primary_threshold"]
    assert wrong["passed"] == (wrong["value"] <= limits["wrong_decision_rate"]["max"])
    assert coverage["passed"] == (coverage["value"] >= limits["coverage"]["min"])
    assert cost["passed"] == (cost["value"] < limits["mean_cost_at_primary_threshold"]["below"])
