"""The recorded outputs of the reference-panel study: tables, summary, report, and manifest.

The outputs hold derived values for each model. No output holds a public grade
of one question. The report applies the pass criteria of the policy to each arm
and states each failure plainly. It also states where the random probe is equal
to the stratified probe or better.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.threshold_panel_study import Arm, StrataRow, Variant
from benchmark_reference.threshold_policy import LoadedPolicy
from benchmark_reference.threshold_replay import (
    PRIMARY,
    RANDOM,
    STRATIFIED,
    CoverageResult,
    ReplayCell,
    ReplaySettings,
    RuleResults,
    at_threshold,
    criteria_marks,
    decided_share,
    distance_ranges,
    mean_cost_fraction,
    wrong_outside_zone,
)
from benchmark_reference.threshold_replay_record import ReplayRecord
from benchmark_reference.threshold_replay_report import (
    CRITERION_TITLES,
    DISCLOSURE_NOTES,
    DISTANCE_EDGES,
    Provenance,
    distance_record,
    mark_record,
)
from benchmark_reference.threshold_replay_report import (
    IMPLEMENTATION_FILES as REPLAY_IMPLEMENTATION_FILES,
)
from benchmark_reference.threshold_tables import (
    csv_table,
    markdown_table,
    optional,
    percent,
    rounded,
)

ANALYSIS_VERSION = "threshold-panel-study-v1"
OUTPUT_NAMES = (
    "cells.csv",
    "coverage.csv",
    "models.csv",
    "strata.csv",
    "distance.csv",
    "summary.json",
    "report.md",
    "manifest.json",
)
IMPLEMENTATION_FILES = (
    *REPLAY_IMPLEMENTATION_FILES,
    "threshold_replay_record.py",
    "threshold_panel_study.py",
    "threshold_panel_study_report.py",
    "threshold_panel_study_run.py",
    "threshold_panel_study_cli.py",
)
PUBLIC_PANEL = "public_panel"
THREE_MODEL = "three_model"
PROBE_TITLES = {
    THREE_MODEL: "3-model strata (#63)",
    PUBLIC_PANEL: "public-panel strata",
    RANDOM: "random probe",
}
SCOPES = ("primary_threshold", "all_thresholds")
# The edges of distance.csv. They set the layout of that file only.
FINE_EDGES = tuple(f"{k / 100:.2f}" for k in range(100))
LIMITS = (
    "The {models} models come from {developer_groups} developer groups, and they are not "
    "independent. Some models are the same base model at different reasoning settings. A "
    "developer group is also no proof of independence: a model can start from a base model or "
    "from outputs of another developer.",
    "The {seeds:,} decisions of one model at one threshold reuse the same grades. They measure "
    "the question selection only. They do not measure a new answer from the model.",
    "Policy v1 fixed the developer groups, the group counts, the probe sizes, the grade rules, the "
    "thresholds, and the seeds. Nobody had computed a score or a decision of a public model then. "
    "The authors knew the result of #63 on the same models before they wrote the code of this "
    "study.",
    "The policy leaves two points open, and this code chooses them. The first point is the split "
    "of questions with the same reference pass rate. This code splits them by question index: the "
    "panel index for the mapped questions, and the position in identifier order for the full "
    "question set. The second point is the grade rule of the references. This code uses one rule "
    "for the references and for the targets. Neither choice uses a grade of a target.",
    "The public-panel strata differ from the 3-model strata in more than the number of models. "
    "The public grades of the references come from the same harness as the grades of the targets. "
    "The 3-model strata come from the EvalScope grades, and they have unequal sizes.",
    "The stratified probe uses the {interval_method} interval. The random probe uses the "
    "{baseline_method} interval, as policy v1 fixes. A difference between the two probes is "
    "therefore a difference of the questions and of the interval together.",
    "The full question set holds the mapped questions. The two arms are therefore not independent. "
    "They also differ in the probe size, the questions, and the full score of each model.",
    "The thresholds reuse the same models and probes, so the cells of one model are not "
    "independent.",
    "The strata use the grades of other public models on every question. A new benchmark has no "
    "such grades before someone runs a panel of models on it.",
)


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Every result of one arm.

    The first of the ``variants`` is the main result: the primary grade rule with the
    policy group count. The other variants are secondary results. ``random`` holds the
    random-probe cells of each grade rule. ``recorded`` holds the recorded #63 results,
    or None for another question set.
    """

    arm: Arm
    variants: Mapping[Variant, tuple[RuleResults, tuple[StrataRow, ...]]]
    random: Mapping[str, tuple[ReplayCell, ...]]
    recorded: Mapping[str, RuleResults] | None

    @property
    def main(self) -> RuleResults:
        return next(iter(self.variants.values()))[0]

    @property
    def probes(self) -> dict[str, tuple[Sequence[ReplayCell], Sequence[CoverageResult]]]:
        """The cells and the coverage of each probe, under the primary grade rule."""
        found: dict[str, tuple[Sequence[ReplayCell], Sequence[CoverageResult]]] = {}
        if self.recorded is not None:
            primary = self.recorded[PRIMARY]
            found[THREE_MODEL] = (primary.of(STRATIFIED), primary.coverage)
        found[PUBLIC_PANEL] = (self.main.of(STRATIFIED), self.main.coverage)
        found[RANDOM] = (self.random[PRIMARY], ())
        return found


