"""Load the inputs of the real replay, check each one against the frozen policy, and run it.

The frozen-policy check runs first, before the command reads a public grade.
Each other input must match its pin in the policy: the public file, the question
mapping, the reference panel, the model names, and the question count.

The replay runs one time. The command writes a start marker before it reads the
public grades. It refuses to run when a marker of the same policy exists, or when
git HEAD already records a replay of that policy. The caller can give a reason
for a second replay, and the report then states that reason. The command also
needs a clean ``task2`` folder, so the recorded commit is the code that ran.
"""

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import (
    MappedQuestion,
    PublicShape,
    load_mapping,
    load_public_grades,
    load_public_results,
)
from benchmark_reference.threshold_benchmarks import (
    BENCHMARKS,
    ReferencePanel,
    load_reference_panel,
)
from benchmark_reference.threshold_cost import CostModel
from benchmark_reference.threshold_policy import LoadedPolicy, authorize_real_replay
from benchmark_reference.threshold_replay import (
    PRIMARY,
    SECONDARY,
    HoldOutDecision,
    build_probes,
    hold_out_references,
    public_targets,
    replay_rule,
    replay_settings,
)
from benchmark_reference.threshold_replay_report import (
    Provenance,
    ReplayRun,
)
from benchmark_reference.threshold_tokens import estimate_question_costs, load_token_counts

TASK2 = Path(__file__).resolve().parents[2]
RECORD = TASK2.parent / "docs" / "data" / "task2-real-replay" / "manifest.json"
# Git ignores this folder, so a marker does not change the clean-folder check.
MARKER_DIR = TASK2 / "output"


