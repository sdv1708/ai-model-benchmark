"""Build the one-page results summary from the recorded data.

Run from ``task2/``: ``uv run python tools/build_results_page.py``. The tool writes
``docs/results.md`` and its two charts. Every number of a result comes from a record
under ``docs/data``. A test rebuilds the page and compares it with the committed copy.
"""

import csv
import json
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.threshold_tables import markdown_table, percent

DOCS = Path(__file__).resolve().parents[2] / "docs"
DATA = DOCS / "data"
REPOSITORY = "https://github.com/sdv1708/ai-model-benchmark"
PROBE_TITLES = {
    "three_model": "Stratified probe, 3 reference models",
    "public_panel": "Stratified probe, public models",
    "random": "Random probe",
}
# The chart shows this range of distance, in steps of 0.01. Beyond it, both lines stay at 100%.
CHART_STEPS = 25
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e4e3df",
        "315": "#2a78d6",
        "1055": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "muted": "#c3c2b7",
        "grid": "#3a3a37",
        "315": "#3987e5",
        "1055": "#d95926",
    },
}
WIDTH, HEIGHT = 720, 380
LEFT, RIGHT, TOP, BOTTOM = 60, 24, 84, 54


def _json(folder: str) -> Any:
    return json.loads((DATA / folder / "summary.json").read_text(encoding="utf-8"))


def stage1_shares(arm: str) -> list[Fraction]:
    """The share decided at stage 1 for each 0.01 of distance, for both sides together.

    The probe is the public-panel probe. A step with no decision is an error.
    """
    path = DATA / "task2-panel-study" / "distance.csv"
    decided: dict[int, int] = {}
    total: dict[int, int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row["arm"], row["probe"]) == (arm, "public_panel"):
                step = round(float(row["distance_from"]) * 100)
                decided[step] = decided.get(step, 0) + int(row["stage1_decisions"])
                total[step] = total.get(step, 0) + int(row["decisions"])
    return [Fraction(decided[step], total[step]) for step in range(CHART_STEPS)]


def distance_chart(theme: str) -> str:
    """The share decided at stage 1 against the distance from the threshold, as SVG."""
    color = THEMES[theme]
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM

    def x(distance: float) -> float:
        return LEFT + plot_width * distance / (CHART_STEPS / 100)

    def y(share: float) -> float:
        return TOP + plot_height * (1 - share)

    font = 'font-family="system-ui, Segoe UI, Helvetica, Arial, sans-serif"'
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="Line chart. The larger benchmark decides closer to the threshold." {font}>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="8" fill="{color["surface"]}"/>',
        f'<text x="{LEFT}" y="28" font-size="16" font-weight="600" fill="{color["ink"]}">'
        "The larger benchmark decides closer to the threshold</text>",
    ]
    legend = (("315", "63 of 315 questions", LEFT), ("1055", "211 of 1,055 questions", LEFT + 200))
    for arm, title, left in legend:
        parts.append(
            f'<rect x="{left}" y="46" width="16" height="4" rx="2" fill="{color[arm]}"/>'
            f'<text x="{left + 24}" y="53" font-size="13" fill="{color["muted"]}">{title}</text>'
        )
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        parts.append(
            f'<line x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{y(share):.1f}" y2="{y(share):.1f}" '
            f'stroke="{color["grid"]}"/>'
            f'<text x="{LEFT - 8}" y="{y(share) + 4:.1f}" font-size="12" text-anchor="end" '
            f'fill="{color["muted"]}">{100 * share:.0f}%</text>'
        )
    for k in range(6):
        parts.append(
            f'<text x="{x(k / 20):.1f}" y="{HEIGHT - BOTTOM + 18}" font-size="12" '
            f'text-anchor="middle" fill="{color["muted"]}">{k / 20:.2f}</text>'
        )
    parts.append(
        f'<text x="{LEFT + plot_width / 2}" y="{HEIGHT - 14}" font-size="13" text-anchor="middle" '
        f'fill="{color["muted"]}">Distance of the full-set score from the threshold</text>'
        f'<text x="{LEFT}" y="{TOP - 10}" font-size="12" fill="{color["muted"]}">'
        "Share of decisions made by the probe alone</text>"
    )
    for arm in ("315", "1055"):
        points = " ".join(
            f"{x((k + 0.5) / 100):.1f},{y(float(share)):.1f}"
            for k, share in enumerate(stage1_shares(arm))
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color[arm]}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
    parts.append("</svg>\n")
    return "\n".join(parts)


def _thresholds() -> set[str]:
    """The thresholds of the recorded replay."""
    path = DATA / "task2-real-replay" / "cells.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["threshold"] for row in csv.DictReader(handle)}


def _points(values: Sequence[float]) -> str:
    """The smallest and the largest score change, in points of 100."""
    return f"{100 * min(values):.0f} to {100 * max(values):.0f}"


