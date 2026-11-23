"""Freeze a threshold policy: apply the fixed rules to a simulated run and write a new version.

The command reads one simulated ``threshold-decision`` run of the draft
policy. It checks that the run belongs to the draft and that its summary is
intact. It then applies the rules of ``threshold_rules`` to each benchmark,
copies the draft, sets the three chosen values of each section, and adds the
fixed replay protocol and the selection record. Nobody edits a chosen value by
hand.

The new file is frozen. The command never overwrites a policy file or a lock
entry, so a later change must create a new version, for example ``v2``.

The command reads no public grade. With ``--public-file`` it reads the model
names of the public panel, to check the developer groups, and nothing else.
"""

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import PINNED_SOURCE, RECORDED_SHAPE, load_public_results
from benchmark_reference.reporting import write_atomic
from benchmark_reference.threshold_benchmarks import LIVE_CODE_BENCH
from benchmark_reference.threshold_intervals import POOLED_EXACT
from benchmark_reference.threshold_policy import FROZEN_LOCK, SCHEMA_VERSION, load_policy
from benchmark_reference.threshold_rules import (
    INTERVAL_RULE,
    PROBE_RULE,
    REQUIRED_GENERATORS,
    Choice,
    choose_values,
)

TASK2 = Path(__file__).resolve().parents[2]
DEFAULT_DRAFT = TASK2 / "policies" / "threshold-draft.json"
DEFAULT_MAPPING = TASK2 / "data" / "lcb-public-mapping.json"
DEFAULT_REFERENCE_PANEL = TASK2 / "data" / "lcb-reference-panel.json"

# The pin and the shape of the public file come from #75.
PUBLIC_MODELS = RECORDED_SHAPE.models
PUBLIC_QUESTIONS = RECORDED_SHAPE.questions
MAPPED_QUESTIONS = 315

# The developer group of each public model (#77). The names are the public model names.
DEVELOPER_GROUPS: Mapping[str, tuple[str, ...]] = {
    "Anthropic": (
        "Claude-3-Haiku",
        "Claude-3.5-Sonnet-20241022",
        "Claude-Opus-4",
        "Claude-Opus-4 (Thinking)",
        "Claude-Sonnet-4",
        "Claude-Sonnet-4 (Thinking)",
    ),
    "OpenAI": (
        "GPT-4-Turbo-2024-04-09",
        "GPT-4O-2024-08-06",
        "GPT-4O-mini-2024-07-18",
        "O3 (High)",
        "O3-Mini-2025-01-31 (High)",
        "O3-Mini-2025-01-31 (Low)",
        "O3-Mini-2025-01-31 (Med)",
        "O4-Mini (High)",
        "O4-Mini (Low)",
        "O4-Mini (Medium)",
    ),
    "Google": (
        "Gemini-2.5-Flash-04-17",
        "Gemini-2.5-Flash-05-20",
        "Gemini-2.5-Pro-05-06",
        "Gemini-2.5-Pro-06-05",
    ),
    "DeepSeek": ("DeepSeek-R1-0528", "DeepSeek-V3"),
    "NVIDIA": ("OpenCodeReasoning-Nemotron-1.1-32B", "OpenReasoning-Nemotron-32B"),
    "xAI": ("Grok-3-Mini (High)",),
    "LG": ("EXAONE-4.0-32B",),
    "Alibaba": ("Qwen3-235B-A22B",),
    "Developer of XBai-o4-medium": ("XBai-o4-medium",),
}

DISCLOSURES = {
    "reference_replay_seen": (
        "The author saw a scratch replay on the 3 reference models before this freeze. The "
        "rules choose every tuned value from simulated results only. This choice reduces the "
        "bias from that replay, but it does not remove it. The simulated models start from "
        "the grades of the same 3 reference models."
    ),
    "public_panel_read": (
        "Before this freeze, the author read these facts from the public panel: the file "
        "shape, the model names, and the count of each pass@1 value. The author also read "
        "the question dates, difficulty labels, and platforms, and the release_date field. "
        "Nobody computed a score or a decision of a public model."
    ),
    "ordering_criterion_change": (
        "The ordering criterion of the pruned-set test changed after the author saw the "
        "3-model results. The criterion now applies only to model pairs with a full-set gap "
        "of 0.10 or more. The author fixed this change before anyone read a public grade."
    ),
}


