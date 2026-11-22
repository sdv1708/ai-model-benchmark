"""The committed frozen policy v1: its lock entry, its source, and its values.

The freeze command wrote v1 from a simulated run of the draft (#62). These
tests check the committed bytes. A later change must create a new version, so
an edit of v1 or of its lock entry fails here.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import DEFAULT_SOURCE_PATH, PINNED_SOURCE, load_public_results
from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH
from benchmark_reference.threshold_policy import authorize_real_replay, load_policy

TASK2 = Path(__file__).parents[1]
POLICIES = TASK2 / "policies"
V1 = POLICIES / "threshold-v1.json"
DRAFT = POLICIES / "threshold-draft.json"
LOCK = POLICIES / "frozen-policies.json"
CHOSEN = {"interval_method", "stratifier", "stage1_size"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_is_frozen_and_its_hash_is_the_lock_entry() -> None:
    loaded = load_policy(V1)
    assert (loaded.key, loaded.frozen) == ("threshold-policy@v1", True)
    assert _json(LOCK) == {"schema_version": 1, "policies": {loaded.key: _sha(V1)}}
    authorize_real_replay(loaded, lock_text=LOCK.read_text(encoding="utf-8"))


def test_the_draft_stays_a_draft_and_is_refused_for_real_grades() -> None:
    draft = load_policy(DRAFT)
    assert (draft.key, draft.frozen) == ("threshold-policy@draft-1", False)
    with pytest.raises(AnalysisError, match="not marked frozen"):
        authorize_real_replay(draft, lock_text=LOCK.read_text(encoding="utf-8"))


def test_v1_was_chosen_from_a_run_of_the_committed_draft() -> None:
    selection = load_policy(V1).selection
    assert selection is not None
    assert selection["source"]["policy"] == "threshold-policy@draft-1"
    assert selection["source"]["policy_sha256"] == _sha(DRAFT)


def test_v1_differs_from_the_draft_only_in_the_chosen_values() -> None:
    draft, v1 = _json(DRAFT), _json(V1)
    assert set(v1) - set(draft) == {"protocol", "selection"}
    assert (v1["version"], v1["frozen"]) == ("v1", True)
    for key in ("schema_version", "policy_id"):
        assert v1[key] == draft[key]
    assert set(v1["benchmarks"]) == set(draft["benchmarks"])
    for name, section in draft["benchmarks"].items():
        mine = v1["benchmarks"][name]
        assert {k: v for k, v in mine.items() if k not in CHOSEN} == {
            k: v for k, v in section.items() if k not in CHOSEN
        }


def test_v1_holds_the_values_that_the_rules_chose() -> None:
    loaded = load_policy(V1)
    lcb, aa_lcr = loaded.benchmarks[LIVE_CODE_BENCH], loaded.benchmarks[AA_LCR]
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
    assert (lcb.threshold, aa_lcr.threshold) == (0.70, 0.60)


def test_v1_pins_the_committed_inputs_of_the_replays() -> None:
    protocol = load_policy(V1).protocol
    assert protocol is not None
    panel = protocol["public_panel"]
    assert panel["sha256"] == PINNED_SOURCE.sha256
    assert panel["mapping_sha256"] == _sha(TASK2 / "data" / "lcb-public-mapping.json")
    replay = protocol["unseen_model_replay"]
    assert replay["reference_panel_sha256"] == _sha(TASK2 / "data" / "lcb-reference-panel.json")
    # 63 of 315 questions is 0.2; 0.2 of 1,055 is 211.
    assert protocol["reference_panel_study"]["full_panel_stage1_size"] == 211


@pytest.mark.skipif(
    not DEFAULT_SOURCE_PATH.exists(), reason="the public file is not downloaded (lcb-public fetch)"
)
def test_the_developer_groups_name_each_public_model_once() -> None:
    protocol = load_policy(V1).protocol
    assert protocol is not None
    groups = protocol["reference_panel_study"]["developer_groups"]
    named = sorted(name for names in groups.values() for name in names)
    # Model names only: this reads no grade.
    assert named == sorted(load_public_results().models)


def test_the_developer_groups_have_the_sizes_of_the_issue() -> None:
    protocol = load_policy(V1).protocol
    assert protocol is not None
    groups = protocol["reference_panel_study"]["developer_groups"]
    assert {group: len(names) for group, names in groups.items()} == {
        "Anthropic": 6,
        "OpenAI": 10,
        "Google": 4,
        "DeepSeek": 2,
        "NVIDIA": 2,
        "xAI": 1,
        "LG": 1,
        "Alibaba": 1,
        "Developer of XBai-o4-medium": 1,
    }
    assert groups["Developer of XBai-o4-medium"] == ["XBai-o4-medium"]


def test_the_pruned_set_test_uses_the_livecodebench_interval() -> None:
    loaded = load_policy(V1)
    assert loaded.protocol is not None
    method = loaded.benchmarks[LIVE_CODE_BENCH].interval_method
    assert loaded.protocol["pruned_set_test"]["interval_method"] == method
