"""Valid frozen policy files for tests, made by the freeze builder of the package.

A frozen file must hold the replay protocol and a selection record whose
candidates give the section values under the fixed rules. ``frozen_value``
makes synthetic simulated results that choose the values of each section, then
builds the file with ``frozen_policy_value``.
"""

import copy
import json
from pathlib import Path
from typing import Any

from benchmark_reference.threshold_benchmarks import BENCHMARKS
from benchmark_reference.threshold_freeze import (
    Pins,
    SimulatedRun,
    choose_from_run,
    frozen_policy_value,
)
from benchmark_reference.threshold_intervals import INTERVAL_METHODS

TASK2 = Path(__file__).parents[1]
DRAFT = TASK2 / "policies" / "threshold-draft.json"
GRID = [k / 100 for k in range(30, 91)]
PINS = Pins(mapping_sha256="a" * 64, reference_panel_sha256="b" * 64)


def draft_value() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(DRAFT.read_text(encoding="utf-8"))
    return value


def simulated_document(name: str, section: dict[str, Any]) -> dict[str, Any]:
    """Coverage and error-rate summaries in which the rules choose the section values."""
    method, stratifier, size = (
        section["interval_method"],
        section["stratifier"],
        section["stage1_size"],
    )
    methods = [
        {"method": m, "cells": 4, "cells_failed": 0, "mean_width": 0.1 if m == method else 0.2}
        for m in INTERVAL_METHODS
    ]
    combined = []
    for m in INTERVAL_METHODS:
        for s in BENCHMARKS[name].stratifiers:
            for n in section["error_rate"]["stage_sizes"]:
                cost = 0.4 if (m, s, n) == (method, stratifier, size) else 0.5
                combined.append(
                    {
                        "method": m,
                        "stratifier": s,
                        "stage_size": n,
                        "passes_both_generators": True,
                        "mean_expected_cost_fraction_by_generator": {
                            "rasch": cost,
                            "reference_flip": cost,
                        },
                        "d95": 0.19,
                        "d95_below": 0.19,
                        "d95_above": 0.17,
                        "d95_by_generator": {"rasch": 0.18, "reference_flip": 0.19},
                    }
                )
    return {
        "benchmark": name,
        "reference_panel_sha256": PINS.reference_panel_sha256,
        "coverage": {"methods": methods},
        "error_rate": {
            "generators": ["rasch", "reference_flip"],
            "true_scores": GRID,
            "combined": combined,
        },
    }


def simulated_run(base: dict[str, Any]) -> SimulatedRun:
    return SimulatedRun(
        policy_key=f"{base['policy_id']}@{base['version']}",
        policy_sha256="c" * 64,
        summary_sha256="d" * 64,
        manifest_sha256="e" * 64,
        analysis_version="threshold-two-stage-v5",
        benchmarks={n: simulated_document(n, s) for n, s in base["benchmarks"].items()},
    )


def frozen_value(base: dict[str, Any] | None = None, *, version: str = "v1") -> dict[str, Any]:
    """A valid frozen policy with the sections of ``base`` (default: the draft)."""
    base = copy.deepcopy(draft_value() if base is None else base)
    run = simulated_run(base)
    return frozen_policy_value(
        base, version=version, run=run, choices=choose_from_run(run), pins=PINS
    )


def write_policy(path: Path, value: object) -> Path:
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path