@dataclass(frozen=True, slots=True)
class Pins:
    """The hashes of the committed inputs that the replays use."""

    mapping_sha256: str
    reference_panel_sha256: str


@dataclass(frozen=True, slots=True)
class SimulatedRun:
    """A checked simulated run of the draft policy: its summary and its hashes."""

    policy_key: str
    policy_sha256: str
    summary_sha256: str
    manifest_sha256: str
    analysis_version: str
    benchmarks: Mapping[str, Mapping[str, Any]]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> tuple[bytes, Any]:
    try:
        data = path.read_bytes()
        return data, json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read {path}: {exc}") from exc


def _get(value: object, *keys: str) -> object:
    """A nested value, or None when a level is missing or is not an object."""
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def read_simulated_run(run_dir: Path, *, policy_key: str, policy_sha256: str) -> SimulatedRun:
    """Read the summary of one run and check it against its manifest and the draft.

    The manifest must name the draft hash, simulated mode, and no real grades.
    The summary bytes must have the hash that the manifest records.
    """
    manifest_bytes, manifest = _json(run_dir / "manifest.json")
    summary_bytes, summary = _json(run_dir / "summary.json")
    if not isinstance(manifest, dict) or manifest.get("command") != "threshold-decision":
        raise AnalysisError(f"{run_dir} is not the output of threshold-decision")
    if manifest.get("mode") != "simulated" or manifest.get("real_grades_used") is not False:
        raise AnalysisError(f"{run_dir} is not a simulated run; only simulated results count")
    recorded = _get(manifest, "policy", "sha256")
    if recorded != policy_sha256:
        raise AnalysisError(
            f"{run_dir} ran policy SHA-256 {recorded}, not the draft {policy_sha256}"
        )
    summary_sha256 = _sha(summary_bytes)
    if _get(manifest, "output_sha256", "summary.json") != summary_sha256:
        raise AnalysisError(f"{run_dir}/summary.json does not match its manifest hash")
    if not isinstance(summary, dict) or summary.get("mode") != "simulated":
        raise AnalysisError(f"{run_dir}/summary.json is not a simulated summary")
    if _get(summary, "policy", "key") != policy_key:
        raise AnalysisError(f"{run_dir}/summary.json is not a run of {policy_key}")
    documents = summary.get("benchmarks")
    if not isinstance(documents, list) or not all(
        isinstance(b, dict) and isinstance(b.get("benchmark"), str) for b in documents
    ):
        raise AnalysisError(f"{run_dir}/summary.json has no benchmark documents")
    benchmarks = {b["benchmark"]: b for b in documents}
    return SimulatedRun(
        policy_key=policy_key,
        policy_sha256=policy_sha256,
        summary_sha256=summary_sha256,
        manifest_sha256=_sha(manifest_bytes),
        analysis_version=str(summary["analysis_version"]),
        benchmarks=benchmarks,
    )