def _git(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", "-C", str(cwd), *arguments], capture_output=True, check=False)
    except OSError as exc:
        raise AnalysisError(f"Cannot run git in {cwd}: {exc}") from exc


def clean_commit(folder: Path = TASK2) -> str:
    """The commit of git HEAD. Stop when ``folder`` has an uncommitted change."""
    head = _git("rev-parse", "HEAD", cwd=folder)
    status = _git("status", "--porcelain", "--", ".", cwd=folder)
    if head.returncode or status.returncode:
        raise AnalysisError(f"{folder} is not in a git repository; the replay needs a commit")
    if status.stdout.strip():
        raise AnalysisError(
            f"{folder} has uncommitted changes. Commit them first, so that the recorded commit "
            "holds the files that the run used."
        )
    return head.stdout.decode("ascii").strip()


def recorded_replay(record: Path = RECORD) -> str | None:
    """The policy key of the run that git HEAD records in the manifest, or None without one."""
    folder = next(p for p in record.parents if p.is_dir())
    shown = _git("show", f"HEAD:./{record.relative_to(folder).as_posix()}", cwd=folder)
    if shown.returncode:
        return None
    try:
        return str(json.loads(shown.stdout.decode("utf-8"))["policy"]["key"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnalysisError(f"The recorded manifest {record} is invalid") from exc


def _marker(loaded: LoadedPolicy) -> Path:
    return MARKER_DIR / f"real-replay-started-{loaded.sha256[:16]}.jsonl"


def check_first_run(
    loaded: LoadedPolicy,
    rerun_reason: str | None,
    *,
    name: str,
    recorded: Callable[[], str | None],
    record: Path,
    marker: Path,
) -> None:
    """Stop a second run of one policy that has no reason. ``name`` is the kind of run."""
    if rerun_reason is not None:
        if not rerun_reason.strip():
            raise AnalysisError("--rerun-reason needs a reason")
        return
    advice = (
        f"The {name} runs one time. Use --rerun-reason only for a code fault or to reproduce "
        "the result."
    )
    if recorded() == loaded.key:
        raise AnalysisError(
            f"git HEAD already records the {name} of {loaded.key} ({record}). {advice}"
        )
    if marker.exists():
        raise AnalysisError(
            f"A {name} of {loaded.key} already started on this computer ({marker}). {advice}"
        )


def mark_start(path: Path, entry: dict[str, str | None]) -> None:
    """Add one line for this run. A crash after this point leaves the line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _pinned(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AnalysisError(f"The policy pins {name} {expected}, but the input has {actual}")


def token_costs(panel: ReferencePanel, data_root: Path, inputs: dict[str, str]) -> CostModel:
    """Token estimates from the saved answers of the reference models.

    The function adds the hash of each prediction file to ``inputs``.
    """
    tokens = load_token_counts(
        data_root,
        benchmark=panel.benchmark,
        models=tuple(sorted(panel.references)),
        questions=panel.questions,
        source_sha256=panel.source_sha256,
    )
    inputs.update(tokens.files)
    return CostModel(estimate_question_costs(tokens))


def check_panel(loaded: LoadedPolicy, panel: ReferencePanel) -> None:
    """Stop when the reference panel differs from its pins in the policy."""
    assert loaded.protocol is not None
    replay = loaded.protocol["unseen_model_replay"]
    _pinned("reference panel SHA-256", panel.sha256, replay["reference_panel_sha256"])
    _pinned("question count", len(panel.questions), replay["questions"])


def pinned_mapping(
    loaded: LoadedPolicy, mapping_file: Path, panel_path: Path, inputs: dict[str, str]
) -> tuple[MappedQuestion, ...]:
    """The question mapping. Stop when it differs from its pin in the policy.

    The function adds the hash of the mapping to ``inputs``.
    """
    assert loaded.protocol is not None
    public = loaded.protocol["public_panel"]
    try:
        sha256 = hashlib.sha256(mapping_file.read_bytes()).hexdigest()
    except OSError as exc:
        raise AnalysisError(f"Cannot read the question mapping {mapping_file}: {exc}") from exc
    _pinned("mapping SHA-256", sha256, public["mapping_sha256"])
    inputs[mapping_file.name] = sha256
    return load_mapping(mapping_file, panel_path=panel_path, expected=public["mapped_questions"])


def check_public_models(
    loaded: LoadedPolicy, public_file: Path, panel: ReferencePanel, inputs: dict[str, str]
) -> PublicShape:
    """The pinned shape of the public file. Stop when its models differ from the policy.

    The function also stops when a public model is in the reference panel. The loader
    range-checks every ``pass@1`` value, but it gives only model names and question
    metadata. The function adds the hash of the public file to ``inputs``.
    """
    assert loaded.protocol is not None
    public = loaded.protocol["public_panel"]
    shape = PublicShape(models=public["models"], questions=public["questions"])
    names = load_public_results(public_file, sha256=public["sha256"], shape=shape).models
    groups = loaded.protocol["reference_panel_study"]["developer_groups"]
    _pinned("model names", sorted(names), sorted(m for group in groups.values() for m in group))
    if set(names) & set(panel.references):
        raise AnalysisError("A public model is in the reference panel; the targets must be unseen")
    inputs[public_file.name] = public["sha256"]
    return shape


def run_real_replay(
    loaded: LoadedPolicy,
    *,
    panel_dir: Path,
    data_root: Path,
    public_file: Path,
    mapping_file: Path,
    command: str,
    rerun_reason: str | None = None,
) -> ReplayRun:
    """The whole replay under one frozen policy."""
    authorize_real_replay(loaded)
    check_first_run(
        loaded,
        rerun_reason,
        name="replay",
        recorded=recorded_replay,
        record=RECORD,
        marker=_marker(loaded),
    )
    commit = clean_commit()
    assert loaded.protocol is not None
    replay, public = loaded.protocol["unseen_model_replay"], loaded.protocol["public_panel"]
    settings = replay_settings(loaded)
    inputs = {loaded.file_name: loaded.sha256}

    panels = {
        name: load_reference_panel(panel_dir / BENCHMARKS[name].panel_file, benchmark=name)
        for name in loaded.benchmarks
    }
    for name, panel in panels.items():
        inputs[BENCHMARKS[name].panel_file] = panel.sha256
    section = loaded.benchmarks[replay["benchmark"]]
    panel = panels[section.benchmark]
    check_panel(loaded, panel)
    mapping = pinned_mapping(
        loaded, mapping_file, panel_dir / BENCHMARKS[section.benchmark].panel_file, inputs
    )
    costs = {name: token_costs(panels[name], data_root, inputs) for name in panels}
    probes = build_probes(panel, section, settings, costs[section.benchmark])

    hold_out: list[HoldOutDecision] = []
    for name, reference_panel in panels.items():
        hold_out.extend(hold_out_references(reference_panel, loaded.benchmarks[name], costs[name]))

    shape = check_public_models(loaded, public_file, panel, inputs)
    # A fault up to here uses no run.
    mark_start(
        _marker(loaded), {"commit": commit, "command": command, "rerun_reason": rerun_reason}
    )
    grades = load_public_grades(public_file, loaded, sha256=public["sha256"], shape=shape)
    raw = public_targets(grades, mapping)
    rule = loaded.protocol["grade_rule"]
    rules = {
        name: replay_rule(
            name,
            rule[f"{name}_min_pass_at_1"],
            raw,
            panel,
            section,
            settings,
            probes,
            costs[section.benchmark],
        )
        for name in (PRIMARY, SECONDARY)
    }
    return ReplayRun(
        loaded=loaded,
        settings=settings,
        costs=costs[section.benchmark],
        rules=rules,
        raw=raw,
        hold_out=tuple(hold_out),
        hold_out_costs=costs,
        provenance=Provenance(command, commit, rerun_reason, inputs),
    )
