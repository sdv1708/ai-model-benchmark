"""A frozen policy must hold every replay value, every pass criterion, and its selection record."""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from policy_fixtures import DRAFT, draft_value, frozen_value, write_policy

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH
from benchmark_reference.threshold_policy import SCHEMA_VERSION, load_policy

LCB = LIVE_CODE_BENCH


def _load(tmp_path: Path, value: object) -> Any:
    return load_policy(write_policy(tmp_path / "policy.json", value))


def _paths(value: object, prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    """Every key path of nested objects. Lists are leaves."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield (*prefix, key)
            yield from _paths(item, (*prefix, key))


def _delete(value: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    edited = copy.deepcopy(value)
    node = edited
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return edited


def _set(value: dict[str, Any], path: str, setting: object) -> dict[str, Any]:
    edited = copy.deepcopy(value)
    keys = path.split(".")
    node = edited
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    node[keys[-1]] = setting
    return edited


def test_the_draft_uses_schema_6_and_holds_no_frozen_block() -> None:
    assert SCHEMA_VERSION == 6
    assert json.loads(DRAFT.read_text(encoding="utf-8"))["schema_version"] == 6
    loaded = load_policy(DRAFT)
    assert (loaded.frozen, loaded.protocol, loaded.selection) == (False, None, None)


def test_a_frozen_policy_with_both_blocks_loads(tmp_path: Path) -> None:
    loaded = _load(tmp_path, frozen_value())
    assert loaded.frozen is True
    assert loaded.key == "threshold-policy@v1"
    assert loaded.protocol["grade_rule"]["primary_min_pass_at_1"] == 50
    assert loaded.selection["source"]["policy"] == "threshold-policy@draft-1"


@pytest.mark.parametrize("block", ["protocol", "selection"])
def test_a_frozen_policy_without_a_block_stops_loading(tmp_path: Path, block: str) -> None:
    value = frozen_value()
    del value[block]
    with pytest.raises(AnalysisError, match=f"frozen policy must hold the blocks \\['{block}'\\]"):
        _load(tmp_path, value)


def test_a_draft_copy_marked_frozen_stops_loading(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="frozen policy must hold"):
        _load(tmp_path, {**draft_value(), "frozen": True})


def test_a_draft_can_hold_a_protocol_and_it_is_checked(tmp_path: Path) -> None:
    value = {**frozen_value(), "frozen": False}
    assert _load(tmp_path, value).protocol is not None
    value["protocol"]["decision"]["stages"] = 3
    with pytest.raises(AnalysisError, match=r"protocol\.decision\.stages"):
        _load(tmp_path, value)


PROTOCOL_PATHS = list(_paths(frozen_value()["protocol"]))
SELECTION_PATHS = [
    p for p in _paths(frozen_value()["selection"]) if p[-1] != "benchmarks" or len(p) == 1
]


@pytest.mark.parametrize("path", PROTOCOL_PATHS, ids=".".join)
def test_every_protocol_value_is_required(tmp_path: Path, path: tuple[str, ...]) -> None:
    with pytest.raises(AnalysisError):
        _load(tmp_path, _delete(frozen_value(), ("protocol", *path)))


@pytest.mark.parametrize("path", SELECTION_PATHS, ids=".".join)
def test_every_selection_value_is_required(tmp_path: Path, path: tuple[str, ...]) -> None:
    with pytest.raises(AnalysisError):
        _load(tmp_path, _delete(frozen_value(), ("selection", *path)))


def test_the_protocol_holds_every_value_of_the_issue() -> None:
    """The fixed values of #62, written by the freeze builder with no tuning."""
    protocol = frozen_value()["protocol"]
    assert protocol["decision"] == {
        "stages": 2,
        "indifference_zone": {"primary": 0, "secondary": 0.02},
    }
    panel = protocol["public_panel"]
    assert panel["sha256"] == "17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1"
    assert (panel["models"], panel["questions"], panel["mapped_questions"]) == (28, 1055, 315)
    rule = protocol["grade_rule"]
    assert (rule["field"], rule["primary_min_pass_at_1"], rule["secondary_min_pass_at_1"]) == (
        "pass@1",
        50,
        100,
    )
    assert rule["full_set_uses_same_rule"] is True
    replay = protocol["unseen_model_replay"]
    assert replay["benchmark"] == LCB
    assert replay["strata"] == "committed_reference_panel"
    assert (replay["targets"], replay["questions"]) == (28, 315)
    assert replay["thresholds"] == {"start": 0.3, "stop": 0.9, "step": 0.01}
    assert replay["selection_seeds"] == {"first": 0, "last": 999}
    assert replay["coverage_subsets"] == 2000
    assert replay["baseline"] == {
        "selector": "uniform_random",
        "interval_method": "pooled_exact_hypergeometric",
        "same_stage1_size": True,
    }
    criteria = replay["pass_criteria"]
    assert criteria["wrong_decision_rate"]["max"] == 0.071
    assert criteria["coverage"]["min"] == 0.935
    assert criteria["mean_cost_at_primary_threshold"]["below"] == 1.0
    assert set(replay["stated_comparisons"]) == {
        "stage1_share_vs_random_probe",
        "real_vs_simulated_d95",
    }
    # The simulated d95 of the chosen LiveCodeBench setting, copied from the run.
    assert replay["stated_comparisons"]["real_vs_simulated_d95"]["simulated"] == {
        "d95": 0.19,
        "d95_below": 0.19,
        "d95_above": 0.17,
        "rasch": 0.18,
        "reference_flip": 0.19,
    }
    study = protocol["reference_panel_study"]
    assert (study["strata"], study["group_sizes"]) == ("reference_pass_rate", "near_equal")
    assert (study["groups"], study["secondary_groups"]) == (4, 8)
    # 63 of 315 is 0.2; 0.2 of 1,055 questions is 211.
    assert (study["full_panel_questions"], study["full_panel_stage1_size"]) == (1055, 211)
    sizes = {group: len(names) for group, names in study["developer_groups"].items()}
    assert sizes == {
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
    pruned = protocol["pruned_set_test"]
    assert (pruned["sizes"], pruned["reported_sizes"]) == ([95, 158], [63])
    assert (pruned["strata"], pruned["score"]) == ("committed_reference_panel", "weighted")
    assert (pruned["published_seed"], pruned["selection_seeds"]) == (42, {"first": 0, "last": 999})
    # The coverage criterion uses the interval method of the LiveCodeBench section.
    assert pruned["interval_method"] == frozen_value()["benchmarks"][LCB]["interval_method"]
    assert pruned["coverage_subsets"] == 2000
    limits = {
        name: {k: v for k, v in item.items() if k != "statement"}
        for name, item in pruned["pass_criteria"].items()
    }
    assert limits == {
        "published_mean_abs_error": {"max": 0.03},
        "published_max_abs_error": {"max": 0.08},
        "seed_mean_abs_error": {"max": 0.03},
        "seed_abs_error_share": {"error_max": 0.08, "min_share": 0.95},
        "coverage": {"min": 0.935},
        "ordering": {"min_gap": 0.10, "min_share": 0.95},
    }
    disclosures = protocol["disclosures"]
    assert "scratch replay on the 3 reference models" in disclosures["reference_replay_seen"]
    assert "reduces the bias" in disclosures["reference_replay_seen"]
    assert "does not remove it" in disclosures["reference_replay_seen"]
    for fact in (
        "file shape",
        "model names",
        "count of each pass@1 value",
        "question dates, difficulty labels, and platforms",
        "release_date field",
        "Nobody computed a score or a decision of a public model",
    ):
        assert fact in disclosures["public_panel_read"]
    change = disclosures["ordering_criterion_change"]
    assert "after the author saw the 3-model results" in change
    assert "gap of 0.10 or more" in change
    assert "before anyone read a public grade" in change


def test_the_full_panel_stage_size_follows_the_livecodebench_fraction(tmp_path: Path) -> None:
    base = draft_value()
    base["benchmarks"][LCB]["stage1_size"] = 64
    base["benchmarks"][LCB]["error_rate"]["stage_sizes"] = [32, 63, 64, 95, 158, 221]
    value = frozen_value(base)
    # 64 / 315 of 1,055 questions is 214.35, rounded up.
    assert value["protocol"]["reference_panel_study"]["full_panel_stage1_size"] == 215
    _load(tmp_path, value)
    edited = _set(value, "protocol.reference_panel_study.full_panel_stage1_size", 214)
    with pytest.raises(AnalysisError, match="must be 215"):
        _load(tmp_path, edited)


@pytest.mark.parametrize(
    ("section", "key", "setting"),
    [
        (LCB, "interval_method", "stratified_wilson"),
        (LCB, "stratifier", "response_stratified"),
        (AA_LCR, "stage1_size", 30),
        (AA_LCR, "stratifier", "metadata_stratified"),
    ],
)
def test_a_hand_edit_of_a_chosen_value_stops_loading(
    tmp_path: Path, section: str, key: str, setting: object
) -> None:
    value = frozen_value()
    value["benchmarks"][section][key] = setting
    # The LiveCodeBench interval method also sets the pruned-set interval, so that check can
    # stop the edit first.
    with pytest.raises(AnalysisError, match=r"but the section holds|interval method of its"):
        _load(tmp_path, value)


def test_a_recorded_choice_that_the_rules_do_not_give_stops_loading(tmp_path: Path) -> None:
    value = frozen_value()
    candidates = value["selection"]["benchmarks"][LCB]["probe"]["candidates"]
    # Another candidate becomes the cheapest, so the rules no longer give the recorded probe.
    candidates[0]["mean_cost_fraction"] = {"rasch": 0.01, "reference_flip": 0.01}
    with pytest.raises(AnalysisError, match="but its candidates give"):
        _load(tmp_path, value)


def test_the_selection_must_state_the_rules_of_the_package(tmp_path: Path) -> None:
    value = _set(frozen_value(), "selection.rules.probe", "Choose the cheapest probe.")
    with pytest.raises(AnalysisError, match=r"selection\.rules"):
        _load(tmp_path, value)


def test_the_selection_must_cover_every_section(tmp_path: Path) -> None:
    value = frozen_value()
    del value["selection"]["benchmarks"][AA_LCR]
    with pytest.raises(AnalysisError, match=r"selection\.benchmarks keys"):
        _load(tmp_path, value)


def test_a_candidate_stratifier_of_another_benchmark_stops_loading(tmp_path: Path) -> None:
    path = f"selection.benchmarks.{LCB}.probe.candidates.0.stratifier"
    with pytest.raises(AnalysisError, match="stratifier must be one of"):
        _load(tmp_path, _set(frozen_value(), path, "metadata_stratified"))


@pytest.mark.parametrize(
    ("path", "setting", "message"),
    [
        ("protocol.decision.stages", 3, "stages must be one of"),
        ("protocol.decision.stages", True, "stages must be one of"),
        ("protocol.decision.indifference_zone.secondary", -0.01, "secondary must be"),
        ("protocol.decision.indifference_zone.primary", 0.03, "secondary must be at least"),
        ("protocol.public_panel.sha256", "17F9" + "0" * 60, "SHA-256"),
        ("protocol.public_panel.sha256", "abc", "SHA-256"),
        ("protocol.grade_rule.secondary_min_pass_at_1", 40, "at least as strict"),
        ("protocol.grade_rule.primary_min_pass_at_1", 101, "primary_min_pass_at_1"),
        ("protocol.grade_rule.full_set_uses_same_rule", False, "full_set_uses_same_rule"),
        ("protocol.grade_rule.statement", " ", "statement must be nonempty"),
        ("protocol.unseen_model_replay.benchmark", AA_LCR, "benchmark must be one of"),
        ("protocol.unseen_model_replay.targets", 27, "targets must equal"),
        ("protocol.unseen_model_replay.questions", 300, "questions must equal"),
        ("protocol.unseen_model_replay.selection_seeds.first", 1000, "first must not exceed"),
        ("protocol.unseen_model_replay.coverage_subsets", 0, "coverage_subsets"),
        ("protocol.unseen_model_replay.baseline.selector", "easiest_only", "selector"),
        ("protocol.unseen_model_replay.baseline.interval_method", "wald", "interval_method"),
        (
            "protocol.unseen_model_replay.thresholds",
            {"start": 0.3, "stop": 0.6, "step": 0.01},
            "must hold the primary threshold 0.7",
        ),
        (
            "protocol.unseen_model_replay.pass_criteria.wrong_decision_rate.max",
            1.5,
            "max must be a number",
        ),
        (
            "protocol.unseen_model_replay.pass_criteria.mean_cost_at_primary_threshold.below",
            0,
            "below must be a number in \\(0",
        ),
        (
            "protocol.unseen_model_replay.stated_comparisons.real_vs_simulated_d95.simulated.d95",
            "0.19",
            "d95 must be a number",
        ),
        ("protocol.reference_panel_study.secondary_groups", 4, "must differ from groups"),
        ("protocol.reference_panel_study.full_panel_questions", 1000, "public questions"),
        ("protocol.pruned_set_test.sizes", [158, 95], "unique, ascending"),
        ("protocol.pruned_set_test.reported_sizes", [95], "must not repeat"),
        ("protocol.pruned_set_test.sizes", [95, 400], "must not exceed"),
        ("protocol.pruned_set_test.score", "raw_mean", "score must be one of"),
        ("protocol.disclosures.public_panel_read", "", "public_panel_read must be nonempty"),
    ],
)
def test_invalid_protocol_values_stop_loading(
    tmp_path: Path, path: str, setting: object, message: str
) -> None:
    with pytest.raises(AnalysisError, match=message):
        _load(tmp_path, _set(frozen_value(), path, setting))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda g: g["Anthropic"].pop(), "must name the 28 public models; it names 27"),
        (lambda g: g["xAI"].append("Claude-3-Haiku"), "more than once"),
        (lambda g: g["OpenAI"].reverse(), "sorted order"),
        (lambda g: g.update({"Empty": []}), "nonempty list"),
    ],
)
def test_the_developer_groups_name_each_public_model_once(
    tmp_path: Path, change: Any, message: str
) -> None:
    value = frozen_value()
    change(value["protocol"]["reference_panel_study"]["developer_groups"])
    with pytest.raises(AnalysisError, match=message):
        _load(tmp_path, value)