def choose_from_run(run: SimulatedRun) -> dict[str, Choice]:
    """Apply the rules to each benchmark of the run, in report order."""
    try:
        return {
            name: choose_values(
                document["coverage"],
                document["error_rate"],
                true_scores=document["error_rate"]["true_scores"],
            )
            for name, document in run.benchmarks.items()
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisError(f"The simulated summary lacks a study result: {exc!r}") from exc


def simulated_d95(document: Mapping[str, Any], choice: Choice) -> dict[str, float | None]:
    """The d95 of #60 for the chosen setting, for the real-against-simulated comparison."""
    key = (choice.stratifier, choice.stage1_size, choice.interval_method)
    try:
        setting = next(
            (
                c
                for c in document["error_rate"]["combined"]
                if (c["stratifier"], c["stage_size"], c["method"]) == key
            ),
            None,
        )
        if setting is None:
            raise AnalysisError(f"The error-rate study has no setting {key}")
        return {
            "d95": setting["d95"],
            "d95_below": setting["d95_below"],
            "d95_above": setting["d95_above"],
            **{g: setting["d95_by_generator"][g] for g in REQUIRED_GENERATORS},
        }
    except (KeyError, TypeError) as exc:
        raise AnalysisError(f"The simulated summary lacks the d95 of {key}: {exc!r}") from exc


def selection_record(choice: Choice) -> dict[str, Any]:
    """The candidates that the rules compared and the values that they chose."""
    return {
        "interval_method": {
            "chosen": choice.interval_method,
            "candidates": [
                {
                    "method": m.method,
                    "cells": m.cells,
                    "cells_failed": m.cells_failed,
                    "mean_width": m.mean_width,
                }
                for m in choice.methods
            ],
        },
        "probe": {
            "chosen": {"stratifier": choice.stratifier, "stage_size": choice.stage1_size},
            "candidates": [
                {
                    "stratifier": p.stratifier,
                    "stage_size": p.stage_size,
                    "passes_both_generators": p.passes_both_generators,
                    "mean_cost_fraction": {g: p.cost_by_generator[g] for g in REQUIRED_GENERATORS},
                }
                for p in choice.probes
            ],
        },
    }


def _criterion(statement: str, **limits: float) -> dict[str, Any]:
    return {"statement": statement, **limits}


def replay_protocol(
    *, livecodebench: Choice, d95: Mapping[str, float | None], pins: Pins
) -> dict[str, Any]:
    """Every fixed value of the real replays (#63, #77, #80), with the pass criteria.

    ``livecodebench`` holds the chosen values of the LiveCodeBench section. The
    1,055-question arm of #77 uses its stage-1 fraction, rounded up. The
    pruned-set test uses its interval method. ``d95`` is the simulated d95 of
    the chosen LiveCodeBench setting.
    """
    stage1_size = livecodebench.stage1_size
    full_panel_stage1 = math.ceil(Fraction(stage1_size * PUBLIC_QUESTIONS, MAPPED_QUESTIONS))
    seeds = {"first": 0, "last": 999}
    return {
        "decision": {"stages": 2, "indifference_zone": {"primary": 0, "secondary": 0.02}},
        "public_panel": {
            "issue": 75,
            "url": PINNED_SOURCE.url,
            "sha256": PINNED_SOURCE.sha256,
            "models": PUBLIC_MODELS,
            "questions": PUBLIC_QUESTIONS,
            "mapping_sha256": pins.mapping_sha256,
            "mapped_questions": MAPPED_QUESTIONS,
        },
        "grade_rule": {
            "field": "pass@1",
            "primary_min_pass_at_1": 50,
            "secondary_min_pass_at_1": 100,
            "full_set_uses_same_rule": True,
            "statement": "A question passes when pass@1 is 50 or more. The secondary rule "
            "is pass@1 equal to 100. The full-set score uses the same rule as the probe.",
        },
        "unseen_model_replay": {
            "issue": 63,
            "benchmark": LIVE_CODE_BENCH,
            "strata": "committed_reference_panel",
            "reference_panel_sha256": pins.reference_panel_sha256,
            "targets": PUBLIC_MODELS,
            "questions": MAPPED_QUESTIONS,
            "thresholds": {"start": 0.3, "stop": 0.9, "step": 0.01},
            "selection_seeds": seeds,
            "coverage_subsets": 2000,
            "baseline": {
                "selector": "uniform_random",
                "interval_method": POOLED_EXACT,
                "same_stage1_size": True,
            },
            "pass_criteria": {
                "wrong_decision_rate": _criterion(
                    "For each model and threshold, the wrong-decision rate across the 1,000 "
                    "seeds is at most 0.071. This is the pass rule of #60.",
                    max=0.071,
                ),
                "coverage": _criterion(
                    "For each model, the interval holds the full-set score in at least 0.935 "
                    "of the 2,000 subsets at the policy stage-1 size.",
                    min=0.935,
                ),
                "mean_cost_at_primary_threshold": _criterion(
                    "At the primary threshold, the mean expected cost across the models is "
                    "below 1.0 of a full run.",
                    below=1.0,
                ),
            },
            "stated_comparisons": {
                "stage1_share_vs_random_probe": _criterion(
                    "The share decided at stage 1 for the stratified probe against the random "
                    "probe. No pass or fail mark."
                ),
                "real_vs_simulated_d95": {
                    **_criterion(
                        "The real d95 against the simulated d95 of #60 for the policy setting. "
                        "No pass or fail mark."
                    ),
                    "simulated": dict(d95),
                },
            },
        },
        "reference_panel_study": {
            "issue": 77,
            "strata": "reference_pass_rate",
            "group_sizes": "near_equal",
            "groups": 4,
            "secondary_groups": 8,
            "full_panel_questions": PUBLIC_QUESTIONS,
            "full_panel_stage1_size": full_panel_stage1,
            "developer_groups": {group: list(names) for group, names in DEVELOPER_GROUPS.items()},
        },
        "pruned_set_test": {
            "issue": 80,
            "benchmark": LIVE_CODE_BENCH,
            "strata": "committed_reference_panel",
            "score": "weighted",
            "sizes": [95, 158],
            "reported_sizes": [63],
            "interval_method": livecodebench.interval_method,
            "published_seed": 42,
            "selection_seeds": seeds,
            "coverage_subsets": 2000,
            "pass_criteria": {
                "published_mean_abs_error": _criterion(
                    "Published set: the mean absolute error across the 28 models is at most 0.03.",
                    max=0.03,
                ),
                "published_max_abs_error": _criterion(
                    "Published set: the largest absolute error across the 28 models is at "
                    "most 0.08.",
                    max=0.08,
                ),
                "seed_mean_abs_error": _criterion(
                    "Seeds: for each model, the mean absolute error across the 1,000 seeds is "
                    "at most 0.03.",
                    max=0.03,
                ),
                "seed_abs_error_share": _criterion(
                    "Seeds: for each model, the absolute error is at most 0.08 in at least 95% "
                    "of the seeds.",
                    error_max=0.08,
                    min_share=0.95,
                ),
                "coverage": _criterion(
                    "Coverage: for each model, the interval holds the full-set score in at "
                    "least 0.935 of 2,000 new subsets.",
                    min=0.935,
                ),
                "ordering": _criterion(
                    "Ordering: for each model pair with a full-set gap of 0.10 or more, the "
                    "pruned scores give the full-set order in at least 95% of the seeds.",
                    min_gap=0.10,
                    min_share=0.95,
                ),
            },
        },
        "disclosures": dict(DISCLOSURES),
    }


def frozen_policy_value(
    draft: Mapping[str, Any],
    *,
    version: str,
    run: SimulatedRun,
    choices: Mapping[str, Choice],
    pins: Pins,
) -> dict[str, Any]:
    """The draft with the chosen values, a new version, the protocol, and the selection."""
    if set(choices) != set(draft["benchmarks"]):
        raise AnalysisError(
            f"The run covers {sorted(choices)}, but the draft has {sorted(draft['benchmarks'])}"
        )
    if LIVE_CODE_BENCH not in choices:
        raise AnalysisError("The replay protocol needs the LiveCodeBench section")
    sections = {}
    for name, section in draft["benchmarks"].items():
        choice = choices[name]
        sections[name] = {
            **section,
            "interval_method": choice.interval_method,
            "stratifier": choice.stratifier,
            "stage1_size": choice.stage1_size,
        }
    lcb = choices[LIVE_CODE_BENCH]
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": draft["policy_id"],
        "version": version,
        "frozen": True,
        "benchmarks": sections,
        "protocol": replay_protocol(
            livecodebench=lcb,
            d95=simulated_d95(run.benchmarks[LIVE_CODE_BENCH], lcb),
            pins=pins,
        ),
        "selection": {
            "rules": {"interval_method": INTERVAL_RULE, "probe": PROBE_RULE},
            "source": {
                "policy": run.policy_key,
                "policy_sha256": run.policy_sha256,
                "summary_sha256": run.summary_sha256,
                "manifest_sha256": run.manifest_sha256,
                "analysis_version": run.analysis_version,
            },
            "benchmarks": {name: selection_record(choice) for name, choice in choices.items()},
        },
    }


