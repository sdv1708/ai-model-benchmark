"""The recorded outputs of the real replay: tables, summary, Markdown report, and manifest.

The outputs hold derived values for each model. No output holds a public grade
of one question. The report applies the pass criteria of the policy and states
each failure plainly.
"""

import csv
import hashlib
import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.threshold_benchmarks import BENCHMARKS
from benchmark_reference.threshold_cost import CostModel, Estimates
from benchmark_reference.threshold_policy import LoadedPolicy
from benchmark_reference.threshold_replay import (
    RANDOM,
    STRATIFIED,
    HoldOutDecision,
    Mark,
    ReplayCell,
    ReplaySettings,
    RuleResults,
    at_threshold,
    criteria_marks,
    mean_cost_fraction,
    real_distances,
    wrong_outside_zone,
)

ANALYSIS_VERSION = "threshold-real-replay-v1"
PRIMARY = "primary"
SECONDARY = "secondary"
OUTPUT_NAMES = (
    "cells.csv",
    "coverage.csv",
    "models.csv",
    "reference_holdout.csv",
    "summary.json",
    "report.md",
    "manifest.json",
)
IMPLEMENTATION_FILES = (
    "models.py",
    "inputs.py",
    "pruning.py",
    "long_context.py",
    "uncertainty.py",
    "public_lcb.py",
    "threshold_benchmarks.py",
    "threshold_intervals.py",
    "threshold_rules.py",
    "threshold_protocol.py",
    "threshold_policy.py",
    "threshold_study.py",
    "threshold_tokens.py",
    "threshold_cost.py",
    "threshold_error_rate.py",
    "two_stage.py",
    "threshold_replay.py",
    "threshold_replay_report.py",
    "threshold_replay_run.py",
    "threshold_cli.py",
)
CRITERION_TITLES = {
    "wrong_decision_rate": "Wrong-decision rate",
    "coverage": "Coverage",
    "mean_cost_at_primary_threshold": "Mean expected cost",
}
# The edges of the distance table. They set the layout of the report only.
DISTANCE_EDGES = ("0", "0.02", "0.05", "0.10", "0.15", "0.20")

