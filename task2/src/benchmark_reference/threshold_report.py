"""Decision table, summary, self-contained HTML report, and manifest bytes.

Every output is a deterministic function of the policy file and the reference
panel: no timestamps, absolute paths, or environment values. Two runs with the
same inputs therefore give byte-identical outputs and manifests.
"""

import csv
import hashlib
import html
import io
import math
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.threshold_cost import (
    CostEvidence,
    run_tokens,
)
from benchmark_reference.threshold_intervals import (
    BONFERRONI,
    BOOTSTRAP,
    BOOTSTRAP_REPLICATES,
    INTERVAL_METHODS,
    POOLED_EXACT,
    WILSON,
)
from benchmark_reference.threshold_policy import LoadedPolicy, alpha_spending
from benchmark_reference.threshold_study import SimulatedDecision

ANALYSIS_VERSION = "threshold-two-stage-v3"
OUTPUT_NAMES = (
    "decisions.csv",
    "coverage.csv",
    "cost.csv",
    "question_tokens.csv",
    "summary.json",
    "report.html",
    "manifest.json",
)
METHOD_LABELS = {
    POOLED_EXACT: "Pooled exact",
    BONFERRONI: "Bonferroni exact",
    WILSON: "Stratified Wilson",
    BOOTSTRAP: "Stratified bootstrap",
}
METHOD_NOTES = {
    POOLED_EXACT: "Exact hypergeometric interval for all sampled questions "
    "as one simple random sample. It ignores the strata.",
    BONFERRONI: "Exact interval for each stratum at alpha divided "
    "by the number of strata, with the bounds added. It is a conservative reference.",
    WILSON: "Wilson score interval for the stratified estimate, with the Kish "
    "effective sample size and the finite-population correction.",
    BOOTSTRAP: f"Percentile interval of {BOOTSTRAP_REPLICATES:,} Rao-Wu rescaling "
    "bootstrap resamples. Its variance is the unbiased stratified variance with the "
    "finite-population correction.",
}
# The line dash and the marker shape give each method a second encoding beside color.
_DASHES = ("", "7 4", "2 3", "9 3 2 3")
LIMITATIONS = (
    "Simulated models only. No real model grades are used in this run.",
    "The generator takes question difficulty from the same reference grades that "
    "define the strata. Strata therefore match the simulated difficulty exactly, "
    "which favors stratification. A second generator is planned in issue #60.",
    "The pooled exact interval treats the stratified probe as one simple random "
    "sample. The allocation in each stratum differs from the proportional share "
    "by less than one question. Stratification with that allocation usually "
    "narrows the true sampling spread, so we expect the interval to be "
    "conservative. The wrong-decision rates are the measured check.",
    "Hash priorities approximate uniform random sampling within each stratum.",
    "One probe exists for each selector seed. All simulated models with that seed "
    "share the probe, so the models are not fully independent.",
    "Wrong-decision rates are Monte Carlo estimates. The table gives a one-sided "
    "95% Clopper-Pearson upper bound for each rate. That bound assumes independent "
    "models, so the shared probes make it optimistic.",
    "Pair-order metrics are diagnostics only and are not gates. This report does not compute them.",
    "Coverage is measured over simulated models: each draw has a new model and a new "
    "subset. It is not the coverage for one fixed model.",
    "The Wilson interval uses the Kish effective sample size. That size ignores the "
    "variance reduction from stratification, so the interval is usually conservative.",
    "The bootstrap cannot estimate the variance of a stratum with one sampled question or "
    "with only passes or only failures. Such a stratum adds no width, so the bootstrap "
    "interval can be too narrow when strata are small.",
    "The coverage study uses the same generator as the decision study, so it has the "
    "same match between strata and simulated difficulty. Issue #60 adds a second generator.",
    "Token cost counts the input and output tokens of the model answers. It does not "
    "count judge or grader tokens, and it is not a price: input and output tokens "
    "usually have different prices. The summary gives the input and output split.",
    "An unseen model has no token counts, so the cost of each question comes from the "
    "reference models. The low and high estimates are the sums of the per-question "
    "minimum and maximum across those models. They are an envelope, not a confidence "
    "interval: an unseen model can use fewer or more tokens than every reference model.",
    "The cost assumes that ESCALATE keeps the stage-1 answers and grades only the "
    "remaining questions, so an escalated run costs one full run.",
    "The cost at each stage size and band is a Monte Carlo estimate. The decision study "
    "has one probe for each selector seed, so the probes limit its precision.",
)
DRAFT_LIMITATION = "The policy is a draft. It is not frozen and must not be used on real grades."
IMPLEMENTATION_FILES = (
    "models.py",
    "pruning.py",
    "uncertainty.py",
    "threshold_intervals.py",
    "threshold_policy.py",
    "threshold_simulation.py",
    "two_stage.py",
    "threshold_study.py",
    "inputs.py",
    "threshold_tokens.py",
    "threshold_cost.py",
    "threshold_coverage.py",
    "threshold_report.py",
    "threshold_cli.py",
)
_COVERAGE_COLUMNS = (
    "stratifier",
    "stage_size",
    "true_score",
    "full_passes",
    "method",
    "subsets",
    "covered",
    "coverage",
    "truth_below_interval",
    "truth_above_interval",
    "mean_width",
    "passes",
    "escalated",
    "expected_cost_fraction_low",
    "expected_cost_fraction_mean",
    "expected_cost_fraction_high",
)
_COST_COLUMNS = (
    "stage_size",
    "true_score",
    "draws",
    "escalated",
    "escalation_rate",
    "stage1_tokens_low",
    "stage1_tokens_mean",
    "stage1_tokens_high",
    "expected_tokens_low",
    "expected_tokens_mean",
    "expected_tokens_high",
    "full_tokens_low",
    "full_tokens_mean",
    "full_tokens_high",
    "expected_cost_fraction_low",
    "expected_cost_fraction_mean",
    "expected_cost_fraction_high",
)
_COLUMNS = (
    "true_score",
    "full_passes",
    "full_score",
    "truth",
    "selector_seed",
    "replicate",
    "model_seed",
    "stage1_size",
    "stage1_successes",
    "stage1_lower",
    "stage1_upper",
    "stage1_result",
    "decision",
    "decided_stage",
    "questions_graded",
    "wrong",
    "tokens_low",
    "tokens_mean",
    "tokens_high",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokens(value: Fraction) -> str:
    """Tokens with one decimal; a mean across models need not be whole."""
    return f"{float(value):.1f}"


def _share(value: float | None) -> str:
    """A cost fraction with 3 decimals, or a dash when no cost model ran."""
    return "-" if value is None else f"{value:.3f}"


def decision_table(
    rows: Sequence[SimulatedDecision], *, population: int, cost: CostEvidence
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_COLUMNS)
    for row in rows:
        result = row.result
        used = run_tokens(result, cost.model)
        writer.writerow(
            (
                row.true_score,
                row.full_passes,
                f"{row.full_passes / population:.6f}",
                row.truth,
                row.selector_seed,
                row.replicate,
                row.model_seed,
                result.stage1_size,
                result.stage1_successes,
                f"{float(result.stage1_lower):.6f}",
                f"{float(result.stage1_upper):.6f}",
                result.stage1_result,
                result.decision,
                result.decided_stage,
                result.questions_graded,
                int(row.wrong),
                used.low,
                _tokens(used.mean),
                used.high,
            )
        )
    return stream.getvalue().encode("utf-8")


def coverage_table(coverage: Mapping[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_COVERAGE_COLUMNS)
    for cell in coverage["cells"]:
        writer.writerow(
            (
                # The first seven columns need no formatting.
                *(cell[name] for name in _COVERAGE_COLUMNS[:7]),
                f"{cell['coverage']:.4f}",
                cell["truth_below_interval"],
                cell["truth_above_interval"],
                f"{cell['mean_width']:.6f}",
                int(cell["passes"]),
                cell["escalated"],
                *(
                    ("", "", "")
                    if cell["expected_cost_fraction"] is None
                    else (
                        f"{cell['expected_cost_fraction'][k]:.6f}" for k in ("low", "mean", "high")
                    )
                ),
            )
        )
    return stream.getvalue().encode("utf-8")


def cost_table(cost: CostEvidence) -> bytes:
    """One row for each cost stage size and true score."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_COST_COLUMNS)
    for cell in cost.cells:
        fraction = cell.fraction
        writer.writerow(
            (
                cell.stage_size,
                cell.true_score,
                cell.draws,
                cell.escalated,
                f"{float(cell.escalation_rate):.6f}",
                *(_tokens(v) for v in cell.stage1.values),
                *(_tokens(v) for v in cell.expected.values),
                *(_tokens(v) for v in cell.full.values),
                *(f"{float(v):.6f}" for v in fraction.values),
            )
        )
    return stream.getvalue().encode("utf-8")


def question_token_table(cost: CostEvidence) -> bytes:
    """Each question: its estimate and the counts of every reference model.

    An empty count cell is a missing count. It is never a zero.
    """
    models = sorted(cost.tokens.counts)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "index",
            "models_with_counts",
            "tokens_low",
            "tokens_mean",
            "tokens_high",
            "input_tokens_mean",
            "output_tokens_mean",
            *(f"{m}_{kind}_tokens" for m in models for kind in ("input", "output")),
        )
    )
    for index, estimate in sorted(cost.questions.items()):
        counts: list[int | str] = []
        for model in models:
            count = cost.tokens.counts[model].get(index)
            counts.extend(("", "") if count is None else (count.input, count.output))
        writer.writerow(
            (
                index,
                estimate.models,
                estimate.low,
                _tokens(estimate.mean),
                estimate.high,
                _tokens(estimate.input_mean),
                _tokens(estimate.output_mean),
                *counts,
            )
        )
    return stream.getvalue().encode("utf-8")


def _cross_check(
    cost: CostEvidence, coverage: Mapping[str, Any], *, stratifier: str, method: str
) -> dict[str, Any]:
    """Compare the decision-study cost with the coverage-study cost of the policy method.

    The decision study reuses one probe for each selector seed. The coverage
    study draws a new subset for every draw. Both estimate the same expected cost.
    """
    by_key = {
        (c["stage_size"], c["true_score"]): c["expected_cost_fraction"]["mean"]
        for c in coverage["cells"]
        if c["stratifier"] == stratifier
        and c["method"] == method
        and c["expected_cost_fraction"] is not None
    }
    pairs = [
        (cell, by_key[(cell.stage_size, cell.true_score)])
        for cell in cost.cells
        if (cell.stage_size, cell.true_score) in by_key
    ]
    if not pairs:
        return {"cells": 0, "max_abs_difference": None, "stage_sizes": []}
    gaps = [(abs(float(cell.fraction.mean) - other), cell) for cell, other in pairs]
    gap, worst = max(gaps, key=lambda item: (item[0], item[1].stage_size, item[1].true_score))
    return {
        "cells": len(pairs),
        "stage_sizes": sorted({cell.stage_size for cell, _ in pairs}),
        "max_abs_difference": round(gap, 6),
        "max_at": {"stage_size": worst.stage_size, "true_score": worst.true_score},
    }


def cost_document(
    cost: CostEvidence, coverage: Mapping[str, Any], *, stratifier: str, method: str
) -> dict[str, Any]:
    model, full = cost.model, cost.model.full
    population = len(model.questions)
    return {
        "unit": "input plus output tokens of the model answers",
        "estimate": "For each question: the low, mean, and high total across the reference "
        "models with a count. A set of questions sums each estimate.",
        "expected_cost": "stage-1 tokens + escalation probability x remaining tokens, "
        "divided by the full-set tokens of the same estimate",
        "reference_models": sorted(cost.tokens.counts),
        "missing_counts": [
            {"model": m.model, "index": m.index, "field": m.field} for m in cost.tokens.missing
        ],
        "full_run": {
            "questions": population,
            "tokens": full.rounded(1),
            "input_tokens_mean": round(float(model.full_input_mean), 1),
            "output_tokens_mean": round(float(model.full_output_mean), 1),
            "tokens_per_question_mean": round(float(full.mean) / population, 1),
        },
        "stage_sizes": sorted({c.stage_size for c in cost.cells}),
        "bands": [
            {
                "band": b.label,
                "low": b.low,
                "high": b.high,
                "stage_size": b.stage_size,
                "true_scores": list(b.true_scores),
                "escalation_rate": round(float(b.escalation_rate), 6),
                "expected_tokens": b.expected.rounded(1),
                "expected_cost_fraction": b.fraction.rounded(6),
            }
            for b in cost.bands
        ],
        "cross_check": _cross_check(cost, coverage, stratifier=stratifier, method=method),
    }


def summary_document(
    loaded: LoadedPolicy,
    summary: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    cost: CostEvidence,
    *,
    population: int,
    panel_sha256: str,
) -> dict[str, Any]:
    policy = loaded.policy
    point = {cell.true_score: cell for cell in cost.point}
    summary = [
        {
            **row,
            "expected_tokens": point[row["true_score"]].expected.rounded(1),
            "expected_cost_fraction": point[row["true_score"]].fraction.rounded(6),
        }
        for row in summary
    ]
    draws = sum(row["draws"] for row in summary)
    wrong = sum(row["wrong_decisions"] for row in summary)
    decided = sum(row["decided_at_stage1"] for row in summary)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "mode": "simulated",
        "policy": {"key": loaded.key, "sha256": loaded.sha256, "frozen": policy.frozen},
        "reference_panel_sha256": panel_sha256,
        "benchmark": policy.benchmark,
        "population": population,
        "threshold": policy.threshold,
        "alpha": policy.alpha,
        "alpha_spending": {
            "stage1": alpha_spending(policy)[0],
            "census": alpha_spending(policy)[1],
        },
        "stage1_size": policy.stage1_size,
        "interval_method": policy.interval_method,
        "stratifier": policy.stratifier,
        "selector_seeds": list(policy.seeds),
        "models_per_seed": policy.models_per_seed,
        "simulation_seed": policy.simulation_seed,
        "overall": {
            "draws": draws,
            "decided_at_stage1": decided,
            "wrong_decisions": wrong,
            "max_wrong_decision_rate": max(r["wrong_decision_rate"] for r in summary),
        },
        "true_scores": list(summary),
        "coverage": {key: value for key, value in coverage.items() if key != "cells"},
        "cost": cost_document(
            cost, coverage, stratifier=policy.stratifier, method=policy.interval_method
        ),
        "limitations": [*LIMITATIONS, *(() if policy.frozen else (DRAFT_LIMITATION,))],
    }


_STYLE = """
:root { color-scheme: light dark; --bg: #ffffff; --fg: #1b1f24; --muted: #57606a;
  --line: #d0d7de; --panel: #f6f8fa; --decisive: #0b6bcb; --wrong: #c4321b;
  --mark: #8250df; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0d1117; --fg: #e6edf3; --muted: #9da7b3; --line: #30363d;
    --panel: #161b22; --decisive: #58a6ff; --wrong: #ff7b72; --mark: #d2a8ff; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 920px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 8px; }
h2 { font-size: 1.2rem; margin: 32px 0 8px; }
p, li { max-width: 72ch; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 0.9em; overflow-wrap: anywhere; }
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px; padding: 0; list-style: none; }
.facts li { background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  padding: 8px 12px; }
.facts b { display: block; font-size: 1.15rem; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
thead th { background: var(--panel); }
svg { width: 100%; height: auto; max-width: 720px; display: block; }
svg text { fill: var(--muted); font-size: 12px; }
.axis { stroke: var(--line); }
.decisive { stroke: var(--decisive); fill: none; stroke-width: 2.5; }
.decisive-dot { fill: var(--decisive); }
.wrong { stroke: var(--wrong); fill: none; stroke-width: 2.5; }
.wrong-dot { fill: var(--wrong); }
.mark { stroke: var(--mark); stroke-dasharray: 5 4; stroke-width: 1.5; }
.method-1 { --method: #2a78d6; } .method-2 { --method: #eb6834; }
.method-3 { --method: #1baf7a; } .method-4 { --method: #eda100; }
@media (prefers-color-scheme: dark) {
  .method-1 { --method: #3987e5; } .method-2 { --method: #d95926; }
  .method-3 { --method: #199e70; } .method-4 { --method: #c98500; }
}
.series { stroke: var(--method); fill: none; stroke-width: 2; }
.marker { fill: var(--method); stroke: var(--bg); stroke-width: 1.5; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 20px; padding: 0; list-style: none; }
.legend li { display: flex; align-items: center; gap: 6px; }
.legend svg { width: 36px; height: 14px; }
.panels { display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); }
.panels figure { margin: 0; min-width: 0; }
.halo { paint-order: stroke; stroke: var(--bg); stroke-width: 4px; stroke-linejoin: round; }
.panels figcaption { font-weight: 600; margin-bottom: 4px; }
.fail { font-weight: 700; }
"""


def _chart(
    title: str,
    description: str,
    points: Sequence[tuple[float, float]],
    *,
    series: str,
    y_max: float,
    y_label: str,
    threshold: float,
    reference: tuple[float, str] | None = None,
) -> str:
    width, height, left, right, top, bottom = 640, 260, 56, 16, 16, 44
    xs = [x for x, _ in points]
    x_low, x_high = min(xs), max(xs)
    span = x_high - x_low or 1.0

    def px(x: float) -> float:
        return left + (x - x_low) / span * (width - left - right)

    def py(y: float) -> float:
        return top + (1 - y / y_max) * (height - top - bottom)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="{series}-t {series}-d">',
        f'<title id="{series}-t">{html.escape(title)}</title>',
        f'<desc id="{series}-d">{html.escape(description)}</desc>',
        f'<line class="axis" x1="{left}" y1="{py(0):.1f}" x2="{width - right}" y2="{py(0):.1f}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{py(0):.1f}"/>',
    ]
    for tick in (0.0, y_max / 2, y_max):
        parts.append(
            f'<text x="{left - 6}" y="{py(tick) + 4:.1f}" text-anchor="end">{tick:.3g}</text>'
        )
    for x in xs:
        parts.append(
            f'<text x="{px(x):.1f}" y="{py(0) + 16:.1f}" text-anchor="middle">{x:.2f}</text>'
        )
    if x_low <= threshold <= x_high:
        parts.append(
            f'<line class="mark" x1="{px(threshold):.1f}" y1="{top}" '
            f'x2="{px(threshold):.1f}" y2="{py(0):.1f}"/>'
            f'<text x="{px(threshold) + 4:.1f}" y="{top + 12}">threshold {threshold:.2f}</text>'
        )
    if reference is not None:
        value, label = reference
        parts.append(
            f'<line class="mark" x1="{left}" y1="{py(value):.1f}" '
            f'x2="{width - right}" y2="{py(value):.1f}"/>'
            f'<text x="{width - right}" y="{py(value) - 4:.1f}" text-anchor="end">'
            f"{html.escape(label)}</text>"
        )
    path = " ".join(f"{px(x):.1f},{py(min(y, y_max)):.1f}" for x, y in points)
    parts.append(f'<polyline class="{series}" points="{path}"/>')
    parts.extend(
        f'<circle class="{series}-dot" cx="{px(x):.1f}" cy="{py(min(y, y_max)):.1f}" r="3.5"/>'
        for x, y in points
    )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 6}" text-anchor="middle">'
        "true full-set score (fraction of questions passed)</text>"
        f'<text transform="translate(14 {(top + py(0)) / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle">{html.escape(y_label)}</text></svg>'
    )
    return "\n".join(parts)


def _marker(slot: int, x: float, y: float, tip: str = "") -> str:
    """Circle, square, triangle, or diamond for method slots 1 to 4."""
    shape = (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4"',
        f'<rect x="{x - 3.5:.1f}" y="{y - 3.5:.1f}" width="7" height="7"',
        f'<path d="M{x:.1f} {y - 4.5:.1f} L{x + 4.5:.1f} {y + 3.5:.1f} '
        f'L{x - 4.5:.1f} {y + 3.5:.1f} Z"',
        f'<path d="M{x:.1f} {y - 5:.1f} L{x + 5:.1f} {y:.1f} L{x:.1f} {y + 5:.1f} '
        f'L{x - 5:.1f} {y:.1f} Z"',
    )[slot - 1]
    tag = ("circle", "rect", "path", "path")[slot - 1]
    title = f"<title>{html.escape(tip)}</title>" if tip else ""
    return f'{shape} class="marker method-{slot}">{title}</{tag}>'


def _series_line(slot: int, points: str) -> str:
    dash = f' stroke-dasharray="{_DASHES[slot - 1]}"' if _DASHES[slot - 1] else ""
    return f'<polyline class="method-{slot} series"{dash} points="{points}"/>'


def _coverage_chart(
    key: str,
    cells: Sequence[Mapping[str, Any]],
    *,
    title: str,
    y_min: float,
    pass_line: float,
) -> str:
    """Coverage against true score, one line for each method, the pass line marked."""
    width, height, left, right, top, bottom = 340, 230, 52, 20, 12, 40
    xs = sorted({float(c["true_score"]) for c in cells})
    x_low, x_high = xs[0], xs[-1]
    span = x_high - x_low or 1.0

    def px(x: float) -> float:
        return left + (x - x_low) / span * (width - left - right)

    def py(y: float) -> float:
        return top + (1 - (max(y, y_min) - y_min) / (1 - y_min)) * (height - top - bottom)

    e = html.escape
    lows = {
        m: min(float(c["coverage"]) for c in cells if c["method"] == m) for m in INTERVAL_METHODS
    }
    description = (
        "Coverage for each true score and method. Lowest coverage: "
        + "; ".join(f"{METHOD_LABELS[m]} {lows[m]:.3f}" for m in INTERVAL_METHODS)
        + f". The dashed line is the pass line {pass_line:.3f}."
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-coverage="{e(key)}" '
        f'aria-labelledby="{e(key)}-t {e(key)}-d">',
        f'<title id="{e(key)}-t">{e(title)}</title>',
        f'<desc id="{e(key)}-d">{e(description)}</desc>',
        f'<line class="axis" x1="{left}" y1="{py(y_min):.1f}" x2="{width - right}" '
        f'y2="{py(y_min):.1f}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{py(y_min):.1f}"/>',
    ]
    for tick in (y_min, (y_min + 1) / 2, 1.0):
        parts.append(
            f'<text x="{left - 6}" y="{py(tick) + 4:.1f}" text-anchor="end">{tick:.3f}</text>'
        )
    for x in xs[::2]:
        parts.append(
            f'<text x="{px(x):.1f}" y="{py(y_min) + 15:.1f}" text-anchor="middle">{x:.2f}</text>'
        )
    parts.append(
        f'<line class="mark" x1="{left}" y1="{py(pass_line):.1f}" x2="{width - right}" '
        f'y2="{py(pass_line):.1f}"/>'
        f'<text class="halo" x="{width - right}" y="{py(pass_line) + 14:.1f}" '
        f'text-anchor="end">pass line {pass_line:.3f}</text>'
    )
    for slot, method in enumerate(INTERVAL_METHODS, start=1):
        mine = sorted(
            (c for c in cells if c["method"] == method), key=lambda c: float(c["true_score"])
        )
        path = " ".join(
            f"{px(float(c['true_score'])):.1f},{py(float(c['coverage'])):.1f}" for c in mine
        )
        parts.append(_series_line(slot, path))
        parts.extend(
            _marker(
                slot,
                px(float(c["true_score"])),
                py(float(c["coverage"])),
                f"{METHOD_LABELS[method]}, true score {c['true_score']}: coverage "
                f"{float(c['coverage']):.3f} ({c['covered']} of {c['subsets']}), "
                f"mean width {float(c['mean_width']):.3f}",
            )
            for c in mine
        )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 6}" text-anchor="middle">'
        "true full-set score</text>"
        f'<text transform="translate(12 {(top + py(y_min)) / 2:.1f}) rotate(-90)" '
        'text-anchor="middle">coverage (share of draws)</text></svg>'
    )
    return "\n".join(parts)


def _legend(labels: Sequence[str]) -> str:
    """One legend entry for each slot: line, dash pattern, marker, and label."""
    items = "\n".join(
        f'<li><svg viewBox="0 0 36 14" aria-hidden="true">{_series_line(slot, "2,7 34,7")}'
        f"{_marker(slot, 18, 7)}</svg>{html.escape(label)}</li>"
        for slot, label in enumerate(labels, start=1)
    )
    return f'<ul class="legend">\n{items}\n</ul>'


def _cost_chart(cost: CostEvidence, *, policy_size: int) -> str:
    """Expected cost against stage-1 size, one line for each true-score band.

    The whisker at each point spans the low, mean, and high estimates.
    """
    width, height, left, right, top, bottom = 640, 280, 56, 16, 16, 44
    population = len(cost.model.questions)
    labels = list(dict.fromkeys(b.label for b in cost.bands))
    sizes = sorted({b.stage_size for b in cost.bands})

    def px(n: float) -> float:
        return left + n / population * (width - left - right)

    def py(y: float) -> float:
        return top + (1 - min(max(y, 0.0), 1.0)) * (height - top - bottom)

    e = html.escape
    at_policy = [float(b.fraction.mean) for b in cost.bands if b.stage_size == policy_size]
    if at_policy:
        title = (
            f"At {policy_size} questions, the expected cost is {min(at_policy):.2f} to "
            f"{max(at_policy):.2f} of a full run, by true-score band"
        )
    else:
        title = "Expected token cost against stage-1 size, by true-score band"
    description = (
        "Expected cost as a share of a full run, mean estimate, for each band and stage size: "
        + "; ".join(
            f"true score {label}: "
            + ", ".join(
                f"{b.stage_size} questions {float(b.fraction.mean):.3f}"
                for b in cost.bands
                if b.label == label
            )
            for label in labels
        )
        + ". The dashed diagonal is the cost when no run escalates."
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-cost="curve" '
        'aria-labelledby="cost-t cost-d">',
        f'<title id="cost-t">{e(title)}</title>',
        f'<desc id="cost-d">{e(description)}</desc>',
        f'<line class="axis" x1="{left}" y1="{py(0):.1f}" x2="{width - right}" y2="{py(0):.1f}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{py(0):.1f}"/>',
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        parts.append(
            f'<text x="{left - 6}" y="{py(tick) + 4:.1f}" text-anchor="end">{tick:.2f}</text>'
        )
    for n in (*sizes, population):
        parts.append(f'<text x="{px(n):.1f}" y="{py(0) + 16:.1f}" text-anchor="middle">{n}</text>')
    parts.append(
        f'<line class="mark" x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(population):.1f}" '
        f'y2="{py(1):.1f}"/>'
        f'<text class="halo" x="{px(population) - 4:.1f}" y="{py(1) + 28:.1f}" '
        'text-anchor="end">no escalation</text>'
    )
    if policy_size in sizes:
        parts.append(
            f'<line class="mark" x1="{px(policy_size):.1f}" y1="{top}" '
            f'x2="{px(policy_size):.1f}" y2="{py(0):.1f}"/>'
            f'<text class="halo" x="{px(policy_size) + 4:.1f}" y="{py(0) - 8:.1f}">'
            f"policy {policy_size}</text>"
        )
    for slot, label in enumerate(labels, start=1):
        mine = [b for b in cost.bands if b.label == label]
        path = " ".join(f"{px(b.stage_size):.1f},{py(float(b.fraction.mean)):.1f}" for b in mine)
        parts.append(_series_line(slot, path))
        for b in mine:
            values = [float(v) for v in b.fraction.values]
            parts.append(
                f'<line class="method-{slot} series" x1="{px(b.stage_size):.1f}" '
                f'y1="{py(min(values)):.1f}" x2="{px(b.stage_size):.1f}" '
                f'y2="{py(max(values)):.1f}"/>'
            )
            parts.append(
                _marker(
                    slot,
                    px(b.stage_size),
                    py(float(b.fraction.mean)),
                    f"True score {label}, {b.stage_size} questions: expected cost "
                    f"{float(b.fraction.mean):.3f} of a full run (low {values[0]:.3f}, high "
                    f"{values[2]:.3f}), escalation rate {float(b.escalation_rate):.3f}",
                )
            )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 6}" text-anchor="middle">'
        "stage-1 size (questions)</text>"
        f'<text transform="translate(14 {(top + py(0)) / 2:.1f}) rotate(-90)" '
        'text-anchor="middle">expected cost (share of a full run)</text></svg>'
    )
    return "\n".join(parts)


def _cost_section(cost: CostEvidence, document: Mapping[str, Any]) -> str:
    e = html.escape
    summary = document["cost"]
    full = summary["full_run"]
    policy_size = int(document["stage1_size"])
    labels = list(dict.fromkeys(b.label for b in cost.bands))
    sizes = sorted({b.stage_size for b in cost.bands})
    models = ", ".join(summary["reference_models"])
    missing = cost.tokens.missing
    if missing:
        listed = ", ".join(f"{m.model} question {m.index} ({m.field})" for m in missing[:10])
        more = f", and {len(missing) - 10} more" if len(missing) > 10 else ""
        missing_text = (
            f"{len(missing)} counts are missing: {e(listed)}{more}. "
            "<code>question_tokens.csv</code> leaves them empty. They are not zeros: the "
            "estimate for those questions uses only the models with a count."
        )
    else:
        missing_text = "Every reference answer has an input and an output count."
    point = [float(c.fraction.mean) for c in cost.point]
    head = "".join(f"<th>{n} questions</th>" for n in sizes)
    band_rows = []
    by_key = {(b.label, b.stage_size): b for b in cost.bands}
    for label in labels:
        values = []
        for n in sizes:
            b = by_key[(label, n)]
            spread = [float(v) for v in b.fraction.values]
            values.append(
                f'<td data-cost="{e(label)}-{n}">{spread[1]:.3f}<br>'
                f"<small>{min(spread):.3f} to {max(spread):.3f}</small></td>"
            )
        band_rows.append(f"<tr><td>{e(label)}</td>{''.join(values)}</tr>")
    groups = {
        (g["stratifier"], g["stage_size"], g["method"]): g for g in document["coverage"]["groups"]
    }
    settings = sorted({(s, n) for s, n, _ in groups})
    method_head = "".join(f"<th>{e(METHOD_LABELS[m])}</th>" for m in INTERVAL_METHODS)
    method_rows = []
    for stratifier, n in settings:
        cells = "".join(
            f'<td data-method-cost="{e(stratifier)}-{n}-{e(m)}">'
            f"{_share(groups[(stratifier, n, m)]['mean_expected_cost_fraction'])}</td>"
            for m in INTERVAL_METHODS
        )
        method_rows.append(f"<tr><td><code>{e(stratifier)}</code>, {n}</td>{cells}</tr>")
    check = summary["cross_check"]
    check_text = (
        f"For the policy method and stratifier, the two studies share {check['cells']} cells. "
        f"Their mean-estimate costs differ by at most {check['max_abs_difference']:.3f}."
        if check["cells"]
        else "The two studies share no stage size, so no cross-check is possible."
    )
    return f"""<h2>Token cost</h2>
<p>A saving in questions is not the same as a saving in tokens. The token counts come from
the saved answers of the reference models ({e(models)}). An unseen model has no counts, so
each question gets a low, a mean, and a high estimate across those models. A full run of
{full["questions"]} questions uses {full["tokens"]["mean"]:,.0f} tokens under the mean estimate
({full["tokens"]["low"]:,.0f} low, {full["tokens"]["high"]:,.0f} high). Of the mean,
{full["input_tokens_mean"]:,.0f} are input tokens and {full["output_tokens_mean"]:,.0f} are
output tokens. {missing_text}</p>
<p>A run decided at stage 1 uses the tokens of its probe. A run that escalates uses one full
run. The expected cost is the stage-1 tokens plus the escalation probability times the
remaining tokens, divided by the full-run tokens. Each estimate divides by its own full-run
total. At the policy size of {policy_size} questions, the expected cost is
{min(point):.3f} to {max(point):.3f} of a full run across the true scores.</p>
<ul class="facts">
<li>Full run, mean estimate<b>{full["tokens"]["mean"]:,.0f} tokens</b></li>
<li>Mean tokens per question<b>{full["tokens_per_question_mean"]:,.0f}</b></li>
<li>Output share of tokens<b>{full["output_tokens_mean"] / full["tokens"]["mean"]:.0%}</b></li>
<li>Missing counts<b>{len(missing)}</b></li>
</ul>
<h3>Expected cost against stage-1 size</h3>
<p>Each line is one band of true scores; each true score in a band has equal weight. The
marker is the mean estimate and the whisker spans the low, mean, and high estimates. The dashed
diagonal is the cost when no run escalates.</p>
{_legend([f"true score {label}" for label in labels])}
{_cost_chart(cost, policy_size=policy_size)}
<h3>Expected cost for each band</h3>
<p>The share of a full run under the mean estimate. Below it is the range of the share
across the low, mean, and high estimates. Each estimate divides by its own full-run total,
so the low estimate can give the larger share. <code>cost.csv</code> holds every stage size
and true score.</p>
<div class="scroll">
<table>
<thead><tr><th>True scores</th>{head}</tr></thead>
<tbody>
{chr(10).join(band_rows)}
</tbody>
</table>
</div>
<h3>Expected cost for each interval method</h3>
<p>The coverage draws give the same cost for every method: a draw that the method decides at
stage 1 costs its subset, and an escalated draw costs a full run. The value is the mean
estimate over every true score, each with equal weight. A narrower interval escalates less,
so it costs less, but only a method that keeps its coverage is safe to use. {check_text}</p>
<div class="scroll">
<table>
<thead><tr><th>Stratifier, stage size</th>{method_head}</tr></thead>
<tbody>
{chr(10).join(method_rows)}
</tbody>
</table>
</div>"""


def _coverage_section(coverage: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]) -> str:
    e = html.escape
    pass_line = float(coverage["pass_line"])
    # All panels use one y-range, so a reader can compare them at a glance.
    y_min = min(0.85, math.floor(min(float(c["coverage"]) for c in cells) * 20) / 20)
    groups = {(g["stratifier"], g["stage_size"], g["method"]): g for g in coverage["groups"]}
    settings = sorted({(s, n) for s, n, _ in groups})
    panels = []
    for stratifier, size in settings:
        passing = sum(groups[(stratifier, size, m)]["passes"] for m in INTERVAL_METHODS)
        title = (
            f"{size} questions, {stratifier}: {passing} of {len(INTERVAL_METHODS)} "
            "methods pass at every true score"
        )
        chart = _coverage_chart(
            f"{stratifier}-{size}",
            [c for c in cells if (c["stratifier"], c["stage_size"]) == (stratifier, size)],
            title=title,
            y_min=y_min,
            pass_line=pass_line,
        )
        panels.append(
            f"<figure><figcaption>{size} questions, <code>{e(stratifier)}</code>: {passing} "
            f"of {len(INTERVAL_METHODS)} methods pass</figcaption>\n{chart}</figure>"
        )
    header = "".join(f"<th>{e(METHOD_LABELS[m])}</th>" for m in INTERVAL_METHODS)

    def table(cell: Callable[[str, Mapping[str, Any]], str]) -> str:
        """One row for each setting. ``cell`` writes the cell of one method."""
        lines = []
        for stratifier, size in settings:
            values = "".join(
                cell(f"{e(stratifier)}-{size}-{e(m)}", groups[(stratifier, size, m)])
                for m in INTERVAL_METHODS
            )
            lines.append(f"<tr><td><code>{e(stratifier)}</code>, {size}</td>{values}</tr>")
        return "\n".join(lines)

    def verdict(key: str, group: Mapping[str, Any]) -> str:
        word, css = ("pass", "") if group["passes"] else ("fail", ' class="fail"')
        low = float(group["min_coverage"])
        return f'<td data-coverage-pass="{key}"{css}>{word} {low:.3f}</td>'

    def width(key: str, group: Mapping[str, Any]) -> str:
        return f'<td data-width="{key}">{float(group["mean_width"]):.3f}</td>'

    notes = "\n".join(
        f"<li><b>{e(METHOD_LABELS[m])}</b> (<code>{e(m)}</code>). {e(METHOD_NOTES[m])}</li>"
        for m in INTERVAL_METHODS
    )
    passing_methods = [
        METHOD_LABELS[m["method"]] for m in coverage["methods"] if m["passes_every_cell"]
    ]
    finding = (
        "Methods that pass in every setting: " + ", ".join(passing_methods) + "."
        if passing_methods
        else "No method passes in every setting."
    )
    return f"""<h2>Interval coverage</h2>
<p>A setting is one stratifier and one stage size. For each true score, the study draws
{coverage["subsets_per_cell"]:,} pairs of a new simulated model and a new stratified subset.
Every method sees the same pairs. A method covers a draw when its
{float(coverage["nominal_coverage"]):.0%} interval holds the model's full-set score. A
method passes a true score when its coverage is at least {pass_line:.3f}: the nominal
coverage minus 3 standard errors. {e(finding)}</p>
<ul>
{notes}
</ul>
{_legend([METHOD_LABELS[m] for m in INTERVAL_METHODS])}
<div class="panels">
{chr(10).join(panels)}
</div>
<h3>Lowest coverage across true scores</h3>
<p>"pass" means that the method passes at every true score in that setting. The number is
the lowest coverage. <code>coverage.csv</code> holds every cell.</p>
<div class="scroll">
<table>
<thead><tr><th>Stratifier, stage size</th>{header}</tr></thead>
<tbody>
{table(verdict)}
</tbody>
</table>
</div>
<h3>Mean interval width</h3>
<p>The mean of the upper bound minus the lower bound, over every true score and draw in
the setting.</p>
<div class="scroll">
<table>
<thead><tr><th>Stratifier, stage size</th>{header}</tr></thead>
<tbody>
{table(width)}
</tbody>
</table>
</div>"""


def html_report(
    document: Mapping[str, Any],
    coverage_cells: Sequence[Mapping[str, Any]],
    cost: CostEvidence,
    *,
    manifest_inputs: Mapping[str, str],
) -> bytes:
    rows, overall, policy = document["true_scores"], document["overall"], document["policy"]
    costs = [float(r["expected_cost_fraction"]["mean"]) for r in rows]
    threshold, alpha = float(document["threshold"]), float(document["alpha"])
    size, population = document["stage1_size"], document["population"]
    decisive = [(float(r["true_score"]), float(r["decisive_fraction"])) for r in rows]
    wrong = [(float(r["true_score"]), float(r["wrong_decision_rate"])) for r in rows]
    worst = max(rate for _, rate in wrong)
    wrong_max = max(0.1, max(float(r["wrong_rate_upper95"]) for r in rows))
    tail = alpha / 2
    e = html.escape
    table = "\n".join(
        f'<tr data-true-score="{e(str(r["true_score"]))}"><td>{e(str(r["true_score"]))}</td>'
        f"<td>{r['full_passes']}/{population}</td><td>{e(str(r['truth']))}</td>"
        f"<td>{r['draws']}</td><td>{r['stage1_go']}</td><td>{r['stage1_no_go']}</td>"
        f"<td>{r['escalate']}</td><td>{float(r['decisive_fraction']):.3f}</td>"
        f"<td>{r['wrong_decisions']}</td><td>{float(r['wrong_decision_rate']):.3f}</td>"
        f"<td>{float(r['wrong_rate_upper95']):.3f}</td>"
        f"<td>{float(r['mean_questions_graded']):.1f}</td>"
        f"<td>{float(r['expected_cost_fraction']['mean']):.3f}</td></tr>"
        for r in rows
    )
    limitations = "\n".join(f"<li>{e(str(item))}</li>" for item in document["limitations"])
    inputs = "\n".join(
        f"<li>{e(name)}: <code>{e(str(sha))}</code></li>" for name, sha in manifest_inputs.items()
    )
    decisive_chart = _chart(
        "Share of simulated models decided by the stage-1 probe",
        "Decisive fraction for each true score. It is near 0 close to the threshold and "
        "rises toward 1 far from it. The table below holds the same values.",
        decisive,
        series="decisive",
        y_max=1.0,
        y_label="decisive fraction",
        threshold=threshold,
    )
    wrong_title = (
        f"No true score has a wrong-decision rate above the one-tail bound {tail:.3f}"
        if worst <= tail
        else f"At least one true score has a wrong-decision rate above {tail:.3f}"
    )
    wrong_chart = _chart(
        wrong_title,
        f"Wrong-decision rate for each true score, with a line at the one-tail bound "
        f"{tail:.3f}. The highest rate is {worst:.3f}. The table below holds the same "
        "values and their 95% upper bounds.",
        wrong,
        series="wrong",
        y_max=wrong_max,
        y_label="wrong-decision rate",
        threshold=threshold,
        reference=(tail, f"one-tail bound {tail:.3f}"),
    )
    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Two-stage threshold decision</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>Two-stage threshold decision on simulated LiveCodeBench models</h1>
<p>Question: is the full-set score of a model at or above the threshold
{threshold:.2f}? A {size}-question probe decided {overall["decided_at_stage1"]} of
{overall["draws"]} simulated models. The census decided the rest. The highest
wrong-decision rate at any true score is {worst:.3f}. The expected token cost is
{min(costs):.3f} to {max(costs):.3f} of a full run, by true score.</p>
<ul class="facts">
<li>Threshold<b>{threshold:.2f}</b></li>
<li>Stage-1 size<b>{size} of {population}</b></li>
<li>Alpha spent<b>{alpha:.2f} + 0 (census)</b></li>
<li>Simulated models<b>{overall["draws"]}</b></li>
<li>Wrong decisions<b>{overall["wrong_decisions"]}</b></li>
</ul>
<h2>How the decision works</h2>
<ol>
<li>Select {size} questions with the <code>{e(str(document["stratifier"]))}</code>
selector. It uses reference grades only.</li>
<li>Grade the probe. Compute a {1 - alpha:.0%}
<code>{e(str(document["interval_method"]))}</code> interval for the full-set score.</li>
<li>If the lower bound is at or above the threshold, decide GO and stop.</li>
<li>If the upper bound is below the threshold, decide NO GO and stop.</li>
<li>Otherwise ESCALATE: grade the remaining questions and decide on the full set. The
census has no sampling error.</li>
</ol>
<p>Each simulated model has an exact full-set score: the smallest score at or above its
true score. A wrong decision differs from the decision on that full-set score. Only the
stage-1 interval can give a wrong decision. A valid interval keeps each true score's
wrong-decision rate at or below {tail:.3f}, because a wrong decision can only
go one way for a given model.</p>
<h2>Decisive fraction</h2>
{decisive_chart}
<h2>Wrong-decision rate</h2>
{wrong_chart}
<h2>Results for each true score</h2>
<div class="scroll">
<table>
<thead><tr><th>True score</th><th>Full set</th><th>Truth</th><th>Models</th>
<th>Stage-1 GO</th><th>Stage-1 NO GO</th><th>ESCALATE</th><th>Decisive fraction</th>
<th>Wrong</th><th>Wrong rate</th><th>Wrong rate 95% upper</th><th>Mean graded</th>
<th>Expected token cost</th></tr></thead>
<tbody>
{table}
</tbody>
</table>
</div>
<p>Expected token cost is the share of a full run under the mean estimate. The token cost
section below explains it.</p>
{_cost_section(cost, document)}
{_coverage_section(document["coverage"], coverage_cells)}
<h2>Limits</h2>
<ul>
{limitations}
</ul>
<h2>Provenance</h2>
<p>Policy <code>{e(str(policy["key"]))}</code>, frozen: {str(policy["frozen"]).lower()},
SHA-256 <code>{e(str(policy["sha256"]))}</code>. Output hashes are in
<code>manifest.json</code>.</p>
<ul>
{inputs}
</ul>
</main>
</body>
</html>
"""
    return body.encode("utf-8")


def build_outputs(
    loaded: LoadedPolicy,
    rows: Sequence[SimulatedDecision],
    summary: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    cost: CostEvidence,
    *,
    population: int,
    panel_name: str,
    panel_sha256: str,
) -> dict[str, bytes]:
    """All report files, with the manifest hashing the others."""
    document = summary_document(
        loaded, summary, coverage, cost, population=population, panel_sha256=panel_sha256
    )
    inputs = {loaded.file_name: loaded.sha256, panel_name: panel_sha256, **cost.tokens.files}
    code_root = Path(__file__).parent
    outputs = {
        "decisions.csv": decision_table(rows, population=population, cost=cost),
        "coverage.csv": coverage_table(coverage),
        "cost.csv": cost_table(cost),
        "question_tokens.csv": question_token_table(cost),
        "summary.json": encode_json(document),
        "report.html": html_report(document, coverage["cells"], cost, manifest_inputs=inputs),
    }
    manifest = {
        "schema_version": 1,
        "command": "threshold-decision",
        "analysis_version": ANALYSIS_VERSION,
        "mode": "simulated",
        "real_grades_used": False,
        "policy": {
            "file": loaded.file_name,
            "key": loaded.key,
            "sha256": loaded.sha256,
            "frozen": loaded.policy.frozen,
        },
        "inputs": {
            "reference_panel": {"file": panel_name, "sha256": panel_sha256},
            # Only the usage records of these files are read, never a grade.
            "token_counts": dict(cost.tokens.files),
        },
        "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
        "implementation_sha256": {
            name: _sha((code_root / name).read_bytes().replace(b"\r\n", b"\n"))
            for name in IMPLEMENTATION_FILES
        },
        "output_sha256": {name: _sha(data) for name, data in outputs.items()},
        "counts": {
            "simulated_models": len(rows),
            "true_scores": len(summary),
            "coverage_cells": len(coverage["cells"]),
            "cost_cells": len(cost.cells),
            "missing_token_counts": len(cost.tokens.missing),
        },
    }
    outputs["manifest.json"] = encode_json(manifest)
    return outputs
