"""Load the inputs of the reference-panel study, check each one, and run the study.

The frozen-policy check runs first, before the command reads a public grade. The
study then needs the record of the real replay (#63) of the same policy file. It
therefore runs only with the exact policy bytes of that replay.

The study runs one time, under the same rules as the real replay: a clean
``task2`` folder, a start marker, and no earlier record in git HEAD.
"""

from pathlib import Path

from benchmark_reference.public_lcb import load_public_grades
from benchmark_reference.threshold_benchmarks import BENCHMARKS, load_reference_panel
from benchmark_reference.threshold_panel_study import (
    Arm,
    full_panel_policy,
    full_panel_targets,
    run_random,
    run_variant,
    study_variants,
    unit_costs,
)
from benchmark_reference.threshold_panel_study_report import ArmResult, PanelStudyRun
from benchmark_reference.threshold_policy import LoadedPolicy, authorize_real_replay
from benchmark_reference.threshold_replay import public_targets, replay_settings
from benchmark_reference.threshold_replay_record import load_replay_record
from benchmark_reference.threshold_replay_report import Provenance
from benchmark_reference.threshold_replay_run import (
    RECORD,
    TASK2,
    check_first_run,
    check_panel,
    check_public_models,
    clean_commit,
    mark_start,
    pinned_mapping,
    recorded_replay,
    token_costs,
)

REPLAY_RECORD = RECORD.parent
# Git ignores this folder, so a marker does not change the clean-folder check.
MARKER_DIR = TASK2 / "output"
STUDY_RECORD = RECORD.parents[1] / "task2-panel-study" / "manifest.json"


def recorded_study() -> str | None:
    """The policy key of the study that git HEAD records, or None without a record."""
    return recorded_replay(STUDY_RECORD)


def _marker(loaded: LoadedPolicy) -> Path:
    return MARKER_DIR / f"panel-study-started-{loaded.sha256[:16]}.jsonl"


def run_panel_study(
    loaded: LoadedPolicy,
    *,
    panel_dir: Path,
    data_root: Path,
    public_file: Path,
    mapping_file: Path,
    replay_record: Path,
    command: str,
    rerun_reason: str | None = None,
    workers: int = 1,
) -> PanelStudyRun:
    """Both arms of the study under one frozen policy."""
    authorize_real_replay(loaded)
    check_first_run(
        loaded,
        rerun_reason,
        name="reference-panel study",
        recorded=recorded_study,
        record=STUDY_RECORD,
        marker=_marker(loaded),
    )
    commit = clean_commit()
    clean_commit(replay_record)
    record = load_replay_record(replay_record, loaded)
    assert loaded.protocol is not None
    replay, public = loaded.protocol["unseen_model_replay"], loaded.protocol["public_panel"]
    groups = loaded.protocol["reference_panel_study"]["developer_groups"]
    settings = replay_settings(loaded)
    section = loaded.benchmarks[replay["benchmark"]]
    inputs = {loaded.file_name: loaded.sha256, "replay manifest.json": record.manifest_sha256}

    panel_path = panel_dir / BENCHMARKS[section.benchmark].panel_file
    panel = load_reference_panel(panel_path, benchmark=section.benchmark)
    inputs[panel_path.name] = panel.sha256
    check_panel(loaded, panel)
    mapping = pinned_mapping(loaded, mapping_file, panel_path, inputs)
    costs = token_costs(panel, data_root, inputs)
    # A fault up to here uses no run.
    shape = check_public_models(loaded, public_file, panel, inputs)
    mark_start(
        _marker(loaded), {"commit": commit, "command": command, "rerun_reason": rerun_reason}
    )
    grades = load_public_grades(public_file, loaded, sha256=public["sha256"], shape=shape)

    arms = (
        Arm(
            str(replay["questions"]),
            section,
            public_targets(grades, mapping),
            costs,
            token_costs=True,
        ),
        Arm(
            str(public["questions"]),
            full_panel_policy(loaded),
            full_panel_targets(grades),
            unit_costs(range(public["questions"])),
            token_costs=False,
        ),
    )
    variants = study_variants(loaded)
    rules = dict.fromkeys((v.rule, v.minimum) for v in variants)
    results = {
        arm.name: ArmResult(
            arm,
            {v: run_variant(arm, v, groups, settings, workers=workers) for v in variants},
            {rule: run_random(arm, minimum, settings) for rule, minimum in rules},
            record.rules if arm.token_costs else None,
        )
        for arm in arms
    }
    return PanelStudyRun(
        loaded=loaded,
        settings=settings,
        arms=results,
        record=record,
        provenance=Provenance(command, commit, rerun_reason, inputs),
    )
