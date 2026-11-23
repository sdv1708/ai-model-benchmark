"""The "Frozen policy" part of the summary and the HTML report.

For a frozen policy, the report shows each chosen value with the simulated
result that chose it, each fixed value, the pass criteria, the stated
comparisons, and the disclosures. It also re-applies the rules to the coverage
and error-rate results of the current run. Those studies do not depend on the
chosen values, so a run of the frozen policy must give the same choice. The
report says whether it does.
"""

import html
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import BENCHMARKS
from benchmark_reference.threshold_policy import LoadedPolicy, ThresholdPolicy
from benchmark_reference.threshold_rules import (
    REQUIRED_GENERATORS,
    MethodCandidate,
    ProbeCandidate,
    choose_interval_method,
    choose_probe,
    choose_probe_for_generator,
    choose_values,
)

GENERATOR_TITLES = {"rasch": "Rasch", "reference_flip": "reference flip"}
METHOD_TITLES = {
    "pooled_exact_hypergeometric": "Pooled exact",
    "stratified_bonferroni_hypergeometric": "Bonferroni exact",
    "stratified_wilson": "Stratified Wilson",
    "stratified_bootstrap_percentile": "Stratified bootstrap",
}

type Evidence = Mapping[str, tuple[ThresholdPolicy, Mapping[str, Any], Mapping[str, Any]]]


def _methods(record: Mapping[str, Any]) -> list[MethodCandidate]:
    return [
        MethodCandidate(c["method"], c["cells"], c["cells_failed"], float(c["mean_width"]))
        for c in record["interval_method"]["candidates"]
    ]


def _probes(record: Mapping[str, Any]) -> list[ProbeCandidate]:
    return [
        ProbeCandidate(
            c["stratifier"],
            c["stage_size"],
            c["passes_both_generators"],
            dict(c["mean_cost_fraction"]),
        )
        for c in record["probe"]["candidates"]
    ]


def _cost(value: Fraction) -> float:
    return round(float(value), 7)


def _recheck(name: str, evidence: Evidence) -> dict[str, Any]:
    """Re-apply the rules to the coverage and error-rate results of this run."""
    if name not in evidence:
        return {"available": False, "reason": "This run has no such section."}
    policy, coverage, error_rate = evidence[name]
    try:
        again = choose_values(coverage, error_rate, true_scores=policy.error_true_scores)
    except AnalysisError as exc:
        # For example, a short study grid is not the uniform prior of the cost rule.
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "interval_method": again.interval_method,
        "stratifier": again.stratifier,
        "stage1_size": again.stage1_size,
        "matches": (again.interval_method, again.stratifier, again.stage1_size)
        == (policy.interval_method, policy.stratifier, policy.stage1_size),
    }


def _benchmark(name: str, record: Mapping[str, Any], evidence: Evidence) -> dict[str, Any]:
    """The chosen values of one section, the runners-up, and the rule check on this run."""
    methods, probes = _methods(record), _probes(record)
    method = choose_interval_method(methods)
    probe = choose_probe(probes)
    others = [m for m in methods if m.passes and m is not method]
    runner_method = min(others, key=lambda m: Fraction(str(m.mean_width)), default=None)
    narrower = [
        m
        for m in methods
        if not m.passes and Fraction(str(m.mean_width)) < Fraction(str(method.mean_width))
    ]
    passing = [p for p in probes if p.passes_both_generators and p is not probe]
    runner_probe = min(passing, key=lambda p: (p.cost, p.stage_size, p.stratifier), default=None)
    alone = {g: choose_probe_for_generator(probes, g) for g in REQUIRED_GENERATORS}
    by_generator = {
        g: {"stratifier": p.stratifier, "stage_size": p.stage_size} for g, p in alone.items()
    }
    recheck = _recheck(name, evidence)
    return {
        "benchmark": name,
        "title": BENCHMARKS[name].title,
        "interval_method": {
            "chosen": method.method,
            "cells": method.cells,
            "cells_failed": method.cells_failed,
            "mean_width": method.mean_width,
            "next_passing": None
            if runner_method is None
            else {"method": runner_method.method, "mean_width": runner_method.mean_width},
            "narrower_failing": [
                {"method": m.method, "mean_width": m.mean_width, "cells_failed": m.cells_failed}
                for m in narrower
            ],
            "candidates": list(record["interval_method"]["candidates"]),
        },
        "probe": {
            "stratifier": probe.stratifier,
            "stage_size": probe.stage_size,
            "mean_cost_fraction": _cost(probe.cost),
            "mean_cost_fraction_by_generator": {
                g: float(probe.generator_cost(g)) for g in REQUIRED_GENERATORS
            },
            "next_passing": None
            if runner_probe is None
            else {
                "stratifier": runner_probe.stratifier,
                "stage_size": runner_probe.stage_size,
                "mean_cost_fraction": _cost(runner_probe.cost),
            },
            "choice_by_generator": by_generator,
            "same_choice_for_each_generator": all(
                (c["stratifier"], c["stage_size"]) == (probe.stratifier, probe.stage_size)
                for c in by_generator.values()
            ),
            "failing_settings": sum(not p.passes_both_generators for p in probes),
            "candidates": [
                {
                    **c,
                    "mean_cost_fraction_both": _cost(p.cost),
                }
                for c, p in zip(record["probe"]["candidates"], probes, strict=True)
            ],
        },
        "recheck": recheck,
    }


