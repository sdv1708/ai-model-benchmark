"""Decision tables, summary, self-contained HTML report, and manifest bytes.

One run covers every benchmark section of the policy file. Each benchmark gets
its own folder of tables and its own report section. Every section has the same
charts and tables, so a reader can compare the benchmarks side by side.

Every output is a deterministic function of the policy file and the reference
panels: no timestamps, absolute paths, or environment values. Two runs with the
same inputs therefore give byte-identical outputs and manifests.
"""

import csv
import hashlib
import html
import io
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.threshold_benchmarks import AA_LCR, BENCHMARKS, LIVE_CODE_BENCH, Benchmark
from benchmark_reference.threshold_cost import (
    CostEvidence,
    run_tokens,
)
from benchmark_reference.threshold_error_rate import FLIP, GENERATORS, RASCH
from benchmark_reference.threshold_intervals import (
    BONFERRONI,
    BOOTSTRAP,
    BOOTSTRAP_REPLICATES,
    INTERVAL_METHODS,
    POOLED_EXACT,
    WILSON,
)
from benchmark_reference.threshold_policy import LoadedPolicy, ThresholdPolicy, alpha_spending
from benchmark_reference.threshold_study import SimulatedDecision

ANALYSIS_VERSION = "threshold-two-stage-v5"
BENCHMARK_OUTPUTS = (
    "decisions.csv",
    "coverage.csv",
    "cost.csv",
    "question_tokens.csv",
    "error_rate.csv",
    "error_rate_settings.csv",
    "error_rate_combined.csv",
)
SHARED_OUTPUTS = ("summary.json", "report.html", "manifest.json")
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
GENERATOR_LABELS = {RASCH: "Rasch", FLIP: "Reference flip"}
GENERATOR_NOTES = {
    RASCH: "A Rasch-style model. Each question passes with odds from its reference pass "
    "rate, conditioned on the exact pass count of the chosen true score.",
    FLIP: "The real grades of one reference model, with random grades flipped until the "
    "pass count reaches the chosen true score. Draws rotate through the reference models.",
}
# The line dash and the marker shape give each method a second encoding beside color.
_DASHES = ("", "7 4", "2 3", "9 3 2 3")
LIMITATIONS = (
    "Simulated models only. No real model grades are used in this run.",
    "The generator takes question difficulty from the reference grades. The strata of "
    "difficulty_stratified, response_stratified, and length_difficulty_stratified use "
    "the same grades, so they match the simulated difficulty exactly. This favors those "
    "stratifiers. The error-rate study adds a second generator that does not use this "
    "difficulty model.",
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
    "The coverage study uses the same generator as the decision study, so the strata "
    "that use reference difficulty have the same advantage. The error-rate study uses "
    "this generator and a second one.",
    "The reference-flip generator starts from the real grades of a reference model. The "
    "strata use the grades of the same models, so a reference-flip model is not unseen. It "
    "tests a real pattern of grades across questions, not a new model.",
    "The distance to decide (d95) uses the share of draws decided at stage 1. With 1,000 "
    "draws, that share has a standard error of about 0.007 near 0.95, so d95 can move by "
    "one grid step between seeds. It holds only at the true scores of the grid.",
    "The distance to decide uses the grid true score, not the full-set score. The full-set "
    "score is the smallest score at or above the grid value. It can be up to one question "
    "above the grid value.",
    "In the error-rate study, every stratifier and stage size sees the same simulated models "
    "and selection seeds. The comparison of two settings is therefore paired. The settings "
    "are not independent of each other.",
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
# The judge-noise limit of a judge-graded benchmark. The report puts it beside every
# result of that benchmark.
JUDGE_NOISE = (
    "Judge noise is not measured. An LLM judge grades each answer. The saved data has one "
    "judgment for each answer. The simulated grades have no judge noise, so these results "
    "do not include it. A real decision also carries the error of the judge."
)
BENCHMARK_LIMITATIONS: Mapping[str, tuple[str, ...]] = {
    LIVE_CODE_BENCH: (
        "LiveCodeBench grades come from the test results of each answer, not from a judge.",
        "Output tokens are most of the LiveCodeBench cost. The answer length depends on the "
        "model, so the low and high token estimates are far apart. The cost fraction changes "
        "much less, because each estimate divides by its own full run.",
    ),
    AA_LCR: (
        JUDGE_NOISE,
        "The simulated AA-LCR models take their difficulty from the AA-LCR reference grades. "
        "The question metadata gives the input length and the source document count of each "
        "question. This metadata defines the strata of both AA-LCR stratifiers. It does not "
        "change the simulated pass probability. The metadata_stratified strata therefore do "
        "not share the difficulty of the generator.",
        "AA-LCR has 100 questions. At the smallest stage sizes, most strata have one sampled "
        "question, and the bootstrap adds no width for such a stratum.",
        "Input tokens depend on the documents of the question. Across the reference models, "
        "the input count of one question differs only by the tokenizer, so most of the cost "
        "does not depend on the model.",
    ),
}
IMPLEMENTATION_FILES = (
    "models.py",
    "pruning.py",
    "long_context.py",
    "threshold_benchmarks.py",
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
    "threshold_error_rate.py",
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
_ERROR_COLUMNS = (
    "generator",
    "stratifier",
    "stage_size",
    "true_score",
    "full_passes",
    "truth",
    "method",
    "draws",
    "stage1_go",
    "stage1_no_go",
    "escalated",
    "decided_share",
    "wrong",
    "wrong_rate",
    "passes",
    "expected_cost_fraction_low",
    "expected_cost_fraction_mean",
    "expected_cost_fraction_high",
)
_ERROR_SETTING_COLUMNS = (
    "generator",
    "stratifier",
    "stage_size",
    "method",
    "true_scores",
    "draws",
    "wrong",
    "max_wrong_rate",
    "max_wrong_rate_true_score",
    "passes",
    "failing_true_scores",
    "decided_share",
    "d95_below",
    "d95_above",
    "d95",
    "mean_expected_cost_fraction",
)
_ERROR_COMBINED_COLUMNS = (
    "stratifier",
    "stage_size",
    "method",
    "passes_both_generators",
    "failing_generators",
    "max_wrong_rate",
    "d95_below",
    "d95_above",
    "d95",
    *(f"d95_{g}" for g in GENERATORS),
    *(f"mean_expected_cost_fraction_{g}" for g in GENERATORS),
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


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """Every study of one policy section, ready for the report.

    ``summary`` holds one record for each true score; ``coverage`` is the
    coverage summary with its cells; ``error_rate`` is the error-rate summary
    with its cells.
    """

    policy: ThresholdPolicy
    panel_file: str
    panel_sha256: str
    population: int
    rows: tuple[SimulatedDecision, ...]
    summary: Sequence[Mapping[str, Any]]
    coverage: Mapping[str, Any]
    cost: CostEvidence
    error_rate: Mapping[str, Any]

    @property
    def benchmark(self) -> Benchmark:
        return BENCHMARKS[self.policy.benchmark]


def output_names(benchmarks: Iterable[str]) -> tuple[str, ...]:
    """Each benchmark folder of tables, then the shared files. The manifest is last."""
    return (
        *(f"{b}/{name}" for b in benchmarks for name in BENCHMARK_OUTPUTS),
        *SHARED_OUTPUTS,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ratio_text(ratio: float | None) -> str:
    """An input ratio with 3 decimals, or a dash when no question has a ratio."""
    return "-" if ratio is None else f"{ratio:.3f}"


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


def _optional(value: float | None) -> str:
    """A value with 6 decimals, or an empty cell for no value."""
    return "" if value is None else f"{value:.6f}"


def error_rate_table(error: Mapping[str, Any]) -> bytes:
    """One row for each generator, stratifier, stage size, true score, and method."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_ERROR_COLUMNS)
    for cell in error["cells"]:
        fraction = cell["expected_cost_fraction"]
        writer.writerow(
            (
                *(cell[name] for name in _ERROR_COLUMNS[:11]),
                f"{cell['decided_share']:.6f}",
                cell["wrong"],
                f"{cell['wrong_rate']:.6f}",
                int(cell["passes"]),
                *(
                    ("", "", "")
                    if fraction is None
                    else (f"{fraction[k]:.6f}" for k in ("low", "mean", "high"))
                ),
            )
        )
    return stream.getvalue().encode("utf-8")


def error_rate_settings_table(error: Mapping[str, Any]) -> bytes:
    """One row for each generator, stratifier, stage size, and method.

    An empty d95 cell means that the probe does not reach the 95% decide level
    on that side within the grid of true scores.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_ERROR_SETTING_COLUMNS)
    for setting in error["settings"]:
        writer.writerow(
            (
                *(setting[name] for name in _ERROR_SETTING_COLUMNS[:7]),
                f"{setting['max_wrong_rate']:.6f}",
                setting["max_wrong_rate_true_score"],
                int(setting["passes"]),
                " ".join(setting["failing_true_scores"]),
                f"{setting['decided_share']:.6f}",
                *(_optional(setting[k]) for k in ("d95_below", "d95_above", "d95")),
                _optional(setting["mean_expected_cost_fraction"]),
            )
        )
    return stream.getvalue().encode("utf-8")


def error_rate_combined_table(error: Mapping[str, Any]) -> bytes:
    """One row for each stratifier, stage size, and method, across both generators.

    A setting passes when it passes for every generator. Its d95 is the largest
    d95 of the generators. An empty d95 cell means that a generator does not
    reach the 95% decide level inside the grid.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_ERROR_COMBINED_COLUMNS)
    for setting in error["combined"]:
        writer.writerow(
            (
                setting["stratifier"],
                setting["stage_size"],
                setting["method"],
                int(setting["passes_both_generators"]),
                " ".join(setting["failing_generators"]),
                f"{setting['max_wrong_rate']:.6f}",
                *(_optional(setting[k]) for k in ("d95_below", "d95_above", "d95")),
                *(_optional(setting["d95_by_generator"].get(g)) for g in GENERATORS),
                *(
                    _optional(setting["mean_expected_cost_fraction_by_generator"].get(g))
                    for g in GENERATORS
                ),
            )
        )
    return stream.getvalue().encode("utf-8")


def _points_text(distance: float | None) -> str:
    """A distance as whole points of score: 0.12 is 12 points."""
    return "not reached" if distance is None else f"{distance * 100:.0f}"


def _policy_setting(error: Mapping[str, Any], policy: ThresholdPolicy) -> Mapping[str, Any] | None:
    key = (policy.stratifier, policy.stage1_size, policy.interval_method)
    return next(
        (c for c in error["combined"] if (c["stratifier"], c["stage_size"], c["method"]) == key),
        None,
    )


def distance_claim(error: Mapping[str, Any], policy: ThresholdPolicy) -> dict[str, Any]:
    """The plain-language d95 sentence for the policy probe, with its evidence."""
    size, threshold = policy.stage1_size, policy.threshold
    scores = policy.error_true_scores
    grid = f"{scores[0]:.2f} to {scores[-1]:.2f}"
    setting = _policy_setting(error, policy)
    claim: dict[str, Any] = {
        "stage_size": size,
        "stratifier": policy.stratifier,
        "method": policy.interval_method,
        "threshold": threshold,
        "true_score_grid": [scores[0], scores[-1]],
    }
    if setting is None:
        return {
            **claim,
            "d95": None,
            "d95_below": None,
            "d95_above": None,
            "d95_by_generator": {},
            "passes_both_generators": None,
            "smallest_stage_size_with_d95": None,
            "sentence": f"The error-rate study does not include the {size}-question probe of "
            "the policy.",
            "smallest_sentence": "",
            "error_verdict": "",
        }
    by_generator = setting["d95_by_generator"]
    d95 = setting["d95"]
    if d95 is None:
        # The farthest grid distance on each side: a side that never reaches 95% needs more.
        limit = Fraction(str(threshold))
        grid_points = [Fraction(str(score)) for score in scores]
        reach = {
            "below": [limit - p for p in grid_points if p < limit],
            "above": [p - limit for p in grid_points if p >= limit],
        }

        def side(name: str, where: str) -> str:
            found = setting[f"d95_{name}"]
            if found is not None:
                return f"{where} the threshold, it needs {_points_text(found)} points."
            if not reach[name]:
                return f"{where} the threshold, the grid has no true score."
            farthest = _points_text(float(max(reach[name])))
            return f"{where} the threshold, it needs more than {farthest} points."

        sentence = (
            f"A {size}-question probe does not decide at stage 1 in 95% of simulated runs at "
            f"every grid distance from the {threshold:.2f} threshold, for true scores {grid}. "
            f"{side('below', 'Below')} {side('above', 'Above')}"
        )
    else:
        detail = ", ".join(
            f"{GENERATOR_LABELS.get(g, g)} {_points_text(d)} points"
            for g, d in by_generator.items()
        )
        sentence = (
            f"A {size}-question probe decides at stage 1 for every model that is at least "
            f"{_points_text(d95)} points ({d95:.2f}) from the {threshold:.2f} threshold. This "
            f"holds in at least 95% of simulated runs for both generators, at true scores "
            f"{grid} ({detail})."
        )
    reached = sorted(
        (
            c
            for c in error["combined"]
            if (c["stratifier"], c["method"]) == (policy.stratifier, policy.interval_method)
            and c["d95"] is not None
        ),
        key=lambda c: c["stage_size"],
    )
    if not reached:
        smallest = None
        smallest_sentence = (
            "No studied probe size with this stratifier and method reaches d95 inside the grid."
        )
    else:
        smallest = reached[0]["stage_size"]
        smallest_sentence = (
            f"The smallest studied probe with this stratifier and method that reaches d95 has "
            f"{smallest} questions: d95 is {_points_text(reached[0]['d95'])} points."
        )
    line = float(error["pass_line"])
    if setting["passes_both_generators"]:
        verdict = (
            f"Its wrong-decision rate is at most the pass line {line:.3f} at every true score "
            "for both generators."
        )
    else:
        failing = ", ".join(GENERATOR_LABELS.get(g, g) for g in setting["failing_generators"])
        verdict = (
            f"Its wrong-decision rate is above the pass line {line:.3f} at one or more true "
            f"scores for: {failing}."
        )
    return {
        **claim,
        "d95": d95,
        "d95_below": setting["d95_below"],
        "d95_above": setting["d95_above"],
        "d95_by_generator": dict(by_generator),
        "passes_both_generators": setting["passes_both_generators"],
        "smallest_stage_size_with_d95": smallest,
        "sentence": sentence,
        "smallest_sentence": smallest_sentence,
        "error_verdict": verdict,
    }


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


def _input_ratio(cost: CostEvidence) -> float | None:
    """The largest ratio of the most to the fewest input tokens of one question.

    The ratio compares the reference models that have a count. A question with a
    zero input count has no ratio. None means that no question has a ratio.
    """
    ratios = []
    for index in cost.tokens.questions:
        inputs = [c[index].input for c in cost.tokens.counts.values() if index in c]
        if inputs and min(inputs) > 0:
            ratios.append(Fraction(max(inputs), min(inputs)))
    return round(float(max(ratios)), 6) if ratios else None


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
            "input_tokens_max_model_ratio": _input_ratio(cost),
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


def benchmark_document(run: BenchmarkRun) -> dict[str, Any]:
    """The summary of one benchmark section."""
    policy, cost, benchmark = run.policy, run.cost, run.benchmark
    point = {cell.true_score: cell for cell in cost.point}
    summary = [
        {
            **row,
            "expected_tokens": point[row["true_score"]].expected.rounded(1),
            "expected_cost_fraction": point[row["true_score"]].fraction.rounded(6),
        }
        for row in run.summary
    ]
    draws = sum(row["draws"] for row in summary)
    wrong = sum(row["wrong_decisions"] for row in summary)
    decided = sum(row["decided_at_stage1"] for row in summary)
    return {
        "benchmark": policy.benchmark,
        "title": benchmark.title,
        "judge_graded": benchmark.judge_graded,
        "judge_noise": JUDGE_NOISE if benchmark.judge_graded else None,
        "reference_panel_sha256": run.panel_sha256,
        "population": run.population,
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
        "coverage": {key: value for key, value in run.coverage.items() if key != "cells"},
        "cost": cost_document(
            cost, run.coverage, stratifier=policy.stratifier, method=policy.interval_method
        ),
        "error_rate": {
            **{key: value for key, value in run.error_rate.items() if key != "cells"},
            "true_scores": list(policy.error_true_scores),
            "stage_sizes": list(policy.error_stage_sizes),
            "claim": distance_claim(run.error_rate, policy),
        },
        "limitations": list(BENCHMARK_LIMITATIONS.get(policy.benchmark, ())),
    }


def summary_document(loaded: LoadedPolicy, runs: Sequence[BenchmarkRun]) -> dict[str, Any]:
    return {
        "analysis_version": ANALYSIS_VERSION,
        "mode": "simulated",
        "policy": {"key": loaded.key, "sha256": loaded.sha256, "frozen": loaded.frozen},
        "benchmarks": [benchmark_document(run) for run in runs],
        "limitations": [*LIMITATIONS, *(() if loaded.frozen else (DRAFT_LIMITATION,))],
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
h3 { font-size: 1.05rem; margin: 24px 0 6px; }
h4 { font-size: 0.95rem; margin: 20px 0 6px; }
section { border-top: 2px solid var(--line); margin-top: 40px; }
.claim { border-left: 4px solid var(--decisive); background: var(--panel);
  padding: 8px 12px; font-weight: 600; }
.judge-noise { border-left: 4px solid var(--mark); background: var(--panel);
  padding: 6px 10px; font-size: 0.92em; }
"""


def _chart(
    title: str,
    description: str,
    points: Sequence[tuple[float, float]],
    *,
    key: str,
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

    ids = f"{key}-{series}"
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-chart="{series}" '
        f'aria-labelledby="{ids}-t {ids}-d">',
        f'<title id="{ids}-t">{html.escape(title)}</title>',
        f'<desc id="{ids}-d">{html.escape(description)}</desc>',
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
    benchmark: str,
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
    ids = e(f"{benchmark}-{key}")
    lows = {
        m: min(float(c["coverage"]) for c in cells if c["method"] == m) for m in INTERVAL_METHODS
    }
    description = (
        "Coverage for each true score and method. Lowest coverage: "
        + "; ".join(f"{METHOD_LABELS[m]} {lows[m]:.3f}" for m in INTERVAL_METHODS)
        + f". The dashed line is the pass line {pass_line:.3f}."
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-chart="coverage" '
        f'data-coverage="{e(key)}" aria-labelledby="{ids}-t {ids}-d">',
        f'<title id="{ids}-t">{e(title)}</title>',
        f'<desc id="{ids}-d">{e(description)}</desc>',
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


def _cost_chart(cost: CostEvidence, *, key: str, policy_size: int) -> str:
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
        f'<svg viewBox="0 0 {width} {height}" role="img" data-chart="cost" data-cost="curve" '
        f'aria-labelledby="{e(key)}-cost-t {e(key)}-cost-d">',
        f'<title id="{e(key)}-cost-t">{e(title)}</title>',
        f'<desc id="{e(key)}-cost-d">{e(description)}</desc>',
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


def _judge_note(document: Mapping[str, Any]) -> str:
    """The judge-noise limit for a judge-graded benchmark; empty for the others."""
    if document["judge_noise"] is None:
        return ""
    return f'<p class="judge-noise">{html.escape(str(document["judge_noise"]))}</p>'


def _cost_section(cost: CostEvidence, document: Mapping[str, Any]) -> str:
    e = html.escape
    note = _judge_note(document)
    key = str(document["benchmark"])
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
    # The groups are in panel stratifier order, then stage-size order.
    settings = list(dict.fromkeys((s, n) for s, n, _ in groups))
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
    ratio_text = _ratio_text(full["input_tokens_max_model_ratio"])
    return f"""<h3>Token cost</h3>
{note}
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
<li>Largest input ratio between models<b data-input-ratio="{e(key)}">{ratio_text}</b></li>
<li>Missing counts<b>{len(missing)}</b></li>
</ul>
<p>The largest input ratio between models compares, for one question, the most and the
fewest input tokens across the reference models. A ratio near 1 means that the input
cost depends on the question and not on the model.</p>
<h4>Expected cost against stage-1 size</h4>
{note}
<p>Each line is one band of true scores; each true score in a band has equal weight. The
marker is the mean estimate and the whisker spans the low, mean, and high estimates. The dashed
diagonal is the cost when no run escalates.</p>
{_legend([f"true score {label}" for label in labels])}
{_cost_chart(cost, key=key, policy_size=policy_size)}
<h4>Expected cost for each band</h4>
{note}
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
<h4>Expected cost for each interval method</h4>
{note}
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


def _coverage_section(document: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]) -> str:
    e = html.escape
    coverage = document["coverage"]
    note = _judge_note(document)
    pass_line = float(coverage["pass_line"])
    # All panels use one y-range, so a reader can compare them at a glance.
    y_min = min(0.85, math.floor(min(float(c["coverage"]) for c in cells) * 20) / 20)
    groups = {(g["stratifier"], g["stage_size"], g["method"]): g for g in coverage["groups"]}
    # The groups are in panel stratifier order, then stage-size order.
    settings = list(dict.fromkeys((s, n) for s, n, _ in groups))
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
            benchmark=str(document["benchmark"]),
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
    return f"""<h3>Interval coverage</h3>
{note}
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
<h4>Lowest coverage across true scores</h4>
{note}
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
<h4>Mean interval width</h4>
{note}
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


def _grid_ticks(xs: Sequence[float]) -> list[float]:
    """Every 0.10 of a fine grid; every point of a grid with fewer than 8 points."""
    if len(xs) < 8:
        return list(xs)
    return [x for x in xs if round(x * 100) % 10 == 0]


def _error_chart(
    method: str,
    cells: Sequence[Mapping[str, Any]],
    *,
    benchmark: str,
    title: str,
    y_max: float,
    alpha: float,
    pass_line: float,
    threshold: float,
) -> str:
    """Wrong-decision rate against true score for one method: one line for each generator."""
    width, height, left, right, top, bottom = 340, 230, 52, 20, 12, 40
    xs = sorted({float(c["true_score"]) for c in cells})
    x_low, x_high = xs[0], xs[-1]
    span = x_high - x_low or 1.0

    def px(x: float) -> float:
        return left + (x - x_low) / span * (width - left - right)

    def py(y: float) -> float:
        return top + (1 - min(y, y_max) / y_max) * (height - top - bottom)

    e = html.escape
    ids = e(f"{benchmark}-error-{method}")
    highs = {
        g: max((float(c["wrong_rate"]) for c in cells if c["generator"] == g), default=0.0)
        for g in GENERATORS
    }
    description = (
        f"{METHOD_LABELS[method]}: wrong-decision rate for each true score and generator. "
        "Highest rate: "
        + "; ".join(f"{GENERATOR_LABELS[g]} {highs[g]:.3f}" for g in GENERATORS)
        + f". Dashed lines: alpha {alpha:.2f} and the pass line {pass_line:.3f}."
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-chart="error" '
        f'data-error="{e(method)}" aria-labelledby="{ids}-t {ids}-d">',
        f'<title id="{ids}-t">{e(title)}</title>',
        f'<desc id="{ids}-d">{e(description)}</desc>',
        f'<line class="axis" x1="{left}" y1="{py(0):.1f}" x2="{width - right}" y2="{py(0):.1f}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{py(0):.1f}"/>',
    ]
    for tick in (0.0, y_max / 2, y_max):
        parts.append(
            f'<text x="{left - 6}" y="{py(tick) + 4:.1f}" text-anchor="end">{tick:.3f}</text>'
        )
    for x in _grid_ticks(xs):
        parts.append(
            f'<text x="{px(x):.1f}" y="{py(0) + 15:.1f}" text-anchor="middle">{x:.2f}</text>'
        )
    if x_low <= threshold <= x_high:
        parts.append(
            f'<line class="mark" x1="{px(threshold):.1f}" y1="{top}" '
            f'x2="{px(threshold):.1f}" y2="{py(0):.1f}"/>'
            f'<text class="halo" x="{px(threshold) - 4:.1f}" y="{top + 12}" '
            f'text-anchor="end">t {threshold:.2f}</text>'
        )
    for value, text, dy in (
        (alpha, f"alpha {alpha:.2f}", 14),
        (pass_line, f"pass line {pass_line:.3f}", -4),
    ):
        parts.append(
            f'<line class="mark" x1="{left}" y1="{py(value):.1f}" x2="{width - right}" '
            f'y2="{py(value):.1f}"/>'
            f'<text class="halo" x="{width - right}" y="{py(value) + dy:.1f}" '
            f'text-anchor="end">{e(text)}</text>'
        )
    for slot, generator in enumerate(GENERATORS, start=1):
        mine = sorted(
            (c for c in cells if c["generator"] == generator), key=lambda c: float(c["true_score"])
        )
        path = " ".join(
            f"{px(float(c['true_score'])):.1f},{py(float(c['wrong_rate'])):.1f}" for c in mine
        )
        parts.append(_series_line(slot, path))
        # On a fine grid, markers only where a draw was wrong, so a flat line stays readable.
        parts.extend(
            _marker(
                slot,
                px(float(c["true_score"])),
                py(float(c["wrong_rate"])),
                f"{GENERATOR_LABELS[generator]}, true score {c['true_score']}: "
                f"{c['wrong']} wrong of {c['draws']} ({float(c['wrong_rate']):.3f}), "
                f"decided at stage 1 {float(c['decided_share']):.3f}",
            )
            for c in mine
            if c["wrong"] or len(mine) < 8
        )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 6}" text-anchor="middle">'
        "true full-set score</text>"
        f'<text transform="translate(12 {(top + py(0)) / 2:.1f}) rotate(-90)" '
        'text-anchor="middle">wrong-decision rate</text></svg>'
    )
    return "\n".join(parts)


def _distance_chart(
    stratifier: str,
    settings: Sequence[Mapping[str, Any]],
    *,
    benchmark: str,
    title: str,
    population: int,
    policy_size: int,
    y_max: float,
) -> str:
    """d95 in points against stage-1 size: one line for each generator.

    A stage size whose probe does not reach the decide level has no marker, and
    the line breaks there.
    """
    width, height, left, right, top, bottom = 340, 230, 52, 20, 12, 40
    sizes = sorted({int(s["stage_size"]) for s in settings})

    def px(n: float) -> float:
        return left + n / population * (width - left - right)

    def py(y: float) -> float:
        return top + (1 - min(y, y_max) / y_max) * (height - top - bottom)

    e = html.escape
    ids = e(f"{benchmark}-distance-{stratifier}")
    description = (
        "d95 in points for each stage size and generator: "
        + "; ".join(
            f"{GENERATOR_LABELS[g]} "
            + ", ".join(
                f"{s['stage_size']} questions {_points_text(s['d95'])}"
                for s in settings
                if s["generator"] == g
            )
            for g in GENERATORS
        )
        + ". A stage size with no 95% decision inside the grid has no marker."
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" data-chart="distance" '
        f'data-distance="{e(stratifier)}" aria-labelledby="{ids}-t {ids}-d">',
        f'<title id="{ids}-t">{e(title)}</title>',
        f'<desc id="{ids}-d">{e(description)}</desc>',
        f'<line class="axis" x1="{left}" y1="{py(0):.1f}" x2="{width - right}" y2="{py(0):.1f}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{py(0):.1f}"/>',
    ]
    for tick in (0.0, y_max / 2, y_max):
        parts.append(
            f'<text x="{left - 6}" y="{py(tick) + 4:.1f}" text-anchor="end">{tick:.0f}</text>'
        )
    for n in (*sizes, population):
        parts.append(f'<text x="{px(n):.1f}" y="{py(0) + 15:.1f}" text-anchor="middle">{n}</text>')
    if policy_size in sizes:
        parts.append(
            f'<line class="mark" x1="{px(policy_size):.1f}" y1="{top}" '
            f'x2="{px(policy_size):.1f}" y2="{py(0):.1f}"/>'
            f'<text class="halo" x="{px(policy_size) + 4:.1f}" y="{top + 12}">'
            f"policy {policy_size}</text>"
        )
    # A stage size that no generator decides at 95% inside the grid gets a vertical label.
    for n in sizes:
        if all(s["d95"] is None for s in settings if s["stage_size"] == n):
            parts.append(
                f'<text class="halo" transform="translate({px(n) + 13:.1f} {py(0) - 6:.1f}) '
                f'rotate(-90)">not reached</text>'
            )
    for slot, generator in enumerate(GENERATORS, start=1):
        mine = sorted(
            (s for s in settings if s["generator"] == generator), key=lambda s: s["stage_size"]
        )
        # One polyline for each run of stage sizes with a d95.
        runs: list[list[Mapping[str, Any]]] = [[]]
        for s in mine:
            if s["d95"] is None:
                runs.append([])
            else:
                runs[-1].append(s)
        for run in (r for r in runs if r):
            path = " ".join(
                f"{px(int(s['stage_size'])):.1f},{py(float(s['d95']) * 100):.1f}" for s in run
            )
            parts.append(_series_line(slot, path))
        parts.extend(
            _marker(
                slot,
                px(int(s["stage_size"])),
                py(float(s["d95"]) * 100),
                f"{GENERATOR_LABELS[generator]}, {s['stage_size']} questions: d95 "
                f"{_points_text(s['d95'])} points (below {_points_text(s['d95_below'])}, "
                f"above {_points_text(s['d95_above'])})",
            )
            for s in mine
            if s["d95"] is not None
        )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 6}" text-anchor="middle">'
        "stage-1 size (questions)</text>"
        f'<text transform="translate(12 {(top + py(0)) / 2:.1f}) rotate(-90)" '
        'text-anchor="middle">d95 (points of score)</text></svg>'
    )
    return "\n".join(parts)


def _error_section(document: Mapping[str, Any], all_cells: Sequence[Mapping[str, Any]]) -> str:
    """The error-rate study: the d95 sentence, the two charts, and two tables."""
    e = html.escape
    error, claim = document["error_rate"], document["error_rate"]["claim"]
    note = _judge_note(document)
    key = str(document["benchmark"])
    threshold, alpha = float(document["threshold"]), float(document["alpha"])
    stratifier, method = str(document["stratifier"]), str(document["interval_method"])
    policy_size, population = int(document["stage1_size"]), int(document["population"])
    pass_line = float(error["pass_line"])
    draws = int(error["draws_per_cell"])
    sizes = list(error["stage_sizes"])
    chart_size = policy_size if policy_size in sizes else sizes[0]
    scores = error["true_scores"]
    grid = f"{scores[0]:.2f} to {scores[-1]:.2f}"
    settings = [
        s
        for s in error["settings"]
        if (s["stratifier"], s["stage_size"]) == (stratifier, chart_size)
    ]
    cells = [c for c in all_cells if (c["stratifier"], c["stage_size"]) == (stratifier, chart_size)]
    highest = max((float(c["wrong_rate"]) for c in cells), default=0.0)
    # Room above the pass line for its label, and above the highest rate.
    y_max = max(0.1, math.ceil(max(highest, pass_line * 1.3) * 20) / 20)
    error_panels = []
    for m in INTERVAL_METHODS:
        mine = [s for s in settings if s["method"] == m]
        passing = all(s["passes"] for s in mine)
        worst = max((float(s["max_wrong_rate"]) for s in mine), default=0.0)
        verdict = "passes" if passing else "fails"
        title = (
            f"{METHOD_LABELS[m]} {verdict} for both generators: highest wrong-decision "
            f"rate {worst:.3f}"
            if passing
            else f"{METHOD_LABELS[m]} fails the pass line: highest wrong-decision rate {worst:.3f}"
        )
        chart = _error_chart(
            m,
            [c for c in cells if c["method"] == m],
            benchmark=key,
            title=title,
            y_max=y_max,
            alpha=alpha,
            pass_line=pass_line,
            threshold=threshold,
        )
        css = "" if passing else ' class="fail"'
        error_panels.append(
            f"<figure><figcaption{css}>{e(METHOD_LABELS[m])}: {verdict} "
            f"(highest {worst:.3f})</figcaption>\n{chart}</figure>"
        )
    distances = [
        float(s["d95"]) * 100
        for s in error["settings"]
        if s["method"] == method and s["d95"] is not None
    ]
    # Room above the highest point for the policy label.
    d_max = max(10.0, math.ceil((max(distances, default=0.0) + 4) / 10) * 10)
    stratifiers = list(dict.fromkeys(s["stratifier"] for s in error["settings"]))
    distance_panels = []
    for name in stratifiers:
        mine = [s for s in error["settings"] if s["stratifier"] == name and s["method"] == method]
        at_policy = [s for s in mine if s["stage_size"] == policy_size]
        found = [s["d95"] for s in at_policy if s["d95"] is not None]
        if at_policy and len(found) == len(at_policy):
            title = (
                f"{name}: at {policy_size} questions, d95 is {_points_text(min(found))} to "
                f"{_points_text(max(found))} points across the generators"
            )
        else:
            title = f"{name}: d95 against stage-1 size, by generator"
        chart = _distance_chart(
            name,
            mine,
            benchmark=key,
            title=title,
            population=population,
            policy_size=policy_size,
            y_max=d_max,
        )
        distance_panels.append(
            f"<figure><figcaption><code>{e(name)}</code></figcaption>\n{chart}</figure>"
        )
    combined = {(c["stratifier"], c["stage_size"], c["method"]): c for c in error["combined"]}
    rows = list(dict.fromkeys((s, n) for s, n, _ in combined))
    header = "".join(f"<th>{e(METHOD_LABELS[m])}</th>" for m in INTERVAL_METHODS)

    def table(cell: Callable[[str, Mapping[str, Any]], str]) -> str:
        lines = []
        for name, n in rows:
            values = "".join(
                cell(f"{e(name)}-{n}-{e(m)}", combined[(name, n, m)]) for m in INTERVAL_METHODS
            )
            lines.append(f"<tr><td><code>{e(name)}</code>, {n}</td>{values}</tr>")
        return "\n".join(lines)

    def verdict_cell(cell_key: str, setting: Mapping[str, Any]) -> str:
        passing = setting["passes_both_generators"]
        word, css = ("pass", "") if passing else ("fail", ' class="fail"')
        return (
            f'<td data-error-pass="{cell_key}"{css}>{word} '
            f"{float(setting['max_wrong_rate']):.3f}</td>"
        )

    def distance_cell(cell_key: str, setting: Mapping[str, Any]) -> str:
        detail = " / ".join(_points_text(d) for d in setting["d95_by_generator"].values())
        # A d95 means nothing when the setting decides wrong too often.
        if setting["passes_both_generators"]:
            return (
                f'<td data-d95="{cell_key}">{_points_text(setting["d95"])}'
                f"<br><small>{e(detail)}</small></td>"
            )
        return (
            f'<td data-d95="{cell_key}" class="fail">{_points_text(setting["d95"])}'
            f"<br><small>{e(detail)}; error rate fails</small></td>"
        )

    generator_notes = "\n".join(
        f"<li><b>{e(GENERATOR_LABELS[g])}</b> (<code>{e(g)}</code>). {e(GENERATOR_NOTES[g])}</li>"
        for g in GENERATORS
    )
    passing_settings = [c for c in error["combined"] if c["passes_both_generators"]]
    labels = [GENERATOR_LABELS[g] for g in GENERATORS]
    return f"""<h3>Error rate and distance to decide</h3>
{note}
<p>How often does the probe decide wrong for a simulated model, and how far from the
threshold must a model be for the probe to decide? For each setting (stratifier, stage size,
and interval method) and each true score from {grid}, the study draws {draws:,} pairs of a
new simulated model and a new stratified subset. Every method sees the same pairs, and
every setting sees the same simulated models, so two settings compare on paired draws. Only
stage 1 can decide wrong. A setting passes when its wrong-decision rate is at most
{pass_line:.3f} at every true score: alpha {alpha:.2f} plus 3 standard errors.
{len(passing_settings)} of {len(error["combined"])} settings pass for both generators.</p>
<ul>
{generator_notes}
</ul>
<p class="claim" data-d95-claim>{e(str(claim["sentence"]))}
{e(str(claim["error_verdict"]))}
{e(str(claim["smallest_sentence"]))}</p>
<p>d95 is the smallest distance from the threshold at which the probe decides at stage 1 in
at least 95% of the draws, at every grid true score at least that far away. Each side of the
threshold has its own distance, and d95 is the larger one. One point is 0.01 of score.</p>
<h4>Wrong-decision rate against true score</h4>
{note}
<p>The policy probe: {chart_size} questions, <code>{e(stratifier)}</code>. One panel for
each interval method. A marker shows a true score with at least one wrong decision; hold the
pointer on it for the counts. <code>error_rate.csv</code> holds every cell.</p>
{_legend(labels)}
<div class="panels">
{chr(10).join(error_panels)}
</div>
<h4>Distance to decide against stage-1 size</h4>
{note}
<p>The policy method, <code>{e(method)}</code>, for each stratifier. A larger probe decides
closer to the threshold. A stage size with no marker does not reach 95% inside the grid.</p>
{_legend(labels)}
<div class="panels">
{chr(10).join(distance_panels)}
</div>
<h4>Highest wrong-decision rate for both generators</h4>
{note}
<p>"pass" means that the setting passes at every true score for both generators. The
number is the highest wrong-decision rate across the generators and true scores.</p>
<div class="scroll">
<table>
<thead><tr><th>Stratifier, stage size</th>{header}</tr></thead>
<tbody>
{table(verdict_cell)}
</tbody>
</table>
</div>
<h4>Distance to decide (d95) for both generators</h4>
{note}
<p>The larger d95 of the two generators, in points. Below it: {e(" / ".join(labels))}.
<code>error_rate_settings.csv</code> holds each side and generator.</p>
<div class="scroll">
<table>
<thead><tr><th>Stratifier, stage size</th>{header}</tr></thead>
<tbody>
{table(distance_cell)}
</tbody>
</table>
</div>"""


def _benchmark_section(document: Mapping[str, Any], run: BenchmarkRun) -> str:
    """One benchmark: the same charts and tables for every benchmark."""
    rows, overall = document["true_scores"], document["overall"]
    key, title = str(document["benchmark"]), str(document["title"])
    costs = [float(r["expected_cost_fraction"]["mean"]) for r in rows]
    threshold, alpha = float(document["threshold"]), float(document["alpha"])
    size, population = document["stage1_size"], document["population"]
    decisive = [(float(r["true_score"]), float(r["decisive_fraction"])) for r in rows]
    wrong = [(float(r["true_score"]), float(r["wrong_decision_rate"])) for r in rows]
    worst = max(rate for _, rate in wrong)
    wrong_max = max(0.1, max(float(r["wrong_rate_upper95"]) for r in rows))
    tail = alpha / 2
    note = _judge_note(document)
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
    decisive_chart = _chart(
        f"{title}: share of simulated models decided by the stage-1 probe",
        "Decisive fraction for each true score. It is near 0 close to the threshold and "
        "rises toward 1 far from it. The table below holds the same values.",
        decisive,
        key=key,
        series="decisive",
        y_max=1.0,
        y_label="decisive fraction",
        threshold=threshold,
    )
    wrong_title = (
        f"{title}: no true score has a wrong-decision rate above the one-tail bound {tail:.3f}"
        if worst <= tail
        else f"{title}: at least one true score has a wrong-decision rate above {tail:.3f}"
    )
    wrong_chart = _chart(
        wrong_title,
        f"Wrong-decision rate for each true score, with a line at the one-tail bound "
        f"{tail:.3f}. The highest rate is {worst:.3f}. The table below holds the same "
        "values and their 95% upper bounds.",
        wrong,
        key=key,
        series="wrong",
        y_max=wrong_max,
        y_label="wrong-decision rate",
        threshold=threshold,
        reference=(tail, f"one-tail bound {tail:.3f}"),
    )
    limits = "\n".join(f"<li>{e(str(item))}</li>" for item in document["limitations"])
    limits_block = f"<h3>Limits for {e(title)}</h3>\n<ul>\n{limits}\n</ul>" if limits else ""
    return f"""<section data-benchmark="{e(key)}" id="bench-{e(key)}">
<h2>{e(title)}</h2>
{note}
<p>Question: is the full-set {e(title)} score of a model at or above the threshold
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
<h3>How the decision works</h3>
<ol>
<li>Select {size} questions with the <code>{e(str(document["stratifier"]))}</code>
selector. It uses the reference panel only.</li>
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
<h3>Decisive fraction</h3>
{note}
{decisive_chart}
<h3>Wrong-decision rate</h3>
{note}
{wrong_chart}
<h3>Results for each true score</h3>
{note}
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
part below explains it.</p>
{_cost_section(run.cost, document)}
{_coverage_section(document, run.coverage["cells"])}
{_error_section(document, run.error_rate["cells"])}
{limits_block}
</section>"""


def _overview(documents: Sequence[Mapping[str, Any]]) -> str:
    """One column for each benchmark, so the results are side by side."""
    e = html.escape

    def judge(d: Mapping[str, Any]) -> str:
        return "One judgment for each answer; not measured" if d["judge_graded"] else "No judge"

    def cost(d: Mapping[str, Any]) -> str:
        values = [float(r["expected_cost_fraction"]["mean"]) for r in d["true_scores"]]
        return f"{min(values):.3f} to {max(values):.3f}"

    def mean_cost(d: Mapping[str, Any]) -> str:
        values = [float(r["expected_cost_fraction"]["mean"]) for r in d["true_scores"]]
        return f"{math.fsum(values) / len(values):.3f}"

    def decided(d: Mapping[str, Any]) -> str:
        overall = d["overall"]
        return f"{overall['decided_at_stage1'] / overall['draws']:.3f}"

    def input_share(d: Mapping[str, Any]) -> str:
        full = d["cost"]["full_run"]
        return f"{full['input_tokens_mean'] / full['tokens']['mean']:.0%}"

    def input_ratio(d: Mapping[str, Any]) -> str:
        return _ratio_text(d["cost"]["full_run"]["input_tokens_max_model_ratio"])

    def d95(d: Mapping[str, Any]) -> str:
        distance = d["error_rate"]["claim"]["d95"]
        return "not reached" if distance is None else f"{_points_text(distance)} points"

    def error_pass(d: Mapping[str, Any]) -> str:
        passes = d["error_rate"]["claim"]["passes_both_generators"]
        return "not studied" if passes is None else ("pass" if passes else "fail")

    rows: tuple[tuple[str, str, Callable[[Mapping[str, Any]], str]], ...] = (
        ("threshold", "Threshold", lambda d: f"{float(d['threshold']):.2f}"),
        ("stage1-size", "Stage-1 size", lambda d: f"{d['stage1_size']} of {d['population']}"),
        ("interval-method", "Interval method", lambda d: str(d["interval_method"])),
        ("stratifier", "Stratifier", lambda d: str(d["stratifier"])),
        ("models", "Simulated models", lambda d: f"{d['overall']['draws']:,}"),
        ("decided", "Share decided at stage 1", decided),
        ("wrong", "Wrong decisions", lambda d: f"{d['overall']['wrong_decisions']:,}"),
        (
            "max-wrong-rate",
            "Highest wrong-decision rate",
            lambda d: f"{float(d['overall']['max_wrong_decision_rate']):.3f}",
        ),
        ("error-pass", "Error rate within the pass line, both generators", error_pass),
        ("d95", "Distance to decide (d95)", d95),
        ("cost", "Expected cost, share of a full run", cost),
        ("mean-cost", "Mean expected cost across true scores", mean_cost),
        (
            "full-tokens",
            "Full run, mean tokens",
            lambda d: f"{d['cost']['full_run']['tokens']['mean']:,.0f}",
        ),
        ("input-share", "Input share of tokens", input_share),
        ("input-ratio", "Largest input ratio between models", input_ratio),
        ("judge-noise", "Judge noise", judge),
    )
    # A judge-graded column carries a mark that points to the judge-noise note below.
    head = "".join(
        f"<th>{e(str(d['title']))}{' *' if d['judge_graded'] else ''}</th>" for d in documents
    )
    judged = [str(d["title"]) for d in documents if d["judge_graded"]]
    footnote = (
        f'<p class="judge-noise" data-overview-note>* {e(", ".join(judged))}: {e(JUDGE_NOISE)}</p>'
        if judged
        else ""
    )
    body = "\n".join(
        f"<tr><td>{e(label)}</td>"
        + "".join(
            f'<td data-overview="{e(str(d["benchmark"]))}-{name}">{e(value(d))}</td>'
            for d in documents
        )
        + "</tr>"
        for name, label, value in rows
    )
    return f"""<div class="scroll">
<table>
<thead><tr><th>Setting or result</th>{head}</tr></thead>
<tbody>
{body}
</tbody>
</table>
</div>
{footnote}"""


def html_report(
    document: Mapping[str, Any],
    runs: Sequence[BenchmarkRun],
    *,
    manifest_inputs: Mapping[str, str],
) -> bytes:
    documents, policy = document["benchmarks"], document["policy"]
    e = html.escape
    titles = [str(d["title"]) for d in documents]
    named = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + " and " + titles[-1]
    links = "\n".join(
        f'<li><a href="#bench-{e(str(d["benchmark"]))}">{e(str(d["title"]))}</a></li>'
        for d in documents
    )
    sections = "\n".join(_benchmark_section(d, run) for d, run in zip(documents, runs, strict=True))
    limitations = "\n".join(f"<li>{e(str(item))}</li>" for item in document["limitations"])
    inputs = "\n".join(
        f"<li>{e(name)}: <code>{e(str(sha))}</code></li>" for name, sha in manifest_inputs.items()
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
<h1>Two-stage threshold decision on simulated {e(named)} models</h1>
<p>Question: is the full-set score of a model at or above the threshold of its benchmark?
One policy file sets the threshold, the stage-1 size, the interval method, and the
stratifier of each benchmark. Each benchmark has its own section with the same charts and
tables.</p>
<ul>
{links}
</ul>
<h2>Benchmarks side by side</h2>
<p>The expected cost is the range across the true scores at the policy stage-1 size, as a
share of one full run. The mean gives each true score equal weight. The benchmark sections
give the evidence for each value.</p>
{_overview(documents)}
{sections}
<h2>Limits</h2>
<p>These limits apply to every benchmark. Each benchmark section adds its own limits.</p>
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


def build_outputs(loaded: LoadedPolicy, runs: Sequence[BenchmarkRun]) -> dict[str, bytes]:
    """All report files, with the manifest hashing the others."""
    document = summary_document(loaded, runs)
    inputs = {loaded.file_name: loaded.sha256}
    for run in runs:
        inputs[run.panel_file] = run.panel_sha256
        inputs.update(run.cost.tokens.files)
    code_root = Path(__file__).parent
    outputs: dict[str, bytes] = {}
    for run in runs:
        folder = run.policy.benchmark
        outputs[f"{folder}/decisions.csv"] = decision_table(
            run.rows, population=run.population, cost=run.cost
        )
        outputs[f"{folder}/coverage.csv"] = coverage_table(run.coverage)
        outputs[f"{folder}/cost.csv"] = cost_table(run.cost)
        outputs[f"{folder}/question_tokens.csv"] = question_token_table(run.cost)
        outputs[f"{folder}/error_rate.csv"] = error_rate_table(run.error_rate)
        outputs[f"{folder}/error_rate_settings.csv"] = error_rate_settings_table(run.error_rate)
        outputs[f"{folder}/error_rate_combined.csv"] = error_rate_combined_table(run.error_rate)
    outputs["summary.json"] = encode_json(document)
    outputs["report.html"] = html_report(document, runs, manifest_inputs=inputs)
    manifest = {
        "schema_version": 2,
        "command": "threshold-decision",
        "analysis_version": ANALYSIS_VERSION,
        "mode": "simulated",
        "real_grades_used": False,
        "policy": {
            "file": loaded.file_name,
            "key": loaded.key,
            "sha256": loaded.sha256,
            "frozen": loaded.frozen,
        },
        "inputs": {
            "benchmarks": {
                run.policy.benchmark: {
                    "reference_panel": {"file": run.panel_file, "sha256": run.panel_sha256},
                    # Only the usage records of these files are read, never a grade.
                    "token_counts": dict(run.cost.tokens.files),
                }
                for run in runs
            }
        },
        "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
        "implementation_sha256": {
            name: _sha((code_root / name).read_bytes().replace(b"\r\n", b"\n"))
            for name in IMPLEMENTATION_FILES
        },
        "output_sha256": {name: _sha(data) for name, data in outputs.items()},
        "counts": {
            run.policy.benchmark: {
                "simulated_models": len(run.rows),
                "true_scores": len(run.summary),
                "coverage_cells": len(run.coverage["cells"]),
                "cost_cells": len(run.cost.cells),
                "missing_token_counts": len(run.cost.tokens.missing),
                "error_rate_cells": len(run.error_rate["cells"]),
            }
            for run in runs
        },
    }
    outputs["manifest.json"] = encode_json(manifest)
    return outputs
