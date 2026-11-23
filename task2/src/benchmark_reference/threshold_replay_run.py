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
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import (
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
    HoldOutDecision,
    build_probes,
    hold_out_references,
    public_targets,
    replay_rule,
    replay_settings,
)
from benchmark_reference.threshold_replay_report import (
    PRIMARY,
    SECONDARY,
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
            "is the code that ran."
        )
    return head.stdout.decode("ascii").strip()


def recorded_replay(record: Path = RECORD) -> str | None:
    """The policy key of the replay that git HEAD records, or None without a record."""
    folder = next(p for p in record.parents if p.is_dir())
    shown = _git("show", f"HEAD:./{record.relative_to(folder).as_posix()}", cwd=folder)
    if shown.returncode:
        return None
    try:
        return str(json.loads(shown.stdout.decode("utf-8"))["policy"]["key"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnalysisError(f"The recorded replay manifest {record} is invalid") from exc


def _marker(loaded: LoadedPolicy) -> Path:
    return MARKER_DIR / f"real-replay-started-{loaded.sha256[:16]}.jsonl"


def _check_first_run(loaded: LoadedPolicy, rerun_reason: str | None) -> None:
    """Stop a second replay of one policy that has no reason."""
    if rerun_reason is not None:
        if not rerun_reason.strip():
            raise AnalysisError("--rerun-reason needs a reason")
        return
    advice = (
        "The replay runs one time. Use --rerun-reason only for a code fault or to reproduce "
        "the result."
    )
    if recorded_replay() == loaded.key:
        raise AnalysisError(
            f"git HEAD already records the replay of {loaded.key} ({RECORD}). {advice}"
        )
    if _marker(loaded).exists():
        raise AnalysisError(
            f"A replay of {loaded.key} already started on this computer "
            f"({_marker(loaded)}). {advice}"
        )


def _mark_start(loaded: LoadedPolicy, entry: dict[str, str | None]) -> None:
    """Add one line for this run. A crash after this point leaves the line."""
    path = _marker(loaded)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _pinned(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AnalysisError(f"The policy pins {name} {expected}, but the input has {actual}")


def _costs(panel: ReferencePanel, data_root: Path, inputs: dict[str, str]) -> CostModel:
    """Token estimates from the saved answers of the reference models."""
    tokens = load_token_counts(
        data_root,
        benchmark=panel.benchmark,
        models=tuple(sorted(panel.references)),
        questions=panel.questions,
        source_sha256=panel.source_sha256,
    )
    inputs.update(tokens.files)
    return CostModel(estimate_question_costs(tokens))


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
    _check_first_run(loaded, rerun_reason)
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
    _pinned("reference panel SHA-256", panel.sha256, replay["reference_panel_sha256"])
    _pinned("question count", len(panel.questions), replay["questions"])
    try:
        mapping_sha256 = hashlib.sha256(mapping_file.read_bytes()).hexdigest()
    except OSError as exc:
        raise AnalysisError(f"Cannot read the question mapping {mapping_file}: {exc}") from exc
    _pinned("mapping SHA-256", mapping_sha256, public["mapping_sha256"])
    inputs[mapping_file.name] = mapping_sha256
    mapping = load_mapping(
        mapping_file,
        panel_path=panel_dir / BENCHMARKS[section.benchmark].panel_file,
        expected=public["mapped_questions"],
    )
    costs = {name: _costs(panels[name], data_root, inputs) for name in panels}
    probes = build_probes(panel, section, settings, costs[section.benchmark])

    hold_out: list[HoldOutDecision] = []
    for name, reference_panel in panels.items():
        hold_out.extend(hold_out_references(reference_panel, loaded.benchmarks[name], costs[name]))

    shape = PublicShape(models=public["models"], questions=public["questions"])
    # Model names and question metadata only. A fault up to here uses no run.
    names = load_public_results(public_file, sha256=public["sha256"], shape=shape).models
    groups = loaded.protocol["reference_panel_study"]["developer_groups"]
    _pinned("model names", sorted(names), sorted(m for group in groups.values() for m in group))
    if set(names) & set(panel.references):
        raise AnalysisError("A public model is in the reference panel; the targets must be unseen")
    inputs[public_file.name] = public["sha256"]
    _mark_start(loaded, {"commit": commit, "command": command, "rerun_reason": rerun_reason})
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