def _reproduced(benchmarks: Sequence[Mapping[str, Any]]) -> bool | None:
    checked = [b["recheck"]["matches"] for b in benchmarks if b["recheck"]["available"]]
    return all(checked) if checked else None


def frozen_document(loaded: LoadedPolicy, evidence: Evidence) -> dict[str, Any] | None:
    """The frozen-policy block of the summary, or None for a policy that is not frozen.

    ``evidence`` maps each benchmark of this run to its policy section, its
    coverage summary, and its error-rate summary.
    """
    if not loaded.frozen or loaded.protocol is None or loaded.selection is None:
        return None
    selection = loaded.selection
    benchmarks = [
        _benchmark(name, selection["benchmarks"][name], evidence) for name in loaded.benchmarks
    ]
    return {
        "key": loaded.key,
        "sha256": loaded.sha256,
        "file": loaded.file_name,
        "rules": dict(selection["rules"]),
        "source": dict(selection["source"]),
        "thresholds": {name: p.threshold for name, p in loaded.benchmarks.items()},
        "benchmarks": benchmarks,
        # None when no section of this run could be checked.
        "rules_reproduced_on_this_run": _reproduced(benchmarks),
        "protocol": dict(loaded.protocol),
    }


def _width(value: float) -> str:
    return f"{value:.3f}"


def _method_title(method: str) -> str:
    return METHOD_TITLES.get(method, method)


def _method_evidence(item: Mapping[str, Any]) -> str:
    chosen = item["interval_method"]
    text = (
        f"Passes {chosen['cells'] - chosen['cells_failed']} of {chosen['cells']} coverage cells "
        f"with mean width {_width(chosen['mean_width'])}, the smallest of the passing methods."
    )
    if chosen["next_passing"]:
        nxt = chosen["next_passing"]
        text += (
            f" Next passing method: {_method_title(nxt['method'])}, {_width(nxt['mean_width'])}."
        )
    for failing in chosen["narrower_failing"]:
        text += (
            f" {_method_title(failing['method'])} is narrower "
            f"({_width(failing['mean_width'])}), but it fails {failing['cells_failed']} cells."
        )
    return text


def _probe_evidence(item: Mapping[str, Any]) -> str:
    probe = item["probe"]
    costs = probe["mean_cost_fraction_by_generator"]
    text = (
        f"Mean expected cost {probe['mean_cost_fraction']:.4f} of a full run "
        f"(Rasch {costs['rasch']:.4f}, reference flip {costs['reference_flip']:.4f}). It "
        "passes the error-rate study for both generators and has the lowest cost of the "
        "passing settings."
    )
    if probe["next_passing"]:
        nxt = probe["next_passing"]
        text += (
            f" Next: {nxt['stratifier']}, {nxt['stage_size']} questions, "
            f"{nxt['mean_cost_fraction']:.4f}."
        )
    if probe["same_choice_for_each_generator"]:
        text += " The cost of each generator alone gives the same choice."
    else:
        alone = "; ".join(
            f"{GENERATOR_TITLES[g]} alone: {c['stratifier']}, {c['stage_size']} questions"
            for g, c in probe["choice_by_generator"].items()
        )
        text += f" The generators alone give different choices ({alone})."
    return text


