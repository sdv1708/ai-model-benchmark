"""The replay protocol and the selection record of a frozen policy file.

A frozen policy holds two blocks beside its benchmark sections:

- ``protocol`` holds every value that the real replays need: the grade rule,
  the public-panel pin, the replay settings, the baseline, the reference-panel
  study, the pruned-set test, every pass criterion, the stated comparisons, and
  the disclosures that the report must make.
- ``selection`` records the simulated results that chose the tuned values of
  each section, and the source run that gave them.

The loader requires both blocks in a frozen file and rejects a file that lacks
any key. It also re-applies the rules of ``threshold_rules`` to the recorded
candidates. The chosen values must agree with the rules and with the sections.
A hand edit of a chosen value therefore stops the loader.

This module imports no other policy module.
"""

import math
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any, NamedTuple

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import BENCHMARKS, LIVE_CODE_BENCH
from benchmark_reference.threshold_intervals import INTERVAL_METHODS
from benchmark_reference.threshold_rules import (
    INTERVAL_RULE,
    PROBE_RULE,
    REQUIRED_GENERATORS,
    MethodCandidate,
    ProbeCandidate,
    choose_interval_method,
    choose_probe,
)


class SectionFacts(NamedTuple):
    """The values of one benchmark section that the frozen blocks must agree with."""

    threshold: float
    stage1_size: int
    interval_method: str
    stratifier: str
    error_stage_sizes: tuple[int, ...]


type Validator = Callable[[object, str], None]
type Spec = Mapping[str, "Validator | Spec"]

_GRID_KEYS = {"start", "stop", "step"}
BASELINE_SELECTORS = ("uniform_random",)
STRATA_SOURCES = ("committed_reference_panel",)
DIFFICULTY_STRATA = ("reference_pass_rate",)
GROUP_SIZES = ("near_equal",)
SCORES = ("weighted",)


def _fail(path: str, message: str) -> AnalysisError:
    return AnalysisError(f"Policy {path} {message}")


def _number_value(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value)


def grid(value: object, name: str) -> tuple[float, ...]:
    """Values from ``start`` to ``stop`` in exact decimal steps of ``step``.

    Each value must be a multiple of 0.01, so every value has an exact
    two-decimal label. The step must divide the span exactly.
    """
    if not isinstance(value, dict) or set(value) != _GRID_KEYS:
        raise AnalysisError(f"Policy {name} keys must be exactly {sorted(_GRID_KEYS)}")
    for key in ("start", "stop"):
        edge = value[key]
        if not _number_value(edge) or not 0 <= edge <= 1:
            raise AnalysisError(f"Policy {name} {key} must be in [0, 1]")
    start, stop = Fraction(str(value["start"])), Fraction(str(value["stop"]))
    if start > stop:
        raise AnalysisError(f"Policy {name} start must not exceed stop")
    step_value = value["step"]
    if (
        not _number_value(step_value)
        or not 0 <= step_value <= 1
        or Fraction(str(step_value)) < Fraction(1, 100)
    ):
        raise AnalysisError(f"Policy {name} step must be in [0.01, 1]")
    step = Fraction(str(step_value))
    if any((v * 100).denominator != 1 for v in (start, stop, step)):
        raise AnalysisError(f"Policy {name} start, stop, and step need 2 decimals")
    points = (stop - start) / step
    if points.denominator != 1:
        raise AnalysisError(f"Policy {name} step must divide stop - start")
    return tuple(float(start + k * step) for k in range(int(points) + 1))


def _integer(minimum: int, maximum: int | None = None) -> Validator:
    def check(value: object, path: str) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            upper = "" if maximum is None else f" and at most {maximum}"
            raise _fail(path, f"must be an integer of at least {minimum}{upper}")

    return check


def _number(low: float, high: float, *, low_open: bool = False) -> Validator:
    def check(value: object, path: str) -> None:
        if (
            not _number_value(value)
            or not low <= value <= high  # type: ignore[operator]
            or (low_open and value == low)
        ):
            bracket = "(" if low_open else "["
            raise _fail(path, f"must be a number in {bracket}{low}, {high}]")

    return check


def _distance(value: object, path: str) -> None:
    """A d95 value: a distance in [0, 1], or null when the probe never reaches 95%."""
    if value is not None:
        _number(0, 1)(value, path)


def _text(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, "must be nonempty text")