@dataclass(frozen=True, slots=True)
class PanelStudyRun:
    """Everything that the outputs need. ``arms`` maps each arm name to its result."""

    loaded: LoadedPolicy
    settings: ReplaySettings
    arms: Mapping[str, ArmResult]
    record: ReplayRecord
    provenance: Provenance

    @property
    def protocol(self) -> Mapping[str, Any]:
        assert self.loaded.protocol is not None
        return self.loaded.protocol

    @property
    def study(self) -> Mapping[str, Any]:
        study: Mapping[str, Any] = self.protocol["reference_panel_study"]
        return study

    @property
    def developers(self) -> dict[str, str]:
        groups = self.study["developer_groups"]
        return {model: group for group, models in groups.items() for model in models}


# The tables.


def _cells_table(run: PanelStudyRun) -> bytes:
    columns = (
        "arm",
        "grade_rule",
        "groups",
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
        "expected_question_fraction",
        "expected_tokens_mean",
        "coverage",
    )
    rows: list[tuple[object, ...]] = []

    def add(
        result: ArmResult,
        rule: str,
        groups: int | str,
        probe: str,
        cells: Sequence[ReplayCell],
        coverage: Mapping[str, CoverageResult],
    ) -> None:
        for c in cells:
            rows.append(
                (
                    result.arm.name,
                    rule,
                    groups,
                    probe,
                    c.model,
                    c.threshold,
                    c.full_passes,
                    rounded(c.score),
                    c.truth,
                    c.draws,
                    c.go,
                    c.no_go,
                    c.escalated,
                    c.wrong,
                    rounded(c.wrong_rate),
                    rounded(c.decided_share),
                    rounded(c.questions, 3),
                    rounded(c.questions / c.population),
                    rounded(c.tokens.mean, 1) if result.arm.token_costs else "",
                    rounded(coverage[c.model].coverage) if coverage else "",
                )
            )

    for result in run.arms.values():
        for variant, (results, _) in result.variants.items():
            coverage = {r.model: r for r in results.coverage}
            add(result, variant.rule, variant.groups, PUBLIC_PANEL, results.cells, coverage)
        for rule, cells in result.random.items():
            add(result, rule, "", RANDOM, cells, {})
    return csv_table(columns, rows)


def _coverage_table(run: PanelStudyRun) -> bytes:
    columns = (
        "arm",
        "grade_rule",
        "groups",
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
            result.arm.name,
            variant.rule,
            variant.groups,
            r.model,
            r.subsets,
            r.covered,
            rounded(r.coverage),
            r.truth_below,
            r.truth_above,
            rounded(r.mean_width),
        )
        for result in run.arms.values()
        for variant, (results, _) in result.variants.items()
        for r in results.coverage
    ]
    return csv_table(columns, rows)


def _strata_table(run: PanelStudyRun) -> bytes:
    columns = (
        "arm",
        "grade_rule",
        "groups",
        "target_developer",
        "stratum",
        "questions",
        "reference_models",
        "fewest_reference_passes",
        "most_reference_passes",
    )
    rows = [
        (
            result.arm.name,
            variant.rule,
            variant.groups,
            row.developer,
            row.stratum,
            row.questions,
            row.references,
            row.fewest,
            row.most,
        )
        for result in run.arms.values()
        for variant, (_, strata) in result.variants.items()
        for row in strata
    ]
    return csv_table(columns, rows)


def _distance_table(run: PanelStudyRun) -> bytes:
    columns = (
        "arm",
        "probe",
        "side",
        "distance_from",
        "distance_below",
        "cells",
        "decisions",
        "stage1_decisions",
        "stage1_share",
        "wrong",
    )
    sides: tuple[tuple[str, Callable[[ReplayCell], bool]], ...] = (
        ("below", lambda cell: cell.distance < 0),
        ("at_or_above", lambda cell: cell.distance >= 0),
    )
    rows: list[tuple[object, ...]] = []
    for result in run.arms.values():
        for probe, (cells, _) in result.probes.items():
            for side, member in sides:
                for low, high, members in distance_ranges(
                    [c for c in cells if member(c)], FINE_EDGES
                ):
                    if not members:
                        continue
                    rows.append(
                        (
                            result.arm.name,
                            probe,
                            side,
                            f"{float(low):.2f}",
                            "" if high is None else f"{float(high):.2f}",
                            len(members),
                            sum(c.draws for c in members),
                            sum(c.decided for c in members),
                            rounded(decided_share(members)),
                            sum(c.wrong for c in members),
                        )
                    )
    return csv_table(columns, rows)