def page() -> str:
    """The results page as Markdown."""
    replay, study = _json("task2-real-replay"), _json("task2-panel-study")
    noise, prompt = _json("task2-aa-lcr-judge-rerun"), _json("task2-aa-lcr-judge-one-word")
    stratified = replay["grade_rules"]["primary"]["probes"]["stratified"]
    at, every = stratified["primary_threshold"], stratified["all_thresholds"]
    far = [r for r in replay["grade_rules"]["primary"]["by_distance"] if r["from"] >= 0.1]
    far_wrong, far_all = sum(r["wrong"] for r in far), sum(r["decisions"] for r in far)
    arms = {name: study["arms"][name] for name in ("315", "1055")}
    small, large = arms["315"], arms["1055"]
    threshold = replay["primary_threshold"]
    near = {
        name: sum(
            abs(Fraction(str(m["full_score"])) - Fraction(threshold)) < Fraction(1, 10)
            for m in study["model_results"]
            if m["arm"] == name
        )
        for name in arms
    }
    big = large["probes"]["public_panel"]["primary_threshold"]
    big_random = large["probes"]["random"]["primary_threshold"]

    sources = (
        ("#63", "315", "3 reference models", replay["criteria"]),
        ("#77", "315", "public models", small["criteria"]),
        ("#77", "1,055", "public models", large["criteria"]),
    )
    limits = replay["criteria"]
    criteria = markdown_table(
        (
            "Run",
            "Questions",
            "Strata from",
            f"Highest wrong-decision rate (limit {limits['wrong_decision_rate']['limit']:g})",
            f"Lowest coverage (limit {limits['coverage']['limit']:g})",
            f"Mean cost at {threshold} (below {limits['mean_cost_at_primary_threshold']['limit']:g})",
            "Mark",
        ),
        [
            (
                f"[{issue}]({REPOSITORY}/issues/{issue[1:]})",
                questions,
                strata,
                f"{c['wrong_decision_rate']['value']:.3f}",
                f"{c['coverage']['value']:.4f}",
                f"{c['mean_cost_at_primary_threshold']['value']:.3f}",
                "Pass" if all(v["passed"] for v in c.values()) else "Fail",
            )
            for issue, questions, strata, c in sources
        ],
        text=3,
    )
    rows = [
        (
            f"{arm['questions']:,}",
            PROBE_TITLES[name],
            percent(p["primary_threshold"]["stage1_share"]),
            f"{p['primary_threshold']['wrong']:,}",
            percent(p["all_thresholds"]["stage1_share"]),
            f"{p['all_thresholds']['wrong']:,}",
            f"{p['all_thresholds']['mean_question_fraction']:.3f}",
        )
        for arm in arms.values()
        for name, p in ((n, arm["probes"][n]) for n in PROBE_TITLES if n in arm["probes"])
    ]
    probes = markdown_table(
        (
            "Questions",
            "Probe",
            f"Decided at {threshold}",
            f"Wrong of {at['decisions']:,}",
            "Decided, all thresholds",
            f"Wrong of {every['decisions']:,}",
            "Mean cost in questions",
        ),
        rows,
        text=2,
    )
    small_random = small["probes"]["random"]["primary_threshold"]
    ranges = {
        name: next(r for r in arm["by_distance"]["public_panel"] if r["from"] == 0.05)
        for name, arm in arms.items()
    }
    shifts = [m["majority_shift"] for m in noise["models"]]
    changes = noise["agreement_with_saved_judgment"]["saved_incorrect_majority_correct"]
    again = prompt["decision_rule"]["incorrect_again"]
    chart = (
        "<picture>\n"
        '  <source media="(prefers-color-scheme: dark)" srcset="results-distance-dark.svg">\n'
        '  <img src="results-distance-light.svg" width="720" alt="Line chart of the share of '
        "decisions that the probe makes alone, by distance from the threshold. At 0.05 to below "
        f"0.10, the probe of 63 of 315 questions makes {percent(ranges['315']['stage1_share'])}, "
        f"and the probe of 211 of 1,055 questions makes {percent(ranges['1055']['stage1_share'])}."
        '">\n</picture>'
    )
    verdict = (
        "Every run passed every criterion of the frozen policy."
        if all(v["passed"] for *_, c in sources for v in c.values())
        else "A run failed a criterion of the frozen policy. The table marks it."
    )
    thresholds = sorted(_thresholds())
    return f"""# Results: a small probe for score-threshold decisions

**Question.** Does a model score at or above a threshold? A full benchmark run answers it, but it is expensive.

**Method.** Grade a small probe first. If its 95% interval is on one side of the threshold, stop with GO or NO GO. If not, grade the full set. The probe is stratified by question difficulty, which comes from other models only.

**Test.** [Policy v1](../task2/policies/threshold-v1.json) was frozen, with every pass criterion, before anyone computed a score of a test model. The test models are {replay["models"]} public LiveCodeBench models from {replay["developer_groups"]} developers. Each model gets {replay["seeds"]:,} different probes. Each probe decides at {len(thresholds)} thresholds from {thresholds[0]} to {thresholds[-1]}.

## Headline

- **{small["questions"]} questions (#63, the preregistered unseen-model test):** over all thresholds, the mean cost was {percent(every["mean_cost_fraction"]["mean"])} of the estimated tokens of a full run, with {every["wrong"]:,} wrong of {every["decisions"]:,} decisions. At 0.10 or more from the threshold, {far_wrong} of {far_all:,} decisions were wrong.
- **{large["questions"]:,} questions (#77, strata from other public models):** at threshold {threshold}, a probe of {large["stage1_size"]} questions made {percent(big["stage1_share"])} of {big["decisions"]:,} decisions. Full runs for the other decisions included, the mean cost was {percent(big["mean_question_fraction"])} of the questions. Wrong decisions: {big["wrong"]}. A random probe of the same size made {big_random["wrong"]} wrong decisions.
- **Hard case:** at threshold {threshold} on {small["questions"]} questions, the probe made {percent(at["stage1_share"])} of the decisions, at {percent(at["mean_cost_fraction"]["mean"])} of the tokens. There, {near["315"]} of {replay["models"]} models score within 0.10 of the threshold.

## Pass criteria

{verdict}

{criteria}

A cost is a share of a full run. The 315-question costs are estimated tokens. The 1,055-question cost is in questions, because the public file has no token counts.

## Stratified probe against random probe

{probes}

- **Larger reference panel:** the strata come from the public models of other developers, never from the developer of the test model. Wrong decisions fall from {small["probes"]["three_model"]["all_thresholds"]["wrong"]:,} to {small["probes"]["public_panel"]["all_thresholds"]["wrong"]:,}. The cost does not fall.
- **Where random is better:** at {threshold} on {small["questions"]} questions, the random probe decides more ({percent(small_random["stage1_share"])}). It also makes more wrong decisions ({small_random["wrong"]}). In each arm, it decides more at less than 0.05 from the threshold.

## Benchmark size

{chart}

At 0.05 to below 0.10 from the threshold, the stratified probe decides {percent(ranges["315"]["stage1_share"])} with 63 of 315 questions and {percent(ranges["1055"]["stage1_share"])} with 211 of 1,055. [`distance.csv`](data/task2-panel-study/distance.csv) holds the plotted values.

## LLM-judge reliability (AA-LCR)

- The judge graded {noise["disagreement"]["answers"]} saved answers {len(noise["models"][0]["pass_scores"])} more times. The verdicts of {noise["disagreement"]["not_unanimous"]} answers ({percent(noise["disagreement"]["share"])}) were not all equal. No GO or NO GO decision at {noise["decisions"]["threshold"]:.2f} changed.
- The new scores were {_points(shifts)} points above the saved scores. All {changes} changed verdicts went from INCORRECT to CORRECT.
- A control run with the old one-word prompt made {again} of the {changes} INCORRECT again. By the rule fixed before that run, the prompt explains most of the shift. {again} is the lowest count for that conclusion, and one control run does not separate the prompt from the date and the endpoint.

## Limits

- The {replay["models"]} models are not independent, and the {replay["seeds"]:,} probes of one model reuse the same saved grades. The test measures question selection, not the variance of new answers.
- The average over all thresholds includes thresholds far from a score, which are easy.
- The token costs are estimates from the saved answers of 3 models. No live inference saving is measured yet.
- The two sizes differ also in the questions, the probe size, and the scores. Within 0.10 of {threshold} there are {near["315"]} models on 315 questions and {near["1055"]} on 1,055.
- The #77 settings were frozen, but its code was written after the #63 result was known. The code chose two points that the policy leaves open.
- The random probe uses another interval method than the stratified probe, as the policy fixes. The gap is not from question selection alone.
- The probe answers a threshold question. No fixed smaller question set is validated as a score estimator.

## Evidence

- Reports: [unseen-model replay](data/task2-real-replay/report.md), [reference-panel study](data/task2-panel-study/report.md), [judge noise](data/task2-aa-lcr-judge-rerun/report.md), [judge-prompt control](data/task2-aa-lcr-judge-one-word/report.md).
- Code and method: [benchmark reference](../task2/README.md). EvalScope adapters: [evalscope-pruning](https://github.com/sdv1708/evalscope-pruning).
- Source of the public grades: [LiveCodeBench](https://livecodebench.github.io/performances_generation.json). The repository holds derived values only.
- [`build_results_page.py`](../task2/tools/build_results_page.py) builds this page from the recorded data, and a test checks it.
"""


def outputs() -> dict[str, bytes]:
    """Each output file of the page, by its name under ``docs``."""
    files = {"results.md": page()}
    files |= {f"results-distance-{theme}.svg": distance_chart(theme) for theme in THEMES}
    return {name: text.encode("utf-8") for name, text in files.items()}


if __name__ == "__main__":
    for name, data in outputs().items():
        (DOCS / name).write_bytes(data)
        print(f"Wrote {DOCS / name}")