def _sha256(value: object, path: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise _fail(path, "must be a lowercase SHA-256 of 64 hexadecimal digits")


def _choice(options: tuple[object, ...]) -> Validator:
    def check(value: object, path: str) -> None:
        if type(value) is not type(options[0]) or value not in options:
            raise _fail(path, f"must be one of {list(options)}")

    return check


def _sizes(value: object, path: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in value)
        or value != sorted(set(value))
    ):
        raise _fail(path, "must be unique, ascending integers of at least 1")


def _grid_check(value: object, path: str) -> None:
    grid(value, path)


def _seed_range(value: object, path: str) -> None:
    _validate(value, {"first": _integer(0), "last": _integer(0)}, path)
    assert isinstance(value, dict)
    if value["first"] > value["last"]:
        raise _fail(path, "first must not exceed last")


def _statement(**limits: Validator) -> Spec:
    """A pass criterion or a comparison: its sentence and its numeric limits."""
    return {"statement": _text, **limits}


def _groups(value: object, path: str) -> None:
    if not isinstance(value, dict) or not value:
        raise _fail(path, "must map each developer group to its model names")
    seen: set[str] = set()
    for group, models in value.items():
        _text(group, f"{path} group name")
        where = f"{path}.{group}"
        if not isinstance(models, list) or not models:
            raise _fail(where, "must be a nonempty list of model names")
        for model in models:
            _text(model, where)
            if model in seen:
                raise _fail(where, f"names model {model!r} more than once")
            seen.add(model)
        if models != sorted(models):
            raise _fail(where, "must list its model names in sorted order")


def _simulated_d95(value: object, path: str) -> None:
    _validate(
        value,
        {
            "d95": _distance,
            "d95_below": _distance,
            "d95_above": _distance,
            **dict.fromkeys(REQUIRED_GENERATORS, _distance),
        },
        path,
    )


PROTOCOL_SPEC: Spec = {
    "decision": {
        # The decision code has two stages: the probe and the census.
        "stages": _choice((2,)),
        "indifference_zone": {"primary": _number(0, 0.5), "secondary": _number(0, 0.5)},
    },
    "public_panel": {
        "issue": _integer(1),
        "url": _text,
        "sha256": _sha256,
        "models": _integer(1),
        "questions": _integer(1),
        "mapping_sha256": _sha256,
        "mapped_questions": _integer(1),
    },
    "grade_rule": {
        "field": _choice(("pass@1",)),
        "primary_min_pass_at_1": _number(0, 100),
        "secondary_min_pass_at_1": _number(0, 100),
        "full_set_uses_same_rule": _choice((True,)),
        "statement": _text,
    },
    "unseen_model_replay": {
        "issue": _integer(1),
        "benchmark": _choice((LIVE_CODE_BENCH,)),
        "strata": _choice(STRATA_SOURCES),
        "reference_panel_sha256": _sha256,
        "targets": _integer(1),
        "questions": _integer(1),
        "thresholds": _grid_check,
        "selection_seeds": _seed_range,
        "coverage_subsets": _integer(1),
        "baseline": {
            "selector": _choice(BASELINE_SELECTORS),
            "interval_method": _choice(INTERVAL_METHODS),
            "same_stage1_size": _choice((True,)),
        },
        "pass_criteria": {
            "wrong_decision_rate": _statement(max=_number(0, 1)),
            "coverage": _statement(min=_number(0, 1)),
            "mean_cost_at_primary_threshold": _statement(below=_number(0, 1, low_open=True)),
        },
        "stated_comparisons": {
            "stage1_share_vs_random_probe": _statement(),
            "real_vs_simulated_d95": _statement(simulated=_simulated_d95),
        },
    },
    "reference_panel_study": {
        "issue": _integer(1),
        "strata": _choice(DIFFICULTY_STRATA),
        "group_sizes": _choice(GROUP_SIZES),
        "groups": _integer(1),
        "secondary_groups": _integer(1),
        "full_panel_questions": _integer(1),
        "full_panel_stage1_size": _integer(1),
        "developer_groups": _groups,
    },
    "pruned_set_test": {
        "issue": _integer(1),
        "benchmark": _choice((LIVE_CODE_BENCH,)),
        "strata": _choice(STRATA_SOURCES),
        "score": _choice(SCORES),
        "sizes": _sizes,
        "reported_sizes": _sizes,
        # The interval of the coverage criterion: the method of the LiveCodeBench section.
        "interval_method": _choice(INTERVAL_METHODS),
        "published_seed": _integer(0),
        "selection_seeds": _seed_range,
        "coverage_subsets": _integer(1),
        "pass_criteria": {
            "published_mean_abs_error": _statement(max=_number(0, 1)),
            "published_max_abs_error": _statement(max=_number(0, 1)),
            "seed_mean_abs_error": _statement(max=_number(0, 1)),
            "seed_abs_error_share": _statement(error_max=_number(0, 1), min_share=_number(0, 1)),
            "coverage": _statement(min=_number(0, 1)),
            "ordering": _statement(min_gap=_number(0, 1), min_share=_number(0, 1)),
        },
    },
    "disclosures": {
        "reference_replay_seen": _text,
        "public_panel_read": _text,
        "ordering_criterion_change": _text,
    },
}