def _probe_record(
    run: PanelStudyRun, cells: Sequence[ReplayCell], model: str
) -> dict[str, float | int | None]:
    mine = [c for c in cells if c.model == model]
    at = at_threshold(mine, run.settings.primary_threshold)[0]
    return {
        "stage1_share_at_primary": rounded(at.decided_share),
        "wrong_at_primary": at.wrong,
        "question_fraction_at_primary": rounded(at.questions / at.population),
        "stage1_share_all_thresholds": rounded(decided_share(mine)),
        "max_wrong_rate": rounded(max(c.wrong_rate for c in mine)),
    }


def model_records(run: PanelStudyRun) -> list[dict[str, Any]]:
    """One record for each public model and arm, in arm and model order."""
    developers = run.developers
    records = []
    for result in run.arms.values():
        strata = next(iter(result.variants.values()))[1]
        references = {row.developer: row.references for row in strata}
        for model in sorted(result.arm.raw):
            first = next(c for c in result.main.cells if c.model == model)
            coverage = next(r for r in result.main.coverage if r.model == model)
            records.append(
                {
                    "arm": result.arm.name,
                    "model": model,
                    "developer": developers[model],
                    "reference_models": references[developers[model]],
                    "full_passes": first.full_passes,
                    "full_score": rounded(first.score),
                    "coverage": rounded(coverage.coverage),
                    "probes": {
                        probe: _probe_record(run, cells, model)
                        for probe, (cells, _) in result.probes.items()
                    },
                }
            )
    return records


def _models_table(records: Sequence[Mapping[str, Any]]) -> bytes:
    head = ("arm", "model", "developer", "reference_models", "full_passes", "full_score")
    fields = tuple(records[0]["probes"][PUBLIC_PANEL])
    columns = (
        *head,
        "coverage",
        *(f"{probe}_{field}" for probe in PROBE_TITLES for field in fields),
    )
    rows = [
        (
            *(r[h] for h in head),
            r["coverage"],
            *(r["probes"].get(probe, {}).get(f, "") for probe in PROBE_TITLES for f in fields),
        )
        for r in records
    ]
    return csv_table(columns, rows)


# The summary.


def _probe_summary(
    run: PanelStudyRun,
    result: ArmResult,
    cells: Sequence[ReplayCell],
    coverage: Sequence[CoverageResult],
) -> dict[str, Any]:
    """The results of one probe at the primary threshold and at all thresholds."""

    def part(members: Sequence[ReplayCell]) -> dict[str, Any]:
        fractions = [c.questions / c.population for c in members]
        return {
            "cells": len(members),
            "decisions": sum(c.draws for c in members),
            "go": sum(c.go for c in members),
            "no_go": sum(c.no_go for c in members),
            "escalate": sum(c.escalated for c in members),
            "stage1_share": rounded(decided_share(members)),
            "wrong": sum(c.wrong for c in members),
            "max_wrong_rate": rounded(max(c.wrong_rate for c in members)),
            "mean_question_fraction": rounded(sum(fractions, Fraction(0)) / len(fractions)),
            "mean_token_fraction": rounded(mean_cost_fraction(members, result.arm.costs).mean)
            if result.arm.token_costs
            else None,
        }

    widths = [r.mean_width for r in coverage]
    return {
        "primary_threshold": part(at_threshold(cells, run.settings.primary_threshold)),
        "all_thresholds": part(cells),
        "min_coverage": rounded(min(r.coverage for r in coverage)) if coverage else None,
        "mean_interval_width": rounded(sum(widths) / len(widths)) if widths else None,
        "d95": distance_record(cells),
        "d95_at_primary": distance_record(at_threshold(cells, run.settings.primary_threshold)),
    }


def _verdict(random: Fraction | int, other: Fraction | int, *, more_is_better: bool) -> str:
    """How the random probe compares with the other probe on one measure."""
    if random == other:
        return "equal"
    return "better" if (random > other) == more_is_better else "worse"


def random_comparisons(
    probes: Mapping[str, Sequence[ReplayCell]], primary_threshold: str
) -> list[dict[str, Any]]:
    """The random probe against each stratified probe: decided share and wrong decisions."""
    records = []
    for scope in SCOPES:

        def members(cells: Sequence[ReplayCell], scope: str = scope) -> Sequence[ReplayCell]:
            return cells if scope == "all_thresholds" else at_threshold(cells, primary_threshold)

        random = members(probes[RANDOM])
        for probe in probes:
            if probe == RANDOM:
                continue
            other = members(probes[probe])
            share, other_share = decided_share(random), decided_share(other)
            wrong, other_wrong = sum(c.wrong for c in random), sum(c.wrong for c in other)
            records.append(
                {
                    "scope": scope,
                    "against": probe,
                    "random_stage1_share": rounded(share),
                    "other_stage1_share": rounded(other_share),
                    "stage1_share_verdict": _verdict(share, other_share, more_is_better=True),
                    "random_wrong": wrong,
                    "other_wrong": other_wrong,
                    "decisions": sum(c.draws for c in random),
                    "wrong_verdict": _verdict(wrong, other_wrong, more_is_better=False),
                }
            )
    return records