# Notes to the v1 disclosures. The text of v1 stays as it is (#62, #63).
DISCLOSURE_NOTES = {
    "reference_replay_seen": (
        'In this text, "the author" means the repository owner and the AI agents that worked '
        "for the owner. A session record of 29 October 2026 shows that an agent made a script "
        "for a scratch threshold replay. The script no longer exists, so this report cannot "
        "check what it read. The owner did not confirm this disclosure from memory."
    ),
    "public_panel_read": (
        "The public loader (#75) parsed and range-checked every pass@1 value in memory before "
        "the freeze. Only model names and question metadata came out of the loader. The owner "
        "confirmed this disclosure with this note on 23 November 2026."
    ),
    "ordering_criterion_change": (
        "Before the freeze, the author read the count of each pass@1 value, as disclosure 2 "
        "says. Nobody computed a score, interval, or decision of a public model. The owner "
        "confirmed this disclosure with this note on 23 November 2026."
    ),
}
LIMITS = (
    "The {models} models come from {developer_groups} developer groups, and they are not "
    "independent. Some models are the same base model at different reasoning settings.",
    "The {seeds:,} decisions of one model at one threshold reuse the same grades. They measure "
    "the question selection only. They do not measure a new answer from the model.",
    "The public grades come from the LiveCodeBench harness. The reference grades come from "
    "EvalScope. This difference does not affect the validity of the interval. It can lower the "
    "share decided at stage 1.",
    "The token cost is an estimate. It uses the saved answers of the 3 reference models, "
    "because the public file has no token count.",
    "The thresholds reuse the same models and probes, so the cells of one model are not "
    "independent.",
    "The result holds for these {questions} LiveCodeBench questions. It is no evidence for another "
    "benchmark.",
)
HOLD_OUT_LIMITS = (
    "There are only 3 models.",
    "Disclosure 1 applies: the author saw a replay on these models before the freeze.",
    "The models are not independent of each other: they answer the same questions, and they "
    "give each other the strata.",
    "The models are not independent of the policy: the simulated models that chose v1 start "
    "from their grades.",
    "The decisions of one model reuse the same grades.",
    "The AA-LCR strata use the question metadata only. Each held-out AA-LCR model therefore "
    "gets the same probes.",
    "An LLM judge gave the AA-LCR grades one time for each answer. The replay "
    "excludes judge noise. Issue #76 measured it after the replay of v1.",
)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where the run came from. ``rerun_reason`` is None for the first run."""

    command: str
    commit: str
    rerun_reason: str | None
    inputs: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ReplayRun:
    """Everything that the outputs need. ``raw`` holds the mapped ``pass@1`` values."""

    loaded: LoadedPolicy
    settings: ReplaySettings
    costs: CostModel
    rules: Mapping[str, RuleResults]
    raw: Mapping[str, Mapping[int, float]]
    hold_out: Sequence[HoldOutDecision]
    hold_out_costs: Mapping[str, CostModel]
    provenance: Provenance

    @property
    def protocol(self) -> Mapping[str, Any]:
        assert self.loaded.protocol is not None
        return self.loaded.protocol

    @property
    def developers(self) -> dict[str, str]:
        groups = self.protocol["reference_panel_study"]["developer_groups"]
        return {model: group for group, models in groups.items() for model in models}


def _round(value: Fraction | float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _csv(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _cells_table(run: ReplayRun) -> bytes:
    columns = (
        "grade_rule",
        "probe",
        "model",
        "threshold",
        "full_passes",
        "full_score",
        "truth",
        "decisions",
        "stage1_go",
        "stage1_no_go",
        "escalate",
        "wrong",
        "wrong_rate",
        "stage1_share",
        "expected_questions",
        "expected_tokens_low",
        "expected_tokens_mean",
        "expected_tokens_high",
        "expected_cost_fraction",
    )
    rows = [
        (
            rule.name,
            c.probe,
            c.model,
            c.threshold,
            c.full_passes,
            _round(c.score),
            c.truth,
            c.draws,
            c.go,
            c.no_go,
            c.escalated,
            c.wrong,
            _round(c.wrong_rate),
            _round(c.decided_share),
            _round(c.questions, 3),
            *(_round(v, 1) for v in c.tokens.values),
            _round(c.tokens.ratio(run.costs.full).mean),
        )
        for rule in run.rules.values()
        for c in rule.cells
    ]
    return _csv(columns, rows)


def _coverage_table(run: ReplayRun) -> bytes:
    columns = (
        "grade_rule",
        "model",
        "subsets",
        "covered",
        "coverage",
        "truth_below_interval",
        "truth_above_interval",
        "mean_width",
    )
    rows = [
        (
            rule.name,
            r.model,
            r.subsets,
            r.covered,
            _round(r.coverage),
            r.truth_below,
            r.truth_above,
            _round(r.mean_width),
        )
        for rule in run.rules.values()
        for r in rule.coverage
    ]
    return _csv(columns, rows)


def _model_rule(run: ReplayRun, rule: RuleResults, model: str) -> dict[str, Any]:
    """The results of one model under one grade rule."""
    mine = [c for c in rule.cells if c.model == model]
    stratified = [c for c in mine if c.probe == STRATIFIED]
    primary = {
        c.probe: c for c in at_threshold(mine, run.settings.primary_threshold)
    }  # one cell for each probe kind
    coverage = next(r for r in rule.coverage if r.model == model)
    return {
        "full_passes": stratified[0].full_passes,
        "full_score": _round(stratified[0].score),
        "max_wrong_rate": _round(max(c.wrong_rate for c in stratified)),
        "coverage": _round(coverage.coverage),
        "stage1_share_at_primary": _round(primary[STRATIFIED].decided_share),
        "random_stage1_share_at_primary": _round(primary[RANDOM].decided_share),
        "wrong_at_primary": primary[STRATIFIED].wrong,
        "cost_fraction_at_primary": _round(primary[STRATIFIED].tokens.ratio(run.costs.full).mean),
        "questions_at_primary": _round(primary[STRATIFIED].questions, 3),
        "stage1_share_all_thresholds": _round(
            Fraction(sum(c.decided for c in stratified), sum(c.draws for c in stratified))
        ),
    }


def model_records(run: ReplayRun) -> list[dict[str, Any]]:
    """One record for each public model, in name order."""
    developers = run.developers
    records = []
    for model in sorted(run.raw):
        values = list(run.raw[model].values())
        records.append(
            {
                "model": model,
                "developer": developers[model],
                "questions": len(values),
                "mean_pass_at_1": round(math.fsum(values) / len(values), 4),
                "neither_0_nor_100": sum(v not in (0, 100) for v in values),
                **{name: _model_rule(run, rule, model) for name, rule in run.rules.items()},
            }
        )
    return records


def _models_table(records: Sequence[Mapping[str, Any]]) -> bytes:
    head = ("model", "developer", "questions", "mean_pass_at_1", "neither_0_nor_100")
    fields = tuple(records[0][PRIMARY])
    columns = (*head, *(f"{rule}_{f}" for rule in (PRIMARY, SECONDARY) for f in fields))
    rows = [
        (
            *(r[h] for h in head),
            *(r[rule][f] for rule in (PRIMARY, SECONDARY) for f in fields),
        )
        for r in records
    ]
    return _csv(columns, rows)


def _hold_out_table(run: ReplayRun) -> bytes:
    columns = (
        "benchmark",
        "model",
        "seed",
        "full_passes",
        "questions",
        "truth",
        "stage1_result",
        "decision",
        "wrong",
        "questions_graded",
        "expected_tokens_mean",
    )
    rows = [
        (
            r.benchmark,
            r.model,
            r.seed,
            r.full_passes,
            r.population,
            r.truth,
            r.result.stage1_result,
            r.result.decision,
            int(r.wrong),
            r.result.questions_graded,
            _round(r.tokens.mean, 1),
        )
        for r in run.hold_out
    ]
    return _csv(columns, rows)


def _share(cells: Sequence[ReplayCell]) -> Fraction:
    return Fraction(sum(c.decided for c in cells), sum(c.draws for c in cells))


def _probe_summary(run: ReplayRun, cells: Sequence[ReplayCell]) -> dict[str, Any]:
    """The results of one probe kind at the primary threshold and at all thresholds."""
    primary = at_threshold(cells, run.settings.primary_threshold)

    def part(members: Sequence[ReplayCell]) -> dict[str, Any]:
        return {
            "cells": len(members),
            "decisions": sum(c.draws for c in members),
            "stage1_decisions": sum(c.decided for c in members),
            "stage1_share": _round(_share(members)),
            "wrong": sum(c.wrong for c in members),
            "max_wrong_rate": _round(max(c.wrong_rate for c in members)),
            "mean_cost_fraction": mean_cost_fraction(members, run.costs).rounded(6),
            "mean_question_fraction": _round(
                sum((c.questions / c.population for c in members), Fraction(0)) / len(members)
            ),
        }

    return {"primary_threshold": part(primary), "all_thresholds": part(cells)}


def _distances(cells: Sequence[ReplayCell]) -> dict[str, float | None]:
    found = real_distances(cells)
    return {
        "d95": _round(found["both"]),
        "d95_below": _round(found["below"]),
        "d95_above": _round(found["above"]),
    }


def _distance_rows(run: ReplayRun, rule: RuleResults) -> list[dict[str, Any]]:
    """The stratified probe by distance from the threshold, over all models and thresholds."""
    edges = [Fraction(e) for e in DISTANCE_EDGES]
    rows = []
    for k, low in enumerate(edges):
        high = edges[k + 1] if k + 1 < len(edges) else None
        members = [
            c
            for c in rule.of(STRATIFIED)
            if abs(c.distance) >= low and (high is None or abs(c.distance) < high)
        ]
        if not members:
            continue
        rows.append(
            {
                "from": float(low),
                "below": None if high is None else float(high),
                "cells": len(members),
                "stage1_share": _round(_share(members)),
                "wrong": sum(c.wrong for c in members),
                "decisions": sum(c.draws for c in members),
                "max_wrong_rate": _round(max(c.wrong_rate for c in members)),
                "mean_cost_fraction": _round(mean_cost_fraction(members, run.costs).mean),
            }
        )
    return rows


def _hold_out_summary(run: ReplayRun) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[HoldOutDecision]] = {}
    for row in run.hold_out:
        groups.setdefault((row.benchmark, row.model), []).append(row)
    records = []
    for (benchmark, model), rows in groups.items():
        outcomes = [r.result.stage1_result for r in rows]
        full: Estimates = run.hold_out_costs[benchmark].full
        records.append(
            {
                "benchmark": benchmark,
                "model": model,
                "threshold": run.loaded.benchmarks[benchmark].threshold,
                "full_passes": rows[0].full_passes,
                "full_score": _round(Fraction(rows[0].full_passes, rows[0].population)),
                "truth": rows[0].truth,
                "decisions": len(rows),
                "stage1_go": outcomes.count("GO"),
                "stage1_no_go": outcomes.count("NO GO"),
                "escalate": outcomes.count("ESCALATE"),
                "wrong": sum(r.wrong for r in rows),
                "mean_questions": _round(
                    Fraction(sum(r.result.questions_graded for r in rows), len(rows)), 3
                ),
                "mean_cost_fraction": _round(
                    Estimates.mean_of([r.tokens for r in rows]).ratio(full).mean
                ),
            }
        )
    return records


def _mark_record(mark: Mark, statement: str) -> dict[str, Any]:
    return {
        "statement": statement,
        "passed": mark.passed,
        "value": _round(mark.value),
        "limit": float(mark.limit),
        "checked": mark.checked,
        "failed": mark.failed,
    }


def summary_document(run: ReplayRun) -> dict[str, Any]:
    """Every number of the report."""
    protocol = run.protocol
    replay = protocol["unseen_model_replay"]
    zone = protocol["decision"]["indifference_zone"]
    marks = criteria_marks(run.rules[PRIMARY], protocol, run.settings, run.costs)
    rules: dict[str, Any] = {}
    for name, rule in run.rules.items():
        stratified = rule.of(STRATIFIED)
        primary = at_threshold(stratified, run.settings.primary_threshold)
        limits = criteria_marks(rule, protocol, run.settings, run.costs)
        rules[name] = {
            "min_pass_at_1": rule.minimum,
            "probes": {kind: _probe_summary(run, rule.of(kind)) for kind in (STRATIFIED, RANDOM)},
            "min_coverage": _round(min(r.coverage for r in rule.coverage)),
            "results_outside_limits": {key: mark.failed for key, mark in limits.items()},
            "real_d95_at_primary_threshold": _distances(primary),
            "real_d95_all_thresholds": _distances(stratified),
            "wrong_outside_indifference_zone": {
                kind: {"zone": value, "wrong": wrong_outside_zone(stratified, Fraction(str(value)))}
                for kind, value in zone.items()
            },
            "by_distance": _distance_rows(run, rule),
        }
    return {
        "schema_version": 1,
        "analysis_version": ANALYSIS_VERSION,
        "mode": "real",
        "policy": {
            "key": run.loaded.key,
            "sha256": run.loaded.sha256,
            "frozen": run.loaded.frozen,
        },
        "primary_threshold": run.settings.primary_threshold,
        "seeds": len(run.settings.seeds),
        "stage1_size": run.loaded.benchmarks[replay["benchmark"]].stage1_size,
        "models": len(run.raw),
        "questions": replay["questions"],
        "developer_groups": len(protocol["reference_panel_study"]["developer_groups"]),
        "criteria": {
            key: _mark_record(mark, replay["pass_criteria"][key]["statement"])
            for key, mark in marks.items()
        },
        "all_criteria_pass": all(mark.passed for mark in marks.values()),
        "simulated_d95": replay["stated_comparisons"]["real_vs_simulated_d95"]["simulated"],
        "grade_rules": rules,
        "model_results": model_records(run),
        "reference_holdout": _hold_out_summary(run),
        "disclosures": {
            key: {"policy_text": protocol["disclosures"][key], "note": note}
            for key, note in DISCLOSURE_NOTES.items()
        },
        "rerun_reason": run.provenance.rerun_reason,
    }


def _table(head: Sequence[str], rows: Sequence[Sequence[object]], *, text: int = 1) -> str:
    """A Markdown table. The first ``text`` columns align left, the others right."""
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" if i < text else "---:" for i in range(len(head))) + " |",
    ]
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _optional(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"


def result_section(doc: Mapping[str, Any]) -> str:
    stratified = doc["grade_rules"][PRIMARY]["probes"][STRATIFIED]
    at, every = stratified["primary_threshold"], stratified["all_thresholds"]
    failed = [CRITERION_TITLES[k] for k, c in doc["criteria"].items() if not c["passed"]]
    if failed:
        verdict = (
            f"**The replay failed {len(failed)} of {len(doc['criteria'])} pass criteria: "
            f'{", ".join(failed)}.** The earlier "full retention" result stays the published '
            "claim."
        )
    else:
        verdict = f"**The replay passed all {len(doc['criteria'])} pass criteria of the policy.**"
    claim = (
        f"At the primary threshold {doc['primary_threshold']}, a probe of "
        f"{doc['stage1_size']} of {doc['questions']} questions made "
        f"{_percent(at['stage1_share'])} of {at['decisions']:,} decisions on "
        f"{doc['models']} unseen models. The other decisions graded the full set. "
        f"Wrong decisions: {at['wrong']:,} of {at['decisions']:,}. The mean expected cost was "
        f"{at['mean_cost_fraction']['mean']:.3f} of a full run, as the mean token estimate. "
        f"Across all thresholds, the probe made {_percent(every['stage1_share'])} of "
        f"{every['decisions']:,} decisions. Wrong decisions: {every['wrong']:,} of "
        f"{every['decisions']:,}. The mean expected cost was "
        f"{every['mean_cost_fraction']['mean']:.3f} of a full run."
    )
    rows = [
        (
            CRITERION_TITLES[key],
            c["statement"],
            f"{c['value']:.4f}",
            f"{c['limit']:g}",
            f"{c['failed']} of {c['checked']}"
            if key != "mean_cost_at_primary_threshold"
            else "one mean",
            "PASS" if c["passed"] else "FAIL",
        )
        for key, c in doc["criteria"].items()
    ]
    table = _table(
        ("Criterion", "Rule", "Worst or mean value", "Limit", "Outside the limit", "Mark"),
        rows,
        text=2,
    )
    note = (
        "The cost criterion uses the mean token estimate. The cost in questions gives the same "
        "mark, because both costs are 1.0 only when every decision escalates."
    )
    return f"## Result\n\n{verdict}\n\n{claim}\n\n{table}\n\n{note}"


def _comparison_section(doc: Mapping[str, Any]) -> str:
    primary = doc["grade_rules"][PRIMARY]
    rows = []
    for scope, title in (
        ("primary_threshold", f"Threshold {doc['primary_threshold']}"),
        ("all_thresholds", "All thresholds"),
    ):
        for kind in (STRATIFIED, RANDOM):
            p = primary["probes"][kind][scope]
            rows.append(
                (
                    title,
                    kind,
                    _percent(p["stage1_share"]),
                    f"{p['wrong']:,} of {p['decisions']:,}",
                    f"{p['max_wrong_rate']:.4f}",
                    f"{p['mean_question_fraction']:.3f}",
                    f"{p['mean_cost_fraction']['mean']:.3f}",
                )
            )
    probes = _table(
        (
            "Scope",
            "Probe",
            "Decided at stage 1",
            "Wrong",
            "Highest wrong rate",
            "Cost, questions",
            "Cost, tokens",
        ),
        rows,
        text=2,
    )
    simulated = doc["simulated_d95"]
    at = primary["real_d95_at_primary_threshold"]
    every = primary["real_d95_all_thresholds"]
    distances = _table(
        ("d95", "Below the threshold", "At or above the threshold", "Both sides"),
        [
            (
                label,
                _optional(d["d95_below"]),
                _optional(d["d95_above"]),
                _optional(d["d95"]),
            )
            for label, d in (
                ("Simulated (#60)", simulated),
                (f"Real, threshold {doc['primary_threshold']}", at),
                ("Real, all thresholds", every),
            )
        ],
    )
    return (
        "## Stated comparisons\n\nThe policy gives these comparisons no pass or fail mark.\n\n"
        f"{probes}\n\nA cost is a share of a full run. The token cost is the mean estimate.\n\n"
        "### Real d95 against simulated d95\n\n"
        "d95 is a distance from the threshold. At d95 and at every larger distance, the probe "
        "makes at least 95% of the decisions. d95 is the smallest such distance. A real d95 at "
        "one threshold has one point for each model, so it is coarse. The second real row uses "
        'every combination of model and threshold. A side with the value "none" has no model, '
        "or its farthest model does not reach 95%.\n\n"
        f"{distances}"
    )


def _distance_section(doc: Mapping[str, Any]) -> str:
    rows = [
        (
            f"{r['from']:.2f} to below {r['below']:.2f}"
            if r["below"] is not None
            else f"{r['from']:.2f} or more",
            r["cells"],
            _percent(r["stage1_share"]),
            f"{r['wrong']:,} of {r['decisions']:,}",
            f"{r['max_wrong_rate']:.4f}",
            f"{r['mean_cost_fraction']:.3f}",
        )
        for r in doc["grade_rules"][PRIMARY]["by_distance"]
    ]
    table = _table(
        (
            "Distance from the threshold",
            "Cells",
            "Decided at stage 1",
            "Wrong",
            "Highest wrong rate",
            "Cost, tokens",
        ),
        rows,
    )
    return (
        "## Results by distance\n\nThe table uses the stratified probe and every combination of "
        "model and threshold. The distance ranges are a layout choice of this report. The policy "
        f"does not set them, and no mark uses them.\n\n{table}"
    )


def _model_section(doc: Mapping[str, Any]) -> str:
    rows = []
    for m in sorted(doc["model_results"], key=lambda m: (-m[PRIMARY]["full_score"], m["model"])):
        p, s = m[PRIMARY], m[SECONDARY]
        rows.append(
            (
                m["model"],
                m["developer"],
                f"{p['full_score']:.3f}",
                f"{m['mean_pass_at_1']:.2f}",
                m["neither_0_nor_100"],
                _percent(p["stage1_share_at_primary"]),
                f"{p['max_wrong_rate']:.3f}",
                f"{p['coverage']:.4f}",
                f"{p['cost_fraction_at_primary']:.3f}",
                f"{s['full_score']:.3f}",
                _percent(s["stage1_share_at_primary"]),
                f"{s['max_wrong_rate']:.3f}",
                f"{s['coverage']:.4f}",
            )
        )
    table = _table(
        (
            "Model",
            "Developer",
            "Full score",
            "Mean pass@1",
            "Neither 0 nor 100",
            "Decided at stage 1",
            "Highest wrong rate",
            "Coverage",
            "Cost",
            "Secondary full score",
            "Secondary decided",
            "Secondary wrong rate",
            "Secondary coverage",
        ),
        rows,
        text=2,
    )
    return (
        "## Results for each model\n\n"
        "The full score is the share of the mapped questions that pass under the grade rule. "
        'The mean pass@1 is on the scale 0 to 100, for the same questions. "Neither 0 nor 100" '
        "counts the results with another value. The decided share and the cost are at the "
        f"primary threshold {doc['primary_threshold']}. The highest wrong rate is the worst of "
        "the thresholds. The secondary columns use the secondary grade rule.\n\n"
        f"{table}"
    )


def _secondary_section(doc: Mapping[str, Any]) -> str:
    second = doc["grade_rules"][SECONDARY]
    outside = second["results_outside_limits"]
    probe = second["probes"][STRATIFIED]["primary_threshold"]
    zone = doc["grade_rules"][PRIMARY]["wrong_outside_indifference_zone"]
    grade = (
        f"Under the secondary grade rule (pass@1 of {second['min_pass_at_1']:g}), "
        f"{outside['wrong_decision_rate']} cells are above the wrong-rate limit and "
        f"{outside['coverage']} models are below the coverage limit. At the primary threshold, "
        f"the probe made {_percent(probe['stage1_share'])} of the decisions, with "
        f"{probe['wrong']:,} wrong decisions, at {probe['mean_cost_fraction']['mean']:.3f} of "
        "the cost of a full run. These values have no pass or fail mark."
    )
    zones = (
        f"The indifference zone of the primary result is {zone['primary']['zone']:g}, so every "
        f"wrong decision counts: {zone['primary']['wrong']:,} across all thresholds. With the "
        f"secondary zone of {zone['secondary']['zone']:g}, a wrong decision counts only when the "
        "full-set score is that distance or more from the threshold: "
        f"{zone['secondary']['wrong']:,} wrong decisions stay."
    )
    rows = [
        (
            BENCHMARKS[r["benchmark"]].title,
            r["model"],
            f"{r['threshold']:.2f}",
            f"{r['full_score']:.3f}",
            r["truth"],
            f"{r['stage1_go']} / {r['stage1_no_go']} / {r['escalate']}",
            f"{r['wrong']} of {r['decisions']}",
            f"{r['mean_questions']:.1f}",
            f"{r['mean_cost_fraction']:.3f}",
        )
        for r in doc["reference_holdout"]
    ]
    table = _table(
        (
            "Benchmark",
            "Held-out model",
            "Threshold",
            "Full score",
            "Truth",
            "GO / NO GO / ESCALATE",
            "Wrong",
            "Mean questions",
            "Cost, tokens",
        ),
        rows,
        text=2,
    )
    limits = "\n".join(f"- {item}" for item in HOLD_OUT_LIMITS)
    return (
        f"## Secondary results\n\n### Secondary grade rule\n\n{grade}\n\n"
        f"### Indifference zone\n\n{zones}\n\n"
        "### The 3 reference models\n\n"
        "The replay holds out each saved model in turn. The LiveCodeBench strata come from the "
        "other two models. The AA-LCR strata come from the question metadata. Each "
        "model gets one decision for each seed of the policy section, at the "
        "primary threshold of the benchmark.\n\n"
        f"{table}\n\nLimits of this replay:\n\n{limits}"
    )


def _limits_section(doc: Mapping[str, Any]) -> str:
    limits = "\n".join(f"- {item.format_map(doc)}" for item in LIMITS)
    disclosures = "\n".join(
        f'{n}. Policy text: "{d["policy_text"]}"\n   Note: {d["note"]}'
        for n, d in enumerate(doc["disclosures"].values(), start=1)
    )
    return (
        f"## Limits\n\n{limits}\n\n## Disclosures\n\n"
        "The policy text is a quote from the frozen file. The notes belong to this report, and "
        f"they do not change the policy.\n\n{disclosures}"
    )


def _provenance_section(run: ReplayRun) -> str:
    panel = run.protocol["public_panel"]
    rerun = (
        "git HEAD and the start marker recorded no earlier replay of this policy."
        if run.provenance.rerun_reason is None
        else f"The caller gave a reason for a second replay: {run.provenance.rerun_reason}"
    )
    inputs = "\n".join(f"- `{name}`: `{sha}`" for name, sha in run.provenance.inputs.items())
    return (
        "## Provenance\n\n"
        f"- Policy: `{run.loaded.key}`, SHA-256 `{run.loaded.sha256}`.\n"
        f"- Command: `{run.provenance.command}`.\n"
        f"- Commit: `{run.provenance.commit}`.\n"
        f"- {rerun}\n"
        f"- Source of the public grades: LiveCodeBench, <{panel['url']}>, SHA-256 "
        f"`{panel['sha256']}`. The source states no license, so the raw file is not in the "
        "repository. The outputs hold derived values for each model only.\n\n"
        f"Input hashes (SHA-256):\n\n{inputs}\n\n"
        "The output hashes are in `manifest.json`.\n"
    )


def markdown_report(run: ReplayRun, doc: Mapping[str, Any]) -> bytes:
    intro = (
        f"# Real replay of frozen policy {run.loaded.version}\n\n"
        f"This is the preregistered test of policy `{run.loaded.key}` (issue #63). The targets "
        f"are {doc['models']} public LiveCodeBench models from {doc['developer_groups']} "
        "developer groups. None of them is in the 3-model reference panel that gives the strata. "
        f"Each model gets {doc['seeds']:,} decisions at each of {len(run.settings.thresholds)} "
        f"thresholds from {run.settings.thresholds[0]} to {run.settings.thresholds[-1]}. "
        f"{run.protocol['grade_rule']['statement']}"
    )
    parts = (
        intro,
        result_section(doc),
        _comparison_section(doc),
        _distance_section(doc),
        _model_section(doc),
        _secondary_section(doc),
        _limits_section(doc),
        _provenance_section(run),
    )
    return "\n\n".join(parts).encode("utf-8")


def build_outputs(run: ReplayRun) -> dict[str, bytes]:
    """All output files, with the manifest hashing the others."""
    doc = summary_document(run)
    outputs = {
        "cells.csv": _cells_table(run),
        "coverage.csv": _coverage_table(run),
        "models.csv": _models_table(doc["model_results"]),
        "reference_holdout.csv": _hold_out_table(run),
        "summary.json": encode_json(doc),
        "report.md": markdown_report(run, doc),
    }
    code_root = Path(__file__).parent
    manifest = {
        "schema_version": 1,
        "command": "threshold-decision --real-grades",
        "command_line": run.provenance.command,
        "commit": run.provenance.commit,
        "rerun_reason": run.provenance.rerun_reason,
        "analysis_version": ANALYSIS_VERSION,
        "mode": "real",
        "real_grades_used": True,
        "policy": {
            "file": run.loaded.file_name,
            "key": run.loaded.key,
            "sha256": run.loaded.sha256,
            "frozen": run.loaded.frozen,
        },
        "inputs": dict(run.provenance.inputs),
        "public_source": {
            "url": run.protocol["public_panel"]["url"],
            "sha256": run.protocol["public_panel"]["sha256"],
            "committed": False,
        },
        "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
        "implementation_sha256": {
            name: hashlib.sha256(
                (code_root / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for name in IMPLEMENTATION_FILES
        },
        "output_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
        "counts": {
            "models": len(run.raw),
            "thresholds": len(run.settings.thresholds),
            "seeds": len(run.settings.seeds),
            "cells": sum(len(rule.cells) for rule in run.rules.values()),
            "decisions": sum(c.draws for rule in run.rules.values() for c in rule.cells),
            "coverage_subsets_per_model": run.settings.coverage_subsets,
            "reference_holdout_decisions": len(run.hold_out),
        },
    }
    outputs["manifest.json"] = encode_json(manifest)
    return outputs