def test_a_frozen_file_needs_the_section_of_the_replay_benchmark(tmp_path: Path) -> None:
    value = frozen_value()
    del value["benchmarks"][LCB]
    del value["selection"]["benchmarks"][LCB]
    with pytest.raises(AnalysisError, match="needs the section of its benchmark"):
        _load(tmp_path, value)


def test_a_float_does_not_pass_for_an_integer_choice(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="stages must be one of"):
        _load(tmp_path, _set(frozen_value(), "protocol.decision.stages", 2.0))


@pytest.mark.parametrize("block", ["interval_method", "probe"])
def test_the_selection_must_hold_every_candidate(tmp_path: Path, block: str) -> None:
    value = frozen_value()
    candidates = value["selection"]["benchmarks"][LCB][block]["candidates"]
    # Drop a candidate that the rules do not choose, so only completeness can fail.
    candidates.pop(-1)
    with pytest.raises(AnalysisError, match="once"):
        _load(tmp_path, value)


def test_a_repeated_probe_candidate_stops_loading(tmp_path: Path) -> None:
    value = frozen_value()
    candidates = value["selection"]["benchmarks"][LCB]["probe"]["candidates"]
    candidates[-1] = copy.deepcopy(candidates[-2])
    with pytest.raises(AnalysisError, match="each stratifier at each error-rate stage size once"):
        _load(tmp_path, value)


def test_the_pruned_set_interval_is_the_livecodebench_interval(tmp_path: Path) -> None:
    value = _set(frozen_value(), "protocol.pruned_set_test.interval_method", "stratified_wilson")
    with pytest.raises(AnalysisError, match="interval method of its benchmark section"):
        _load(tmp_path, value)
