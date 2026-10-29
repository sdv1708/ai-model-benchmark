"""Policy file contract and the frozen-hash gate for real-grade replays."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_policy import (
    alpha_spending,
    authorize_real_replay,
    committed_lock_text,
    load_policy,
)

POLICY_DIR = Path(__file__).parents[1] / "policies"
DRAFT = POLICY_DIR / "lcb-threshold-draft.json"


def _policy(**changes: object) -> dict[str, object]:
    value: dict[str, object] = json.loads(DRAFT.read_text(encoding="utf-8"))
    value.update(changes)
    return value


def _write(path: Path, value: object) -> Path:
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def _lock(policies: dict[str, str]) -> str:
    return json.dumps({"schema_version": 1, "policies": policies})


def test_committed_draft_policy_holds_every_required_setting() -> None:
    loaded = load_policy(DRAFT)
    policy = loaded.policy
    assert loaded.sha256 == hashlib.sha256(DRAFT.read_bytes()).hexdigest()
    assert policy.frozen is False
    assert policy.threshold == 0.70
    assert policy.alpha == 0.05
    assert policy.stage1_size == 63
    assert policy.interval_method == "pooled_exact_hypergeometric"
    assert policy.stratifier == "difficulty_stratified"
    assert policy.seeds == tuple(range(20))
    assert policy.simulation_seed == 56


def test_spent_alpha_is_at_most_005_for_the_committed_policy() -> None:
    spending = alpha_spending(load_policy(DRAFT).policy)
    # Stage 1 spends the policy alpha; the census has no sampling error.
    assert spending == (0.05, 0.0)
    assert sum(spending) <= 0.05


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"alpha": 0}, "alpha"),
        ({"alpha": 1.5}, "alpha"),
        ({"threshold": 1.2}, "threshold"),
        ({"stage1_size": 0}, "stage1_size"),
        ({"stage1_size": True}, "stage1_size"),
        ({"interval_method": "wald"}, "interval_method"),
        ({"stratifier": "easiest_only"}, "stratifier"),
        ({"seeds": [0, 0]}, "seeds"),
        ({"seeds": []}, "seeds"),
        ({"frozen": "yes"}, "frozen"),
        ({"extra": 1}, "keys"),
    ],
)
def test_invalid_policy_values_stop_loading(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(AnalysisError, match=message):
        load_policy(_write(tmp_path / "policy.json", _policy(**changes)))


def test_missing_policy_key_stops_loading(tmp_path: Path) -> None:
    value = _policy()
    del value["alpha"]
    with pytest.raises(AnalysisError, match="keys"):
        load_policy(_write(tmp_path / "policy.json", value))


def test_real_replay_refuses_a_policy_that_is_not_frozen(tmp_path: Path) -> None:
    loaded = load_policy(_write(tmp_path / "policy.json", _policy(frozen=False)))
    with pytest.raises(AnalysisError, match="not marked frozen"):
        authorize_real_replay(loaded, lock_text=_lock({loaded.key: loaded.sha256}))


def test_real_replay_refuses_a_frozen_policy_without_a_committed_hash(tmp_path: Path) -> None:
    loaded = load_policy(_write(tmp_path / "policy.json", _policy(frozen=True)))
    with pytest.raises(AnalysisError, match="no committed hash"):
        authorize_real_replay(loaded, lock_text=_lock({}))


def test_hash_mismatch_stops_a_real_replay(tmp_path: Path) -> None:
    path = _write(tmp_path / "policy.json", _policy(frozen=True))
    loaded = load_policy(path)
    lock = _lock({loaded.key: loaded.sha256})
    authorize_real_replay(loaded, lock_text=lock)
    # One changed setting after the freeze changes the bytes and the hash.
    edited = load_policy(_write(path, _policy(frozen=True, threshold=0.65)))
    with pytest.raises(AnalysisError, match="hash mismatch"):
        authorize_real_replay(edited, lock_text=lock)


def test_gate_reads_the_committed_lock_not_an_uncommitted_edit(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    lock = tmp_path / "frozen-policies.json"
    lock.write_text(_lock({}), encoding="utf-8")
    git("init", "-q")
    git("add", lock.name)
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "lock")
    # An edit that is not committed must not authorize anything.
    lock.write_text(_lock({"lcb-threshold@draft-1": "0" * 64}), encoding="utf-8")
    assert json.loads(committed_lock_text(lock)) == {"schema_version": 1, "policies": {}}


def test_gate_refuses_when_the_lock_has_no_committed_copy(tmp_path: Path) -> None:
    lock = _write(tmp_path / "frozen-policies.json", {"schema_version": 1, "policies": {}})
    with pytest.raises(AnalysisError, match="committed"):
        committed_lock_text(lock)


def test_committed_lock_file_records_no_frozen_policy_yet() -> None:
    lock = json.loads((POLICY_DIR / "frozen-policies.json").read_text(encoding="utf-8"))
    assert lock == {"schema_version": 1, "policies": {}}
    with pytest.raises(AnalysisError, match="not marked frozen"):
        authorize_real_replay(load_policy(DRAFT))