def _validate(value: object, spec: Spec, path: str) -> None:
    if not isinstance(value, dict) or set(value) != set(spec):
        raise _fail(path, f"keys must be exactly {sorted(spec)}")
    for key, rule in spec.items():
        where = f"{path}.{key}"
        if callable(rule):
            rule(value[key], where)
        else:
            _validate(value[key], rule, where)


def _method_candidate(value: object, path: str) -> MethodCandidate:
    spec: Spec = {
        "method": _choice(INTERVAL_METHODS),
        "cells": _integer(0),
        "cells_failed": _integer(0),
        "mean_width": _number(0, 1),
    }
    _validate(value, spec, path)
    assert isinstance(value, dict)
    return MethodCandidate(
        value["method"], value["cells"], value["cells_failed"], float(value["mean_width"])
    )


def _probe_candidate(value: object, path: str, stratifiers: tuple[str, ...]) -> ProbeCandidate:
    spec: Spec = {
        "stratifier": _choice(stratifiers),
        "stage_size": _integer(1),
        "passes_both_generators": _choice((True, False)),
        "mean_cost_fraction": dict.fromkeys(REQUIRED_GENERATORS, _number(0, 1)),
    }
    _validate(value, spec, path)
    assert isinstance(value, dict)
    return ProbeCandidate(
        value["stratifier"],
        value["stage_size"],
        value["passes_both_generators"],
        dict(value["mean_cost_fraction"]),
    )


def _candidates(value: object, path: str) -> None:
    if not isinstance(value, list) or not value:
        raise _fail(path, "must be a nonempty list")


def validate_selection(raw: object, sections: Mapping[str, SectionFacts]) -> Mapping[str, Any]:
    """Check the selection record and re-apply the rules to its candidates.

    The candidates must be complete: every interval method, and every
    stratifier at every error-rate stage size of the section. The rules must
    choose exactly the interval method, stratifier, and stage-1 size of the
    section.
    """
    path = "selection"
    _validate(
        raw,
        {
            "rules": {"interval_method": _text, "probe": _text},
            "source": {
                "policy": _text,
                "policy_sha256": _sha256,
                "summary_sha256": _sha256,
                "manifest_sha256": _sha256,
                "analysis_version": _text,
            },
            "benchmarks": lambda value, where: None,
        },
        path,
    )
    assert isinstance(raw, dict)
    if raw["rules"] != {"interval_method": INTERVAL_RULE, "probe": PROBE_RULE}:
        raise _fail(f"{path}.rules", "must state the rules that this package applies")
    benchmarks = raw["benchmarks"]
    if not isinstance(benchmarks, dict) or set(benchmarks) != set(sections):
        raise _fail(f"{path}.benchmarks", f"keys must be exactly {sorted(sections)}")
    for name, facts in sections.items():
        where = f"{path}.benchmarks.{name}"
        record = benchmarks[name]
        _validate(
            record,
            {
                "interval_method": {
                    "chosen": _choice(INTERVAL_METHODS),
                    "candidates": _candidates,
                },
                "probe": {
                    "chosen": {"stratifier": _text, "stage_size": _integer(1)},
                    "candidates": _candidates,
                },
            },
            where,
        )
        methods = [
            _method_candidate(c, f"{where}.interval_method.candidates")
            for c in record["interval_method"]["candidates"]
        ]
        stratifiers = BENCHMARKS[name].stratifiers
        probes = [
            _probe_candidate(c, f"{where}.probe.candidates", stratifiers)
            for c in record["probe"]["candidates"]
        ]
        if sorted(m.method for m in methods) != sorted(INTERVAL_METHODS):
            raise _fail(f"{where}.interval_method.candidates", "must hold each method once")
        settings = sorted((p.stratifier, p.stage_size) for p in probes)
        expected = sorted((s, n) for s in stratifiers for n in facts.error_stage_sizes)
        if settings != expected:
            raise _fail(
                f"{where}.probe.candidates",
                "must hold each stratifier at each error-rate stage size once",
            )
        recorded = (
            record["interval_method"]["chosen"],
            record["probe"]["chosen"]["stratifier"],
            record["probe"]["chosen"]["stage_size"],
        )
        probe = choose_probe(probes)
        ruled = (choose_interval_method(methods).method, probe.stratifier, probe.stage_size)
        if recorded != ruled:
            raise _fail(where, f"records the choice {recorded}, but its candidates give {ruled}")
        held = (facts.interval_method, facts.stratifier, facts.stage1_size)
        if recorded != held:
            raise _fail(where, f"records the choice {recorded}, but the section holds {held}")
    return raw


