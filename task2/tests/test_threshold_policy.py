"""Policy file contract and the frozen-hash gate for real-grade replays."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import AA_LCR as AA_LCR_NAME
from benchmark_reference.threshold_benchmarks import LIVE_CODE_BENCH
from benchmark_reference.threshold_policy import (
    alpha_spending,
    authorize_real_replay,
    committed_lock_text,
    load_policy,
)

POLICY_DIR = Path(__file__).parents[1] / "policies"
DRAFT = POLICY_DIR / "threshold-draft.json"
LCB, AA_LCR = LIVE_CODE_BENCH, AA_LCR_NAME
_FILE_KEYS = {"schema_version", "policy_id", "version", "frozen", "benchmarks"}


def _policy(section: str = LCB, /, **changes: object) -> dict[str, Any]:
    """The draft policy; file-level keys change the file, others the benchmark section."""
    value: dict[str, Any] = json.loads(DRAFT.read_text(encoding="utf-8"))
    for key, setting in changes.items():
        (value if key in _FILE_KEYS else value["benchmarks"][section])[key] = setting
    return value


def _write(path: Path, value: object) -> Path:
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def _lock(policies: dict[str, str]) -> str:
    return json.dumps({"schema_version": 1, "policies": policies})


def test_committed_draft_policy_holds_every_required_setting() -> None:
    loaded = load_policy(DRAFT)
    policy = loaded.benchmarks[LCB]
    assert loaded.key == "threshold-policy@draft-1"
    assert (policy.benchmark, policy.policy_id, policy.version) == (
        LCB,
        "threshold-policy",
        "draft-1",
    )
    assert loaded.sha256 == hashlib.sha256(DRAFT.read_bytes()).hexdigest()
    assert policy.frozen is False
    assert policy.threshold == 0.70
    assert policy.alpha == 0.05
    assert policy.stage1_size == 63
    assert policy.interval_method == "pooled_exact_hypergeometric"
    assert policy.stratifier == "difficulty_stratified"
    assert policy.seeds == tuple(range(20))
    assert policy.simulation_seed == 56
    assert policy.coverage_subsets == 2000
    assert policy.coverage_stage_sizes == (32, 63, 95, 158, 221)
    assert policy.cost_stage_sizes == (32, 63, 95, 158, 221)
    assert policy.cost_bands == ((0.3, 0.5), (0.55, 0.65), (0.7, 0.75), (0.8, 0.9))


def test_committed_draft_policy_has_its_own_section_for_aa_lcr() -> None:
    loaded = load_policy(DRAFT)
    # LiveCodeBench comes first in every report, whatever the key order of the file.
    assert tuple(loaded.benchmarks) == (LCB, AA_LCR)
    policy = loaded.benchmarks[AA_LCR]
    assert policy.benchmark == AA_LCR
    assert policy.frozen is False
    assert policy.threshold == 0.60
    assert policy.alpha == 0.05
    assert policy.stage1_size == 20
    assert policy.interval_method == "pooled_exact_hypergeometric"
    assert policy.stratifier == "length_difficulty_stratified"
    assert policy.coverage_stage_sizes == (12, 20, 30, 50, 70)
    assert policy.cost_stage_sizes == (12, 20, 30, 50, 70)
    assert policy.cost_bands == ((0.3, 0.4), (0.45, 0.55), (0.6, 0.65), (0.7, 0.9))


def test_a_policy_file_can_hold_one_benchmark(tmp_path: Path) -> None:
    value = _policy()
    del value["benchmarks"][LCB]
    loaded = load_policy(_write(tmp_path / "policy.json", value))
    assert tuple(loaded.benchmarks) == (AA_LCR,)


@pytest.mark.parametrize(
    ("benchmark", "stratifier"),
    [
        (LCB, "metadata_stratified"),
        (LCB, "length_difficulty_stratified"),
        (AA_LCR, "difficulty_stratified"),
        (AA_LCR, "response_stratified"),
    ],
)
def test_a_stratifier_of_another_benchmark_stops_loading(
    tmp_path: Path, benchmark: str, stratifier: str
) -> None:
    value = _policy(benchmark, stratifier=stratifier)
    with pytest.raises(AnalysisError, match=f"section {benchmark}: Policy stratifier"):
        load_policy(_write(tmp_path / "policy.json", value))


@pytest.mark.parametrize(
    ("benchmarks", "message"),
    [
        ({}, "at least one benchmark"),
        ({"mmmu": {}}, "Unknown policy benchmark"),
        ([], "at least one benchmark"),
    ],
)
def test_invalid_benchmark_sections_stop_loading(
    tmp_path: Path, benchmarks: object, message: str
) -> None:
    with pytest.raises(AnalysisError, match=message):
        load_policy(_write(tmp_path / "policy.json", _policy(benchmarks=benchmarks)))


def test_cost_bands_group_every_true_score_into_exactly_one_band(tmp_path: Path) -> None:
    value = _policy(cost={"stage_sizes": [63], "bands": [[0.3, 0.45], [0.5, 0.9]]})
    policy = load_policy(_write(tmp_path / "policy.json", value)).benchmarks[LCB]
    assert policy.cost_bands == ((0.3, 0.45), (0.5, 0.9))
    assert policy.cost_stage_sizes == (63,)


@pytest.mark.parametrize(
    "method",
    [
        "pooled_exact_hypergeometric",
        "stratified_bonferroni_hypergeometric",
        "stratified_wilson",
        "stratified_bootstrap_percentile",
    ],
)
def test_policy_file_can_name_each_interval_method(tmp_path: Path, method: str) -> None:
    loaded = load_policy(_write(tmp_path / "policy.json", _policy(interval_method=method)))
    assert loaded.benchmarks[LCB].interval_method == method


def test_spent_alpha_is_at_most_005_for_the_committed_policy() -> None:
    spending = alpha_spending(load_policy(DRAFT).benchmarks[LCB])
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
        ({"schema_version": 1}, "schema_version"),
        ({"schema_version": 3}, "schema_version"),
        ({"benchmark": LCB}, "keys"),
        ({"coverage": {"subsets": 0, "stage_sizes": [32]}}, "subsets"),
        ({"coverage": {"subsets": 10, "stage_sizes": []}}, "stage_sizes"),
        ({"coverage": {"subsets": 10, "stage_sizes": [63, 32]}}, "stage_sizes"),
        ({"coverage": {"subsets": 10, "stage_sizes": [0, 32]}}, "stage_sizes"),
        ({"coverage": {"subsets": 10}}, "coverage keys"),
        ({"schema_version": 2}, "schema_version"),
        ({"cost": {"stage_sizes": [63]}}, "cost keys"),
        ({"cost": {"stage_sizes": [], "bands": [[0.3, 0.9]]}}, "cost stage_sizes"),
        ({"cost": {"stage_sizes": [63, 32], "bands": [[0.3, 0.9]]}}, "cost stage_sizes"),
        ({"cost": {"stage_sizes": [63], "bands": []}}, "cost bands"),
        # A band must be a [low, high] pair with low <= high.
        ({"cost": {"stage_sizes": [63], "bands": [[0.9, 0.3]]}}, "cost bands"),
        ({"cost": {"stage_sizes": [63], "bands": [[0.3]]}}, "cost bands"),
        ({"cost": {"stage_sizes": [63], "bands": [[True, 0.9]]}}, "cost bands"),
        # Bands must be ascending and must not overlap.
        ({"cost": {"stage_sizes": [63], "bands": [[0.3, 0.6], [0.6, 0.9]]}}, "cost bands"),
        ({"cost": {"stage_sizes": [63], "bands": [[0.6, 0.9], [0.3, 0.5]]}}, "cost bands"),
        (
            {
                "cost": {
                    "stage_sizes": [63],
                    "bands": [[0.3, 0.4], [0.45, 0.5], [0.55, 0.6], [0.65, 0.7], [0.75, 0.9]],
                }
            },
            "at most 4",
        ),
        # 0.85 and 0.90 fall in no band.
        ({"cost": {"stage_sizes": [63], "bands": [[0.3, 0.8]]}}, "every true score"),
        # The band 0.91 to 0.95 holds no policy true score.
        ({"cost": {"stage_sizes": [63], "bands": [[0.3, 0.9], [0.91, 0.95]]}}, "no true score"),
    ],
)
def test_invalid_policy_values_stop_loading(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(AnalysisError, match=message):
        load_policy(_write(tmp_path / "policy.json", _policy(**changes)))


def test_missing_policy_key_stops_loading(tmp_path: Path) -> None:
    value = _policy()
    del value["benchmarks"][LCB]["alpha"]
    with pytest.raises(AnalysisError, match="keys"):
        load_policy(_write(tmp_path / "policy.json", value))


def test_unknown_file_key_stops_loading(tmp_path: Path) -> None:
    value = _policy()
    value["threshold"] = 0.7
    with pytest.raises(AnalysisError, match="file keys"):
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
    lock.write_text(_lock({"threshold-policy@draft-1": "0" * 64}), encoding="utf-8")
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