def _distance_rows(result: ArmResult) -> dict[str, list[dict[str, Any]]]:
    return {
        probe: [
            {
                "from": float(low),
                "below": rounded(high),
                "cells": len(members),
                "stage1_share": rounded(decided_share(members)) if members else None,
                "wrong": sum(c.wrong for c in members),
                "decisions": sum(c.draws for c in members),
            }
            for low, high, members in distance_ranges(cells, DISTANCE_EDGES)
        ]
        for probe, (cells, _) in result.probes.items()
    }


def _same_decisions(one: Sequence[ReplayCell], two: Sequence[ReplayCell]) -> bool:
    def facts(cells: Sequence[ReplayCell]) -> set[tuple[object, ...]]:
        return {
            (c.model, c.threshold, c.full_passes, c.draws, c.go, c.no_go, c.escalated)
            for c in cells
        }

    return len(one) == len(two) and facts(one) == facts(two)


def _arm_document(run: PanelStudyRun, result: ArmResult) -> dict[str, Any]:
    protocol, arm = run.protocol, result.arm
    replay = protocol["unseen_model_replay"]
    marks = criteria_marks(result.main, protocol, run.settings, arm.costs)
    zone = protocol["decision"]["indifference_zone"]
    variants = []
    for variant, (results, _) in result.variants.items():
        limits = criteria_marks(results, protocol, run.settings, arm.costs)
        variants.append(
            {
                "grade_rule": variant.rule,
                "min_pass_at_1": variant.minimum,
                "groups": variant.groups,
                "results_outside_limits": {key: mark.failed for key, mark in limits.items()},
                **_probe_summary(run, result, results.cells, results.coverage),
                "random": _probe_summary(run, result, result.random[variant.rule], ()),
                "random_comparisons": random_comparisons(
                    {PUBLIC_PANEL: results.cells, RANDOM: result.random[variant.rule]},
                    run.settings.primary_threshold,
                ),
            }
        )
    document: dict[str, Any] = {
        "questions": arm.questions,
        "stage1_size": arm.policy.stage1_size,
        "cost_unit": "tokens" if arm.token_costs else "questions",
        "criteria": {
            key: mark_record(mark, replay["pass_criteria"][key]["statement"])
            for key, mark in marks.items()
        },
        "all_criteria_pass": all(mark.passed for mark in marks.values()),
        "probes": {
            probe: _probe_summary(run, result, cells, coverage)
            for probe, (cells, coverage) in result.probes.items()
        },
        "random_comparisons": random_comparisons(
            {probe: cells for probe, (cells, _) in result.probes.items()},
            run.settings.primary_threshold,
        ),
        "by_distance": _distance_rows(result),
        "wrong_outside_indifference_zone": {
            kind: {
                "zone": value,
                "wrong": wrong_outside_zone(result.main.cells, Fraction(str(value))),
            }
            for kind, value in zone.items()
        },
        "variants": variants,
    }
    if result.recorded is not None:
        document["random_probe_equals_record"] = all(
            _same_decisions(cells, result.recorded[rule].of(RANDOM))
            for rule, cells in result.random.items()
        )
    return document


def summary_document(run: PanelStudyRun) -> dict[str, Any]:
    """Every number of the report."""
    protocol, study = run.protocol, run.study
    section = run.loaded.benchmarks[protocol["unseen_model_replay"]["benchmark"]]
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
        "coverage_subsets": run.settings.coverage_subsets,
        "models": len(run.developers),
        "developer_groups": len(study["developer_groups"]),
        "groups": study["groups"],
        "secondary_groups": study["secondary_groups"],
        "interval_method": section.interval_method,
        "baseline_method": run.settings.baseline_method,
        "simulated_d95": protocol["unseen_model_replay"]["stated_comparisons"][
            "real_vs_simulated_d95"
        ]["simulated"],
        "arms": {name: _arm_document(run, result) for name, result in run.arms.items()},
        "model_results": model_records(run),
        "replay_record_manifest_sha256": run.record.manifest_sha256,
        "disclosures": {
            key: {"policy_text": protocol["disclosures"][key], "note": note}
            for key, note in DISCLOSURE_NOTES.items()
        },
        "rerun_reason": run.provenance.rerun_reason,
    }


# The report.


def _scope_title(doc: Mapping[str, Any], scope: str) -> str:
    return (
        f"Threshold {doc['primary_threshold']}"
        if scope == "primary_threshold"
        else "All thresholds"
    )


def verdict_text(arm: Mapping[str, Any]) -> str:
    """The verdict of one arm in one or two sentences."""
    criteria, name = arm["criteria"], f"{arm['questions']:,}"
    failed = [title for key, title in CRITERION_TITLES.items() if not criteria[key]["passed"]]
    if failed:
        return (
            f"**The {name}-question arm failed {len(failed)} of {len(criteria)} pass criteria: "
            f"{', '.join(failed)}.** The recorded result of #63 does not change."
        )
    return f"**The {name}-question arm passed all {len(criteria)} pass criteria of the policy.**"