def _recheck_text(item: Mapping[str, Any]) -> str:
    recheck = item["recheck"]
    if not recheck["available"]:
        return f"Not available: {recheck['reason']}"
    if recheck["matches"]:
        return "Same value"
    return (
        f"Differs: {recheck['interval_method']}, {recheck['stratifier']}, "
        f"{recheck['stage1_size']} questions"
    )


def _decimal(value: float) -> str:
    return f"{value:g}"


def _fixed_rows(document: Mapping[str, Any]) -> list[tuple[str, str]]:
    protocol = document["protocol"]
    decision, panel, rule = protocol["decision"], protocol["public_panel"], protocol["grade_rule"]
    replay, study = protocol["unseen_model_replay"], protocol["reference_panel_study"]
    pruned = protocol["pruned_set_test"]
    zone = decision["indifference_zone"]
    seeds, pruned_seeds = replay["selection_seeds"], pruned["selection_seeds"]
    grid = replay["thresholds"]
    thresholds = ", ".join(
        f"{BENCHMARKS[name].title} {value:.2f}" for name, value in document["thresholds"].items()
    )
    baseline = replay["baseline"]
    return [
        ("Primary thresholds", thresholds),
        (
            "Indifference zone",
            f"{_decimal(zone['primary'])} for the primary result, "
            f"{_decimal(zone['secondary'])} as a secondary result",
        ),
        ("Stages", str(decision["stages"])),
        (
            "Public panel pin",
            f"SHA-256 {panel['sha256']} ({panel['models']} models, {panel['questions']:,} "
            f"questions, issue #{panel['issue']})",
        ),
        (
            "Question mapping",
            f"SHA-256 {panel['mapping_sha256']} ({panel['mapped_questions']} questions)",
        ),
        ("Grade rule", rule["statement"]),
        (
            "Unseen-model replay",
            f"Issue #{replay['issue']}. Strata from the committed 3-model reference panel "
            f"(SHA-256 {replay['reference_panel_sha256']}). Targets: the {replay['targets']} "
            f"public models on the {replay['questions']} mapped questions. The LiveCodeBench "
            "section of this policy applies with no change.",
        ),
        (
            "Replay thresholds",
            f"{grid['start']:.2f} to {grid['stop']:.2f} in steps of {grid['step']:.2f}",
        ),
        (
            "Replay selection seeds",
            f"{seeds['first']} to {seeds['last']} for each model and threshold",
        ),
        ("Replay coverage", f"{replay['coverage_subsets']:,} new stratified subsets per model"),
        (
            "Baseline",
            f"A {baseline['selector'].replace('_', ' ')} probe of the same size with the "
            f"{baseline['interval_method']} interval",
        ),
        (
            "Reference-panel study",
            f"Issue #{study['issue']}. Strata from the reference pass rate, cut into "
            f"{study['groups']} groups of near-equal size, with {study['secondary_groups']} "
            f"groups as a secondary result. The {study['full_panel_questions']:,}-question arm "
            f"uses {study['full_panel_stage1_size']} questions at stage 1: the stage-1 fraction "
            "of the LiveCodeBench section, rounded up.",
        ),
        (
            "Pruned-set test",
            f"Issue #{pruned['issue']}. Fixed subsets of "
            f"{' and '.join(str(n) for n in pruned['sizes'])} questions, with "
            f"{', '.join(str(n) for n in pruned['reported_sizes'])} questions as a reported "
            f"size. Strata from the committed 3-model reference panel. The published set uses "
            f"selection seed {pruned['published_seed']}. The interval method is "
            f"{pruned['interval_method']}. The spread uses seeds "
            f"{pruned_seeds['first']} to {pruned_seeds['last']}. Coverage uses "
            f"{pruned['coverage_subsets']:,} new subsets.",
        ),
    ]