def validate_protocol(raw: object, sections: Mapping[str, SectionFacts]) -> Mapping[str, Any]:
    """Check every key of the protocol and its agreement with the sections."""
    _validate(raw, PROTOCOL_SPEC, "protocol")
    assert isinstance(raw, dict)
    zone = raw["decision"]["indifference_zone"]
    if zone["secondary"] < zone["primary"]:
        raise _fail("protocol.decision.indifference_zone", "secondary must be at least primary")
    rule = raw["grade_rule"]
    if rule["secondary_min_pass_at_1"] < rule["primary_min_pass_at_1"]:
        raise _fail("protocol.grade_rule", "secondary rule must be at least as strict as primary")
    panel, replay = raw["public_panel"], raw["unseen_model_replay"]
    if replay["benchmark"] not in sections:
        raise _fail("protocol.unseen_model_replay", "needs the section of its benchmark")
    facts = sections[replay["benchmark"]]
    threshold, stage1_size = facts.threshold, facts.stage1_size
    if replay["questions"] != panel["mapped_questions"]:
        raise _fail(
            "protocol.unseen_model_replay.questions", "must equal the mapped public questions"
        )
    if replay["targets"] != panel["models"]:
        raise _fail("protocol.unseen_model_replay.targets", "must equal the public models")
    thresholds = grid(replay["thresholds"], "protocol.unseen_model_replay.thresholds")
    if Fraction(str(threshold)) not in {Fraction(str(t)) for t in thresholds}:
        raise _fail(
            "protocol.unseen_model_replay.thresholds",
            f"must hold the primary threshold {threshold}",
        )
    study = raw["reference_panel_study"]
    if study["full_panel_questions"] != panel["questions"]:
        raise _fail(
            "protocol.reference_panel_study.full_panel_questions",
            "must equal the public questions",
        )
    # The stage-1 fraction of the replay benchmark, rounded up.
    expected = math.ceil(Fraction(stage1_size * study["full_panel_questions"], replay["questions"]))
    if study["full_panel_stage1_size"] != expected:
        raise _fail(
            "protocol.reference_panel_study.full_panel_stage1_size",
            f"must be {expected}: the stage-1 fraction {stage1_size}/{replay['questions']} "
            f"of {study['full_panel_questions']} questions, rounded up",
        )
    if study["secondary_groups"] == study["groups"]:
        raise _fail("protocol.reference_panel_study.secondary_groups", "must differ from groups")
    named = sum(len(models) for models in study["developer_groups"].values())
    if named != panel["models"]:
        raise _fail(
            "protocol.reference_panel_study.developer_groups",
            f"must name the {panel['models']} public models; it names {named}",
        )
    pruned = raw["pruned_set_test"]
    if (
        pruned["sizes"][-1] > replay["questions"]
        or pruned["reported_sizes"][-1] > replay["questions"]
    ):
        raise _fail("protocol.pruned_set_test", "sizes must not exceed the mapped questions")
    if set(pruned["sizes"]) & set(pruned["reported_sizes"]):
        raise _fail("protocol.pruned_set_test", "reported_sizes must not repeat a tested size")
    if pruned["benchmark"] not in sections:
        raise _fail("protocol.pruned_set_test", "needs the section of its benchmark")
    if pruned["interval_method"] != sections[pruned["benchmark"]].interval_method:
        raise _fail(
            "protocol.pruned_set_test.interval_method",
            "must be the interval method of its benchmark section",
        )
    return raw