def _result_section(doc: Mapping[str, Any]) -> str:
    parts = ["## Result"]
    rows = []
    for arm in doc["arms"].values():
        probe = arm["probes"][PUBLIC_PANEL]
        at, every = probe["primary_threshold"], probe["all_thresholds"]
        parts.append(
            f"{verdict_text(arm)} At the primary threshold {doc['primary_threshold']}, a "
            f"probe of {arm['stage1_size']} of {arm['questions']:,} questions made "
            f"{percent(at['stage1_share'])} of {at['decisions']:,} decisions. Wrong decisions: "
            f"{at['wrong']:,}. The mean expected cost was "
            f"{at['mean_question_fraction']:.3f} of the questions. Across all thresholds, the "
            f"probe made {percent(every['stage1_share'])} of {every['decisions']:,} decisions. "
            f"Wrong decisions: {every['wrong']:,}. The mean expected cost was "
            f"{every['mean_question_fraction']:.3f} of the questions."
        )
        for key, c in arm["criteria"].items():
            one_mean = key == "mean_cost_at_primary_threshold"
            rows.append(
                (
                    f"{arm['questions']:,} questions",
                    CRITERION_TITLES[key],
                    c["statement"],
                    f"{c['value']:.4f}",
                    f"{c['limit']:g}",
                    "one mean" if one_mean else f"{c['failed']} of {c['checked']}",
                    "PASS" if c["passed"] else "FAIL",
                )
            )
    table = markdown_table(
        (
            "Arm",
            "Criterion",
            "Rule",
            "Worst or mean value",
            "Limit",
            "Outside the limit",
            "Mark",
        ),
        rows,
        text=3,
    )
    units = " ".join(
        f"The cost value of the {arm['questions']:,}-question arm is "
        + (
            "the mean token estimate from the saved answers of the 3 reference models, as in #63."
            if arm["cost_unit"] == "tokens"
            else "in questions. The public file has no token counts, so this arm has no token cost."
        )
        for arm in doc["arms"].values()
    )
    note = (
        f"The marks use {doc['groups']} groups and the primary grade rule. {units} A cost in "
        "questions and a cost in tokens give the same mark, because both are 1.0 only when every "
        "decision escalates."
    )
    return "\n\n".join([*parts, table, note])