def frozen_html(document: Mapping[str, Any]) -> str:
    """The "Frozen policy" section of the HTML report."""
    e = html.escape
    protocol = document["protocol"]
    replay, pruned = protocol["unseen_model_replay"], protocol["pruned_set_test"]
    source = document["source"]
    chosen_rows = []
    for item in document["benchmarks"]:
        title, key = e(item["title"]), e(item["benchmark"])
        probe = item["probe"]
        chosen_rows.append(
            f'<tr data-chosen="{key}-interval-method"><td>{title}</td><td>Interval method</td>'
            f"<td><code>{e(item['interval_method']['chosen'])}</code></td>"
            f"<td>{e(_method_evidence(item))}</td><td>{e(_recheck_text(item))}</td></tr>"
        )
        chosen_rows.append(
            f'<tr data-chosen="{key}-probe"><td>{title}</td><td>Stratifier and stage-1 size</td>'
            f"<td><code>{e(probe['stratifier'])}</code>, {probe['stage_size']} questions</td>"
            f"<td>{e(_probe_evidence(item))}</td><td>{e(_recheck_text(item))}</td></tr>"
        )
    candidates = []
    for item in document["benchmarks"]:
        title = e(item["title"])
        method_rows = "\n".join(
            f"<tr><td>{e(_method_title(c['method']))}</td>"
            f"<td>{c['cells'] - c['cells_failed']} of {c['cells']}</td>"
            f"<td>{_width(c['mean_width'])}</td>"
            f"<td>{'chosen' if c['method'] == item['interval_method']['chosen'] else ''}</td></tr>"
            for c in item["interval_method"]["candidates"]
        )
        probe = item["probe"]
        chosen_setting = (probe["stratifier"], probe["stage_size"])
        probe_rows = "\n".join(
            f"<tr><td><code>{e(c['stratifier'])}</code></td><td>{c['stage_size']}</td>"
            f"<td>{'pass' if c['passes_both_generators'] else 'fail'}</td>"
            f"<td>{c['mean_cost_fraction']['rasch']:.4f}</td>"
            f"<td>{c['mean_cost_fraction']['reference_flip']:.4f}</td>"
            f"<td>{c['mean_cost_fraction_both']:.4f}</td>"
            f"<td>{'chosen' if (c['stratifier'], c['stage_size']) == chosen_setting else ''}"
            "</td></tr>"
            for c in probe["candidates"]
        )
        candidates.append(
            f"""<h4>{title}: interval methods in the coverage study</h4>
<div class="scroll"><table>
<thead><tr><th>Method</th><th>Cells passed</th><th>Mean width</th><th>Choice</th></tr></thead>
<tbody>
{method_rows}
</tbody></table></div>
<h4>{title}: settings of <code>{e(item["interval_method"]["chosen"])}</code>
in the error-rate study</h4>
<div class="scroll"><table>
<thead><tr><th>Stratifier</th><th>Stage-1 size</th><th>Error rate, both generators</th>
<th>Cost, Rasch</th><th>Cost, reference flip</th><th>Cost, mean</th><th>Choice</th></tr></thead>
<tbody>
{probe_rows}
</tbody></table></div>"""
        )
    fixed = "\n".join(
        f"<tr><td>{e(label)}</td><td>{e(value)}</td></tr>" for label, value in _fixed_rows(document)
    )
    groups = protocol["reference_panel_study"]["developer_groups"]
    group_rows = "\n".join(
        f"<tr><td>{e(group)}</td><td>{len(models)}</td><td>{e(', '.join(models))}</td></tr>"
        for group, models in groups.items()
    )
    replay_criteria = "\n".join(
        f"<li>{e(c['statement'])}</li>" for c in replay["pass_criteria"].values()
    )
    pruned_criteria = "\n".join(
        f"<li>{e(c['statement'])}</li>" for c in pruned["pass_criteria"].values()
    )
    criteria = pruned["pass_criteria"]
    limits = (
        f"{criteria['published_mean_abs_error']['max']:g} and "
        f"{criteria['published_max_abs_error']['max']:g}"
    )
    comparisons = replay["stated_comparisons"]
    simulated = comparisons["real_vs_simulated_d95"]["simulated"]
    d95 = "not reached" if simulated["d95"] is None else f"{simulated['d95']:.2f}"
    stated = "\n".join(f"<li>{e(c['statement'])}</li>" for c in comparisons.values())
    disclosures = "\n".join(
        f'<li data-disclosure="{e(name)}">{e(text)}</li>'
        for name, text in protocol["disclosures"].items()
    )
    reproduced = {
        True: "The rules, applied to the coverage and error-rate results of this run, give "
        "the same values.",
        False: "The rules, applied to the coverage and error-rate results of this run, give "
        "different values. The table shows the differences.",
        None: "The rules cannot be applied to the results of this run. The table gives the reason.",
    }[document["rules_reproduced_on_this_run"]]
    return f"""<section data-frozen-policy id="frozen-policy">
<h2>Frozen policy</h2>
<p class="claim">Policy <code>{e(document["key"])}</code> is frozen. Its SHA-256 is
<code data-frozen-sha256>{e(document["sha256"])}</code>. The lock file
<code>policies/frozen-policies.json</code> records this hash. A later change must create a new
policy version. The commands never overwrite the results of this version.</p>
<p>Fixed rules chose the tuned values from simulated results only. The rules read no real
grade. The source is the simulated run of <code>{e(str(source["policy"]))}</code> (policy
SHA-256 <code>{e(str(source["policy_sha256"]))}</code>, summary SHA-256
<code>{e(str(source["summary_sha256"]))}</code>, manifest SHA-256
<code>{e(str(source["manifest_sha256"]))}</code>).</p>
<h3>Rules</h3>
<ol>
<li>{e(document["rules"]["interval_method"])}</li>
<li>{e(document["rules"]["probe"])}</li>
</ol>
<p>The candidates are the existing stratifiers only. The Neyman selector (#61) is deferred and
is not a candidate.</p>
<h3>Chosen values</h3>
<p>{e(reproduced)}</p>
<div class="scroll"><table>
<thead><tr><th>Benchmark</th><th>Value</th><th>Chosen</th>
<th>Simulated result that chose it</th><th>Rule on this run</th></tr></thead>
<tbody>
{chr(10).join(chosen_rows)}
</tbody></table></div>
{chr(10).join(candidates)}
<h3>Fixed values</h3>
<p>This policy fixes these values without tuning.</p>
<div class="scroll"><table>
<thead><tr><th>Value</th><th>Setting</th></tr></thead>
<tbody>
{fixed}
</tbody></table></div>
<h4>Developer groups of the reference-panel study</h4>
<div class="scroll"><table>
<thead><tr><th>Group</th><th>Models</th><th>Model names</th></tr></thead>
<tbody>
{group_rows}
</tbody></table></div>
<h3>Pass criteria of the real replay</h3>
<p>Each real replay applies these criteria.</p>
<ol data-criteria="real-replay">
{replay_criteria}
</ol>
<h3>Stated comparisons</h3>
<p>The replay reports these comparisons with no pass or fail mark. The simulated d95 of the
LiveCodeBench setting is {e(d95)}.</p>
<ul data-comparisons>
{stated}
</ul>
<h3>Pass criteria of the pruned-set test</h3>
<p>These criteria apply to each size of the pruned-set test only. The limits
{e(limits)} come from the earlier operating-point policy with no change.</p>
<ol data-criteria="pruned-set">
{pruned_criteria}
</ol>
<h3>Disclosures</h3>
<ul>
{disclosures}
</ul>
</section>"""


def console_lines(document: Mapping[str, Any] | None) -> Sequence[str]:
    """One console line for each chosen value and its rule check on this run."""
    if document is None:
        return ()
    lines = []
    for item in document["benchmarks"]:
        probe = item["probe"]
        lines.append(
            f"{item['title']}, frozen {document['key']}: {item['interval_method']['chosen']}, "
            f"{probe['stratifier']}, {probe['stage_size']} questions; rule on this run: "
            f"{_recheck_text(item).lower()}"
        )
    return lines