def check_developer_groups(models: Sequence[str]) -> None:
    """The developer groups must name each public model exactly once."""
    grouped = sorted(name for names in DEVELOPER_GROUPS.values() for name in names)
    if grouped != sorted(models):
        missing = sorted(set(models) - set(grouped))
        extra = sorted(set(grouped) - set(models))
        raise AnalysisError(
            f"The developer groups do not match the public models: missing {missing}, "
            f"unknown {extra}"
        )


def _lock_with(lock_path: Path, key: str, sha256: str) -> bytes:
    _, lock = _json(lock_path)
    if (
        not isinstance(lock, dict)
        or lock.get("schema_version") != 1
        or not isinstance(lock.get("policies"), dict)
    ):
        raise AnalysisError(f"The frozen-policy lock {lock_path} is invalid")
    if key in lock["policies"]:
        raise AnalysisError(
            f"The lock {lock_path} already holds {key}; a change needs a new policy version"
        )
    return encode_json({**lock, "policies": {**lock["policies"], key: sha256}})


@dataclass(frozen=True, slots=True)
class Frozen:
    """The written policy, its lock key, its hash, and the chosen values."""

    path: Path
    key: str
    sha256: str
    choices: Mapping[str, Choice]


def freeze(
    *,
    draft_path: Path,
    run_dir: Path,
    output: Path,
    version: str,
    lock_path: Path = FROZEN_LOCK,
    mapping_path: Path = DEFAULT_MAPPING,
    reference_panel_path: Path = DEFAULT_REFERENCE_PANEL,
) -> Frozen:
    """Write the frozen policy and its lock entry. Refuse to overwrite either."""
    if output.exists():
        raise AnalysisError(f"{output} exists. This command never overwrites a policy file")
    draft = load_policy(draft_path)
    if version == draft.version:
        raise AnalysisError(f"Version {version} is the version of the draft; choose a new one")
    _, draft_value = _json(draft_path)
    run = read_simulated_run(run_dir, policy_key=draft.key, policy_sha256=draft.sha256)
    choices = choose_from_run(run)
    mapping_bytes, mapping = _json(mapping_path)
    panel_sha256 = _sha(reference_panel_path.read_bytes())
    if (
        _get(mapping, "panel_sha256") != panel_sha256
        or _get(mapping, "public_sha256") != PINNED_SOURCE.sha256
    ):
        raise AnalysisError(
            f"The mapping {mapping_path} does not name the reference panel and the public pin"
        )
    if _get(run.benchmarks.get(LIVE_CODE_BENCH), "reference_panel_sha256") != panel_sha256:
        raise AnalysisError("The simulated run used another LiveCodeBench reference panel")
    pins = Pins(mapping_sha256=_sha(mapping_bytes), reference_panel_sha256=panel_sha256)
    value = frozen_policy_value(draft_value, version=version, run=run, choices=choices, pins=pins)
    data = encode_json(value)
    key = f"{value['policy_id']}@{version}"
    lock_bytes = _lock_with(lock_path, key, _sha(data))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(output, data)
    try:
        # The loader must accept the frozen file before the lock records it.
        loaded = load_policy(output)
        write_atomic(lock_path, lock_bytes)
    except (AnalysisError, OSError):
        # No policy file stays behind without its lock entry.
        output.unlink(missing_ok=True)
        raise
    return Frozen(path=output, key=loaded.key, sha256=loaded.sha256, choices=choices)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Apply the fixed rules to a simulated run of the draft and freeze a policy."
    )
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT, help="Draft policy file")
    parser.add_argument(
        "--simulated-run",
        type=Path,
        required=True,
        help="Output folder of threshold-decision run on the draft policy",
    )
    parser.add_argument("--output", type=Path, required=True, help="New frozen policy file")
    parser.add_argument("--version", required=True, help="New policy version, for example v1")
    parser.add_argument(
        "--lock", type=Path, default=FROZEN_LOCK, help="Frozen-policy lock file to extend"
    )
    parser.add_argument(
        "--public-file",
        type=Path,
        help="Pinned public LiveCodeBench file; only its model names are read",
    )
    args = parser.parse_args(argv)
    try:
        if args.public_file is not None:
            # Model names only: load_public_results gives no grade.
            check_developer_groups(load_public_results(args.public_file).models)
        frozen = freeze(
            draft_path=args.draft,
            run_dir=args.simulated_run,
            output=args.output,
            version=args.version,
            lock_path=args.lock,
        )
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"threshold-freeze: {exc}\n")
    for name, choice in frozen.choices.items():
        print(
            f"{name}: interval_method {choice.interval_method}, stratifier "
            f"{choice.stratifier}, stage1_size {choice.stage1_size} "
            f"(mean cost {float(choice.probe.cost):.4f} of a full run)"
        )
    if args.public_file is None:
        print("Developer groups: not checked against the public model names")
    else:
        print(f"Developer groups: each of the {PUBLIC_MODELS} public model names appears once")
    print(f"Wrote {frozen.path} ({frozen.key}), frozen")
    print(f"Policy SHA-256: {frozen.sha256}")


if __name__ == "__main__":
    main()