def _probe_rows(doc: Mapping[str, Any], arm: Mapping[str, Any]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for scope in SCOPES:
        for probe, p in arm["probes"].items():
            s = p[scope]
            row: list[object] = [
                _scope_title(doc, scope),
                PROBE_TITLES[probe],
                f"{s['go']:,} / {s['no_go']:,} / {s['escalate']:,}",
                percent(s["stage1_share"]),
                f"{s['wrong']:,} of {s['decisions']:,}",
                f"{s['max_wrong_rate']:.4f}",
                f"{s['mean_question_fraction']:.3f}",
            ]
            if arm["cost_unit"] == "tokens":
                row.append(f"{s['mean_token_fraction']:.3f}")
            rows.append(
                (
                    *row,
                    "not measured" if p["min_coverage"] is None else f"{p['min_coverage']:.4f}",
                    "not measured"
                    if p["mean_interval_width"] is None
                    else f"{p['mean_interval_width']:.4f}",
                )
            )
    return rows


def _probe_table(doc: Mapping[str, Any], arm: Mapping[str, Any]) -> str:
    cost = ["Cost, questions"]
    if arm["cost_unit"] == "tokens":
        cost.append("Cost, tokens")
    return markdown_table(
        (
            "Scope",
            "Probe",
            "GO / NO GO / ESCALATE",
            "Decided at stage 1",
            "Wrong",
            "Highest wrong rate",
            *cost,
            "Lowest coverage",
            "Mean interval width",
        ),
        _probe_rows(doc, arm),
        text=2,
    )


def _random_better(comparison: Mapping[str, Any]) -> list[str]:
    """The measures on which the random probe is equal or better."""
    measures = (
        ("decided share", "stage1_share_verdict"),
        ("wrong decisions", "wrong_verdict"),
    )
    return [measure for measure, key in measures if comparison[key] != "worse"]


def _random_flag(better: Sequence[str]) -> str:
    if not better:
        return "The random probe is worse on both measures."
    return f"**The random probe is equal or better on {' and '.join(better)}.**"


def _range_title(row: Mapping[str, Any]) -> str:
    if row["below"] is None:
        return f"{row['from']:.2f} or more"
    return f"{row['from']:.2f} to below {row['below']:.2f}"


def random_text(doc: Mapping[str, Any], arm: Mapping[str, Any]) -> str:
    """Say where the random probe is equal to a stratified probe or better."""
    verbs = {"better": "more", "equal": "the same share", "worse": "fewer"}
    words = {"better": "fewer wrong decisions", "equal": "the same number", "worse": "more"}
    lines = []
    for c in arm["random_comparisons"]:
        title = PROBE_TITLES[c["against"]]
        flag = _random_flag(_random_better(c))
        lines.append(
            f"- {_scope_title(doc, c['scope'])}, against the {title}: the random probe decides "
            f"{percent(c['random_stage1_share'])} at stage 1, against "
            f"{percent(c['other_stage1_share'])} ({verbs[c['stage1_share_verdict']]}). It makes "
            f"{c['random_wrong']:,} wrong decisions of {c['decisions']:,}, against "
            f"{c['other_wrong']:,} ({words[c['wrong_verdict']]}). {flag}"
        )
    return "\n".join(lines)


def random_distance_text(arm: Mapping[str, Any]) -> str:
    """Name the distance ranges in which the random probe decides as much or more."""
    rows = arm["by_distance"]
    lines = []
    for probe in rows:
        if probe == RANDOM:
            continue
        found = [
            _range_title(other)
            for random, other in zip(rows[RANDOM], rows[probe], strict=True)
            if random["cells"]
            and other["cells"]
            and random["stage1_share"] >= other["stage1_share"]
        ]
        lines.append(
            f"- {arm['questions']:,} questions, against the {PROBE_TITLES[probe]}: "
            + (f"{', '.join(found)}." if found else "no range.")
        )
    return "\n".join(lines)


def variant_text(doc: Mapping[str, Any], arm: Mapping[str, Any]) -> str:
    """Say where the random probe is equal to a secondary variant or better."""
    lines = []
    for v in arm["variants"][1:]:
        for c in v["random_comparisons"]:
            better = _random_better(c)
            lines.append(
                f"- {arm['questions']:,} questions, {v['grade_rule']} grade rule, "
                f"{v['groups']} groups, {_scope_title(doc, c['scope']).lower()}: the random probe "
                f"decides {percent(c['random_stage1_share'])} against "
                f"{percent(c['other_stage1_share'])}, with {c['random_wrong']:,} wrong decisions "
                f"against {c['other_wrong']:,}. {_random_flag(better)}"
            )
    return "\n".join(lines)


def _points(value: float) -> str:
    size = f"{abs(100 * value):.1f}"
    if size == "0.0":
        return "the same to 0.1 percentage points"
    return f"{size} percentage points {'higher' if value > 0 else 'lower'}"


def panel_text(doc: Mapping[str, Any], arm: Mapping[str, Any]) -> str:
    """What the larger reference panel changes against the 3-model strata."""
    lines = []
    for scope in SCOPES:
        old, new = arm["probes"][THREE_MODEL][scope], arm["probes"][PUBLIC_PANEL][scope]
        lines.append(
            f"- {_scope_title(doc, scope)}: with the public-panel strata, the share decided at "
            f"stage 1 is {_points(new['stage1_share'] - old['stage1_share'])} "
            f"({percent(new['stage1_share'])} against {percent(old['stage1_share'])}). Wrong "
            f"decisions: {new['wrong']:,} against {old['wrong']:,} of {new['decisions']:,}. Mean "
            f"cost in questions: {new['mean_question_fraction']:.3f} against "
            f"{old['mean_question_fraction']:.3f}."
        )
    return "\n".join(lines)


def _arm_sections(doc: Mapping[str, Any]) -> str:
    parts = []
    for arm in doc["arms"].values():
        head = f"## The {arm['questions']:,}-question arm"
        if THREE_MODEL in arm["probes"]:
            if arm["random_probe_equals_record"]:
                same = (
                    "The random probe makes the decisions of the recorded random probe again, for "
                    "each model, threshold, and grade rule. The two runs therefore used the same "
                    "targets and the same questions."
                )
                panel = panel_text(doc, arm)
            else:
                same = (
                    "**The random probe does not make the decisions of the recorded random probe "
                    "again. The 3-model result is not comparable with the other results.**"
                )
                panel = "The report makes no comparison, because the results are not comparable."
            parts.append(
                f"{head}\n\nThe table puts three results side by side. The 3-model result is the "
                f"record of #63. This study did not run it again. {same}\n\n"
                f"{_probe_table(doc, arm)}\n\n### The larger reference panel\n\n{panel}\n\n"
                f"### The random probe\n\n{random_text(doc, arm)}"
            )
        else:
            parts.append(
                f"{head}\n\nThis arm uses every public question and a probe of "
                f"{arm['stage1_size']} questions, the stage-1 fraction of the policy. The public "
                "file has no token counts, so the cost of this arm is in questions.\n\n"
                f"{_probe_table(doc, arm)}\n\n"
                f"### The random probe\n\n{random_text(doc, arm)}"
            )
    return "\n\n".join(parts)


def _distance_section(doc: Mapping[str, Any]) -> str:
    arms = doc["arms"]
    columns = [(name, probe) for name, arm in arms.items() for probe in arm["by_distance"]]
    first = next(iter(next(iter(arms.values()))["by_distance"].values()))
    rows: list[tuple[object, ...]] = []
    for k, edge in enumerate(first):
        values: list[object] = [_range_title(edge)]
        for name, arm in arms.items():
            members = [arm["by_distance"][probe][k] for n, probe in columns if n == name]
            values.append(members[0]["cells"])
            values.extend(
                "none" if m["stage1_share"] is None else percent(m["stage1_share"]) for m in members
            )
        rows.append(tuple(values))
    head = ["Distance from the threshold"]
    for name, arm in arms.items():
        head.append(f"{arm['questions']:,}: cells")
        head.extend(
            f"{arm['questions']:,}: {PROBE_TITLES[probe]}" for n, probe in columns if n == name
        )
    primary = f"threshold {doc['primary_threshold']}"
    distances = [(f"Simulated (#60), 315 questions, {primary}", doc["simulated_d95"])]
    for arm in arms.values():
        for probe, p in arm["probes"].items():
            title = f"{arm['questions']:,} questions, {PROBE_TITLES[probe]}"
            distances.append((f"{title}, {primary}", p["d95_at_primary"]))
            distances.append((f"{title}, all thresholds", p["d95"]))
    d95 = markdown_table(
        ("d95", "Below the threshold", "At or above the threshold", "Both sides"),
        [
            (label, optional(d["d95_below"]), optional(d["d95_above"]), optional(d["d95"]))
            for label, d in distances
        ],
    )
    return (
        "## Share decided at stage 1 by distance\n\nThe distance is the distance of the full-set "
        "score from the threshold. The table uses every combination of model and threshold, with "
        f"{doc['groups']} groups and the primary grade rule. A column with a probe name gives the "
        "share decided at stage 1. `distance.csv` gives the same shares in steps of 0.01, for each "
        "side of the threshold. The distance ranges are a layout choice, and no mark uses them.\n\n"
        f"{markdown_table(head, rows)}\n\n"
        "d95 is a distance from the threshold. At d95 and at every larger distance, the probe "
        "makes at least 95% of the decisions. d95 is the smallest such distance. The simulated row "
        "uses the 3-model strata at one threshold. A real row at one threshold has one point for "
        'each model, so it is coarse. The value "none" means that the side has no model, or that '
        f"its farthest model does not reach 95%.\n\n{d95}\n\n"
        "### Where the random probe decides as much or more\n\nEach line names the ranges in which "
        "the share of the random probe is equal or larger.\n\n"
        + "\n".join(random_distance_text(arm) for arm in arms.values())
    )


def _secondary_section(doc: Mapping[str, Any]) -> str:
    rows = []
    for arm in doc["arms"].values():
        for v in arm["variants"]:
            at, every = v["primary_threshold"], v["all_thresholds"]
            random = v["random"]["primary_threshold"]
            rows.append(
                (
                    f"{arm['questions']:,}",
                    v["grade_rule"],
                    v["groups"],
                    percent(at["stage1_share"]),
                    percent(random["stage1_share"]),
                    f"{at['wrong']:,}",
                    f"{random['wrong']:,}",
                    percent(every["stage1_share"]),
                    f"{every['wrong']:,}",
                    f"{every['max_wrong_rate']:.4f}",
                    f"{v['min_coverage']:.4f}",
                    v["results_outside_limits"]["wrong_decision_rate"],
                    v["results_outside_limits"]["coverage"],
                )
            )
    table = markdown_table(
        (
            "Questions",
            "Grade rule",
            "Groups",
            f"Decided at {doc['primary_threshold']}",
            f"Random probe at {doc['primary_threshold']}",
            f"Wrong at {doc['primary_threshold']}",
            f"Random wrong at {doc['primary_threshold']}",
            "Decided, all thresholds",
            "Wrong, all thresholds",
            "Highest wrong rate",
            "Lowest coverage",
            "Cells above the wrong-rate limit",
            "Models below the coverage limit",
        ),
        rows,
        text=2,
    )
    random = "\n".join(variant_text(doc, arm) for arm in doc["arms"].values())
    zones = "\n".join(
        f"- {arm['questions']:,} questions: "
        + ", ".join(
            f"{z['wrong']:,} wrong decisions with a zone of {z['zone']:g}"
            for z in arm["wrong_outside_indifference_zone"].values()
        )
        + "."
        for arm in doc["arms"].values()
    )
    return (
        f"## Secondary results\n\n### {doc['secondary_groups']} groups and the secondary grade "
        "rule\n\nThe first row of each arm is the result above. Each other row changes one value. "
        "The grade rule applies to the reference models and to the targets. The secondary rows "
        f"have no pass or fail mark.\n\n{table}\n\nThe random probe against each secondary row:\n\n"
        f"{random}\n\n### Indifference zone\n\nA wrong decision "
        "counts only when the full-set score is the zone or more from the threshold. The counts "
        f"use the public-panel strata and all thresholds.\n\n{zones}"
    )


def _model_section(doc: Mapping[str, Any]) -> str:
    parts = []
    for name, arm in doc["arms"].items():
        probes = list(arm["probes"])
        mine = [m for m in doc["model_results"] if m["arm"] == name]
        rows = [
            (
                m["model"],
                m["developer"],
                m["reference_models"],
                f"{m['full_score']:.3f}",
                *(percent(m["probes"][p]["stage1_share_at_primary"]) for p in probes),
                f"{m['probes'][PUBLIC_PANEL]['question_fraction_at_primary']:.3f}",
                f"{m['probes'][PUBLIC_PANEL]['max_wrong_rate']:.3f}",
                f"{m['coverage']:.4f}",
            )
            for m in sorted(mine, key=lambda m: (-m["full_score"], m["model"]))
        ]
        head = (
            "Model",
            "Developer",
            "Reference models",
            "Full score",
            *(f"Decided, {PROBE_TITLES[p]}" for p in probes),
            "Cost, questions",
            "Highest wrong rate",
            "Coverage",
        )
        parts.append(f"### {arm['questions']:,} questions\n\n{markdown_table(head, rows, text=2)}")
    return (
        "## Results for each model\n\nThe decided shares and the cost are at the primary threshold "
        f"{doc['primary_threshold']}. The cost, the highest wrong rate of all thresholds, and the "
        "coverage are of the public-panel strata. `cells.csv` gives every threshold.\n\n"
        + "\n\n".join(parts)
    )


def _limits_section(doc: Mapping[str, Any]) -> str:
    limits = "\n".join(f"- {item.format_map(doc)}" for item in LIMITS)
    disclosures = "\n".join(
        f'{n}. Policy text: "{d["policy_text"]}"\n   Note: {d["note"]}'
        for n, d in enumerate(doc["disclosures"].values(), start=1)
    )
    return (
        f"## Limits\n\n{limits}\n\n## Disclosures\n\nThe policy text is a quote from the frozen "
        "file. The notes are the notes of the #63 report, and they do not change the policy.\n\n"
        f"{disclosures}"
    )


def _provenance_section(run: PanelStudyRun) -> str:
    panel = run.protocol["public_panel"]
    rerun = (
        "git HEAD and the start marker recorded no earlier run of this study."
        if run.provenance.rerun_reason is None
        else f"The caller gave this rerun reason: {run.provenance.rerun_reason}"
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


def markdown_report(run: PanelStudyRun, doc: Mapping[str, Any]) -> bytes:
    arms = " and ".join(f"{arm['questions']:,}" for arm in doc["arms"].values())
    intro = (
        f"# Reference-panel study of frozen policy {run.loaded.version}\n\n"
        f"This study (issue #77) runs policy `{run.loaded.key}` with the public models as the "
        f"reference panel, on {arms} LiveCodeBench questions. The targets are the "
        f"{doc['models']} public models from {doc['developer_groups']} developer groups. For each "
        "target, the references are the public models outside the developer group of the target. "
        "The selector reads no grade of the target and no grade of its developer group. The "
        f"strata are the reference pass rate, cut into {doc['groups']} groups of near-equal size. "
        f"Each model gets {doc['seeds']:,} decisions at each of {len(run.settings.thresholds)} "
        f"thresholds from {run.settings.thresholds[0]} to {run.settings.thresholds[-1]}, and "
        f"{doc['coverage_subsets']:,} new subsets for the coverage check. "
        f"{run.protocol['grade_rule']['statement']}"
    )
    parts = (
        intro,
        _result_section(doc),
        _arm_sections(doc),
        _distance_section(doc),
        _secondary_section(doc),
        _model_section(doc),
        _limits_section(doc),
        _provenance_section(run),
    )
    return "\n\n".join(parts).encode("utf-8")


def build_outputs(run: PanelStudyRun) -> dict[str, bytes]:
    """All output files, with the manifest hashing the others."""
    doc = summary_document(run)
    outputs = {
        "cells.csv": _cells_table(run),
        "coverage.csv": _coverage_table(run),
        "models.csv": _models_table(doc["model_results"]),
        "strata.csv": _strata_table(run),
        "distance.csv": _distance_table(run),
        "summary.json": encode_json(doc),
        "report.md": markdown_report(run, doc),
    }
    code_root = Path(__file__).parent
    cells = [
        c
        for result in run.arms.values()
        for group in (
            *(results.cells for results, _ in result.variants.values()),
            *result.random.values(),
        )
        for c in group
    ]
    manifest = {
        "schema_version": 1,
        "command": "threshold-panel-study",
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
            "models": len(run.developers),
            "thresholds": len(run.settings.thresholds),
            "seeds": len(run.settings.seeds),
            "cells": len(cells),
            "decisions": sum(c.draws for c in cells),
            "coverage_subsets_per_model": run.settings.coverage_subsets,
        },
    }
    outputs["manifest.json"] = encode_json(manifest)
    return outputs
