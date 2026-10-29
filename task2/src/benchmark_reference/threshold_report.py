"""Decision table, summary, self-contained HTML report, and manifest bytes.

Every output is a deterministic function of the policy file and the reference
panel: no timestamps, absolute paths, or environment values. Two runs with the
same inputs therefore give byte-identical outputs and manifests.
"""

import csv
import hashlib
import html
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.threshold_policy import LoadedPolicy, alpha_spending
from benchmark_reference.threshold_study import SimulatedDecision

ANALYSIS_VERSION = "threshold-two-stage-v1"
OUTPUT_NAMES = ("decisions.csv", "summary.json", "report.html", "manifest.json")
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
)
DRAFT_LIMITATION = "The policy is a draft. It is not frozen and must not be used on real grades."
IMPLEMENTATION_FILES = (
    "models.py",
    "pruning.py",
    "uncertainty.py",
    "threshold_policy.py",
    "threshold_simulation.py",
    "two_stage.py",
    "threshold_study.py",
    "threshold_report.py",
    "threshold_cli.py",
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
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decision_table(rows: Sequence[SimulatedDecision], *, population: int) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_COLUMNS)
    for row in rows:
        result = row.result
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
            )
        )
    return stream.getvalue().encode("utf-8")


def summary_document(
    loaded: LoadedPolicy,
    summary: Sequence[Mapping[str, Any]],
    *,
    population: int,
    panel_sha256: str,
) -> dict[str, Any]:
    policy = loaded.policy
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


def html_report(document: Mapping[str, Any], *, manifest_inputs: Mapping[str, str]) -> bytes:
    rows, overall, policy = document["true_scores"], document["overall"], document["policy"]
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
        f"<td>{float(r['mean_questions_graded']):.1f}</td></tr>"
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
wrong-decision rate at any true score is {worst:.3f}.</p>
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
<li>Grade the probe. Compute a {1 - alpha:.0%} pooled exact hypergeometric interval for
the full-set score.</li>
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
<th>Wrong</th><th>Wrong rate</th><th>Wrong rate 95% upper</th><th>Mean graded</th></tr></thead>
<tbody>
{table}
</tbody>
</table>
</div>
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
    *,
    population: int,
    panel_name: str,
    panel_sha256: str,
) -> dict[str, bytes]:
    """All report files, with the manifest hashing the other three."""
    document = summary_document(loaded, summary, population=population, panel_sha256=panel_sha256)
    inputs = {loaded.file_name: loaded.sha256, panel_name: panel_sha256}
    code_root = Path(__file__).parent
    outputs = {
        "decisions.csv": decision_table(rows, population=population),
        "summary.json": encode_json(document),
        "report.html": html_report(document, manifest_inputs=inputs),
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
        "inputs": {"reference_panel": {"file": panel_name, "sha256": panel_sha256}},
        "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
        "implementation_sha256": {
            name: _sha((code_root / name).read_bytes().replace(b"\r\n", b"\n"))
            for name in IMPLEMENTATION_FILES
        },
        "output_sha256": {name: _sha(data) for name, data in outputs.items()},
        "counts": {"simulated_models": len(rows), "true_scores": len(summary)},
    }
    outputs["manifest.json"] = encode_json(manifest)
    return outputs
