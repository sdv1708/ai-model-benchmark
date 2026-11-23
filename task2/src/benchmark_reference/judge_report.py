"""Measure the judge noise from a complete run, and write the recorded outputs.

A judgment is the verdict of one slot: one pass, one model, one question. The report
needs a verdict for every slot. It never fills a missing verdict.

The full-set score of a model in a pass is the share of CORRECT verdicts in that pass.
"""

import csv
import hashlib
import io
import json
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

from benchmark_reference.judge_estimate import PASSES, Estimate, load_estimate, model_key
from benchmark_reference.judge_items import JudgeInputs
from benchmark_reference.judge_prompt import parse_reply, prompt_sha256
from benchmark_reference.judge_run import (
    JUDGMENTS,
    PARSE_ERROR,
    REJECTED,
    SETTINGS,
    SUCCESS,
    TRANSPORT_ERROR,
    Slot,
    check_approval_url,
    read_attempts,
    slot_of,
)
from benchmark_reference.judge_statement import RECORD_FILE, RECORD_SCHEMA, statement_and_cell
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import select_strata
from benchmark_reference.threshold_benchmarks import AA_LCR, ReferencePanel
from benchmark_reference.threshold_intervals import interval_bounds, stratum_counts
from benchmark_reference.threshold_policy import LoadedPolicy, ThresholdPolicy, alpha_spending
from benchmark_reference.two_stage import full_set_decision

OUTPUT_NAMES = (
    JUDGMENTS,
    SETTINGS,
    "answers.csv",
    "scores.csv",
    "summary.json",
    RECORD_FILE,
    "report.md",
    "manifest.json",
)
IMPLEMENTATION_FILES = (
    "judge_prompt.py",
    "judge_items.py",
    "judge_estimate.py",
    "judge_run.py",
    "judge_statement.py",
    "judge_report.py",
    "judge_cli.py",
    "pruning.py",
    "long_context.py",
    "threshold_benchmarks.py",
    "threshold_intervals.py",
    "threshold_policy.py",
    "two_stage.py",
    "uncertainty.py",
)
type Verdicts = dict[tuple[str, int], tuple[int, ...]]


@dataclass(frozen=True, slots=True)
class JudgeRecord:
    """A complete run: its settings, every attempt, and the 5 grades of each answer."""

    estimate: Estimate
    approval_url: str | None
    settings_bytes: bytes
    attempts: tuple[dict[str, Any], ...]
    verdicts: Verdicts


def load_run(run_dir: Path, inputs: JudgeInputs) -> JudgeRecord:
    """Read a run folder. It stops when a judgment is missing, repeated, or not consistent."""
    settings_path = run_dir / SETTINGS
    settings_bytes = settings_path.read_bytes()
    try:
        settings = json.loads(settings_bytes)
        estimate = load_estimate(encode_json(settings["estimate"]))
        approval = settings["approval_url"]
        recorded = settings["estimate_sha256"]
    except AnalysisError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise AnalysisError(f"{settings_path} is not valid: {exc}") from exc
    if estimate.sha256 != recorded:
        raise AnalysisError(f"{settings_path} does not hold the estimate that it names")
    if not estimate.loopback:
        check_approval_url(approval)
    if estimate.prompts_sha256 != inputs.prompts_sha256:
        raise AnalysisError(f"{run_dir} used other prompts")
    prompts = {item.key: prompt_sha256(item.prompt) for item in inputs.items}
    attempts = read_attempts(run_dir / JUDGMENTS)
    found: dict[Slot, int] = {}
    seen: set[tuple[Slot, int]] = set()
    identities: set[str] = set()
    for attempt in attempts:
        slot = slot_of(attempt)
        key = (slot[1], slot[2])
        if key not in prompts or slot[0] not in range(1, PASSES + 1):
            raise AnalysisError(f"The run holds a judgment of another answer: {slot}")
        if attempt["prompt_sha256"] != prompts[key]:
            raise AnalysisError(f"The prompt of {slot} differs from the prompt of the saved answer")
        if (slot, attempt["attempt"]) in seen:
            raise AnalysisError(f"The run repeats attempt {attempt['attempt']} of {slot}")
        seen.add((slot, attempt["attempt"]))
        if attempt["status"] != SUCCESS:
            continue
        if slot in found:
            raise AnalysisError(f"The run holds two judgments for {slot}")
        identity, returned = attempt["response_id"], attempt["response_model"]
        if identity in identities:
            raise AnalysisError(f"Two judgments have the response {identity!r}")
        if identity is not None:
            identities.add(identity)
        if returned is not None and model_key(returned) != model_key(estimate.judge_model):
            raise AnalysisError(f"The judgment of {slot} comes from model {returned!r}")
        verdict = parse_reply(attempt["reply"] or "").verdict
        if verdict is None or verdict != attempt["verdict"]:
            raise AnalysisError(f"The verdict of {slot} differs from its reply")
        found[slot] = int(verdict == "CORRECT")
    needed = len(prompts) * PASSES
    if len(found) != needed:
        raise AnalysisError(
            f"The run holds {len(found)} of {needed} judgments. Run 'aa-lcr-judge run' again."
        )
    verdicts = {
        (model, index): tuple(found[n, model, index] for n in range(1, PASSES + 1))
        for model, index in sorted(prompts)
    }
    ordered = sorted(attempts, key=lambda a: (*slot_of(a), a["attempt"]))
    return JudgeRecord(estimate, approval, settings_bytes, tuple(ordered), verdicts)


def pass_scores(verdicts: Verdicts) -> dict[str, tuple[int, ...]]:
    """The number of CORRECT verdicts of each model in each pass."""
    return {
        model: tuple(
            sum(grades[n] for (m, _), grades in verdicts.items() if m == model)
            for n in range(PASSES)
        )
        for model in sorted({m for m, _ in verdicts})
    }


def majority(grades: Sequence[int]) -> int:
    """The vote of an odd number of grades."""
    return int(2 * sum(grades) > len(grades))


def interval_widths(panel: ReferencePanel, policy: ThresholdPolicy) -> dict[str, list[Fraction]]:
    """The stage-1 interval width of each reference model at each policy seed.

    The strata come from the other reference models, as in the hold-out of the real
    replay. The grades are the saved grades.
    """
    widths: dict[str, list[Fraction]] = {}
    alpha = Fraction(str(alpha_spending(policy)[0]))
    for model, target in sorted(panel.references.items()):
        others = ReferencePanel(
            panel.benchmark,
            {m: grades for m, grades in panel.references.items() if m != model},
            panel.metadata,
        )
        groups = others.strata(policy.stratifier)
        widths[model] = []
        for seed in policy.seeds:
            selection = select_strata(groups, budget=policy.stage1_size, seed=seed)
            low, high = interval_bounds(
                policy.interval_method, stratum_counts(selection, target), alpha=alpha
            )
            widths[model].append(high - low)
    return widths


def _round(value: float | Fraction) -> float:
    return round(float(value), 6)


def _mean(values: Sequence[Fraction]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


def _agreement(verdicts: Verdicts, inputs: JudgeInputs) -> dict[str, Any]:
    saved = {item.key: item.saved_grade for item in inputs.items}
    table = Counter((saved[key], majority(grades)) for key, grades in verdicts.items())
    agree = table[0, 0] + table[1, 1]
    return {
        "answers": len(verdicts),
        "agree": agree,
        "share": _round(Fraction(agree, len(verdicts))),
        "saved_correct_majority_incorrect": table[1, 0],
        "saved_incorrect_majority_correct": table[0, 1],
    }


def _models(
    record: JudgeRecord,
    inputs: JudgeInputs,
    widths: Mapping[str, Sequence[Fraction]],
    threshold: Fraction,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, counts in pass_scores(record.verdicts).items():
        grades = {i: g for (m, i), g in record.verdicts.items() if m == model}
        size = len(grades)
        decisions = [full_set_decision(c, size, threshold) for c in counts]
        saved = sum(i.saved_grade for i in inputs.items if i.model == model)
        voted = sum(majority(g) for g in grades.values())
        rows.append(
            {
                "model": model,
                "answers": size,
                "not_unanimous": sum(len(set(g)) > 1 for g in grades.values()),
                "pass_correct": list(counts),
                "pass_scores": [_round(Fraction(c, size)) for c in counts],
                "lowest_score": _round(Fraction(min(counts), size)),
                "highest_score": _round(Fraction(max(counts), size)),
                "score_range": _round(Fraction(max(counts) - min(counts), size)),
                "score_standard_deviation": _round(statistics.stdev(c / size for c in counts)),
                "saved_score": _round(Fraction(saved, size)),
                "majority_score": _round(Fraction(voted, size)),
                "majority_shift": _round(Fraction(voted - saved, size)),
                "saved_decision": full_set_decision(saved, size, threshold),
                "pass_decisions": decisions,
                "decision_changes": len(set(decisions)) > 1,
                "pass_pairs_that_differ": sum(a != b for a, b in combinations(decisions, 2)),
                "mean_stage1_interval_width": _round(_mean(widths[model])),
            }
        )
    return rows


def _usage(record: JudgeRecord) -> dict[str, Any]:
    attempts = record.attempts
    status = Counter(a["status"] for a in attempts)
    return {
        "requests": len(attempts),
        "judgments": status[SUCCESS],
        "replies_outside_the_contract": status[PARSE_ERROR],
        "requests_with_no_usable_reply": status[TRANSPORT_ERROR],
        "rejected_replies": status[REJECTED],
        "input_tokens": sum(a["input_tokens"] or 0 for a in attempts),
        "output_tokens": sum(a["output_tokens"] or 0 for a in attempts),
        "requests_with_no_token_count": sum(
            a["input_tokens"] is None or a["output_tokens"] is None for a in attempts
        ),
        "cost_bound_usd": _round(sum(Fraction(a["cost_bound_usd"]) for a in attempts)),
        "limit_usd": _round(record.estimate.limit_usd),
    }


def _values(record: JudgeRecord, name: str) -> list[str]:
    return sorted({a[name] for a in record.attempts if a[name] is not None})


def summary_document(
    record: JudgeRecord, inputs: JudgeInputs, panel: ReferencePanel, loaded: LoadedPolicy
) -> dict[str, Any]:
    """Every measured value of the report."""
    if panel.sha256 != inputs.panel_sha256:
        raise AnalysisError("The panel differs from the panel of the saved answers")
    policy = loaded.benchmarks[AA_LCR]
    widths = interval_widths(panel, policy)
    models = _models(record, inputs, widths, Fraction(str(policy.threshold)))
    split = sum(m["not_unanimous"] for m in models)
    largest = max(
        Fraction(max(m["pass_correct"]) - min(m["pass_correct"]), m["answers"]) for m in models
    )
    all_widths = [w for values in widths.values() for w in values]
    estimate = record.estimate
    return {
        "schema_version": 1,
        "command": "aa-lcr-judge report",
        "loopback_test": estimate.loopback,
        "judge": {
            **estimate.document["judge"],
            "response_models": _values(record, "response_model"),
            "providers": _values(record, "provider"),
            "system_fingerprints": _values(record, "system_fingerprint"),
            "run_dates_utc": sorted({a["started_at"][:10] for a in record.attempts}),
        },
        "prompt": estimate.document["prompt"],
        "estimate_sha256": estimate.sha256,
        "approval_url": record.approval_url,
        "passes": PASSES,
        "disagreement": {
            "answers": len(record.verdicts),
            "not_unanimous": split,
            "share": _round(Fraction(split, len(record.verdicts))),
            "correct_votes": {
                str(votes): count
                for votes, count in sorted(
                    Counter(sum(g) for g in record.verdicts.values()).items()
                )
            },
        },
        "agreement_with_saved_judgment": _agreement(record.verdicts, inputs),
        "models": models,
        "full_set_score": {"largest_range": _round(largest)},
        "decisions": {
            "threshold": policy.threshold,
            "models": len(models),
            "models_that_change": sum(m["decision_changes"] for m in models),
            "pass_pairs_that_differ": sum(m["pass_pairs_that_differ"] for m in models),
            "pass_pairs": len(models) * PASSES * (PASSES - 1) // 2,
        },
        "stage1_interval": {
            "policy": loaded.key,
            "policy_sha256": loaded.sha256,
            "method": policy.interval_method,
            "stratifier": policy.stratifier,
            "stage1_size": policy.stage1_size,
            "seeds": len(policy.seeds),
            "mean_width": _round(_mean(all_widths)),
            "lowest_width": _round(min(all_widths)),
            "highest_width": _round(max(all_widths)),
            "largest_score_range_to_mean_width": _round(largest / _mean(all_widths)),
            "includes_judge_noise": False,
        },
        "usage": _usage(record),
    }


def noise_record(summary: Mapping[str, Any], *, panel_sha256: str) -> dict[str, Any]:
    """The values that the threshold report shows."""
    dates = summary["judge"]["run_dates_utc"]
    return {
        "schema_version": RECORD_SCHEMA,
        "loopback_test": summary["loopback_test"],
        "reference_panel_sha256": panel_sha256,
        "judge_model": summary["judge"]["model"],
        "temperature": summary["judge"]["temperature"],
        "original_judge": summary["judge"]["original_model"],
        "same_judge": summary["judge"]["same_judge"],
        "run_dates": dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}",
        "estimate_sha256": summary["estimate_sha256"],
        **{
            name: summary[name]
            for name in (
                "passes",
                "disagreement",
                "agreement_with_saved_judgment",
                "models",
                "full_set_score",
                "decisions",
                "stage1_interval",
            )
        },
    }


def _csv(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _table(head: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    return "\n".join([*lines, *("| " + " | ".join(str(c) for c in row) + " |" for row in rows)])


def _judge_sentences(summary: Mapping[str, Any]) -> list[str]:
    judge, agreement = summary["judge"], summary["agreement_with_saved_judgment"]
    original = judge["original_model"]
    if judge["same_judge"]:
        first = (
            f"The saved reviews name the judge `{original}`. This run uses the same model, "
            f"with the name `{judge['model']}` at this endpoint."
        )
    elif original is None:
        first = "The saved reviews do not name one judge. The judge of this run can differ."
    else:
        first = (
            f"The saved reviews name the judge `{original}`. This run uses another judge, "
            f"`{judge['model']}`. The values describe the judge of this run only."
        )
    return [
        first,
        "The saved reviews record no endpoint, no precision, and no settings, and an earlier "
        "EvalScope version can have sent another prompt. Each of these can differ from this run.",
        f"The majority of the {summary['passes']} new judgments agrees with the saved judgment "
        f"for {agreement['agree']} of {agreement['answers']} answers ({agreement['share']:.1%}). "
        f"{agreement['saved_correct_majority_incorrect']} answers change from CORRECT to "
        f"INCORRECT, and {agreement['saved_incorrect_majority_correct']} change from INCORRECT "
        "to CORRECT.",
    ]


def _settings_table(summary: Mapping[str, Any]) -> str:
    judge, prompt = summary["judge"], summary["prompt"]
    return _table(
        ("Setting", "Value"),
        (
            ("Judge model, requested", f"`{judge['model']}`"),
            ("Judge model, returned", ", ".join(judge["response_models"]) or "not returned"),
            ("Provider, returned", ", ".join(judge["providers"]) or "not returned"),
            ("Endpoint", judge["base_url"]),
            ("Run dates (UTC)", ", ".join(judge["run_dates_utc"])),
            ("Temperature", judge["temperature"]),
            ("Maximum output tokens", judge["max_tokens"]),
            ("Seed", "none sent"),
            ("Judge prompt", f"{prompt['source']} at `{prompt['commit']}`, no change"),
            ("Prompts SHA-256", f"`{prompt['prompts_sha256']}`"),
            ("Approval", summary["approval_url"] or "not needed"),
            ("Estimate SHA-256", f"`{summary['estimate_sha256']}`"),
        ),
    )


def _score_table(summary: Mapping[str, Any]) -> str:
    return _table(
        (
            "Model",
            "Answers with unequal judgments",
            "Scores in the passes",
            "Lowest",
            "Highest",
            "Standard deviation",
            "Saved score",
            "Majority score",
            "Decisions in the passes",
            "Decision changes",
        ),
        [
            (
                m["model"],
                f"{m['not_unanimous']} of {m['answers']}",
                ", ".join(f"{s:.2f}" for s in m["pass_scores"]),
                f"{m['lowest_score']:.2f}",
                f"{m['highest_score']:.2f}",
                f"{m['score_standard_deviation']:.4f}",
                f"{m['saved_score']:.2f}",
                f"{m['majority_score']:.2f} ({m['majority_shift']:+.2f})",
                ", ".join(m["pass_decisions"]),
                "yes" if m["decision_changes"] else "no",
            )
            for m in summary["models"]
        ],
    )


def markdown_report(summary: Mapping[str, Any]) -> bytes:
    interval, usage, changes = summary["stage1_interval"], summary["usage"], summary["decisions"]
    disagree = summary["disagreement"]
    test_note = (
        "**This is a loopback test with a scripted judge. It measures nothing.**\n\n"
        if summary["loopback_test"]
        else ""
    )
    widths = _table(
        ("Model", "Score range across the passes", "Mean stage-1 interval width"),
        [
            (m["model"], f"{m['score_range']:.2f}", f"{m['mean_stage1_interval_width']:.3f}")
            for m in summary["models"]
        ],
    )
    judge_text = "\n".join(f"- {line}" for line in _judge_sentences(summary))
    text = f"""# AA-LCR judge noise on the saved answers (#76)

{test_note}The judge graded each of the {disagree["answers"]} saved answers
{summary["passes"]} times. The run generated no new answer.

## Result

- The judgments are not all equal for {disagree["not_unanimous"]} of {disagree["answers"]} answers ({disagree["share"]:.1%}).
- At threshold {changes["threshold"]:.2f}, {changes["models_that_change"]} of {changes["models"]} full-set decisions change between passes. {changes["pass_pairs_that_differ"]} of {changes["pass_pairs"]} pairs of passes differ.

{_score_table(summary)}

## Judge variation and the stage-1 interval

Policy {interval["policy"]} uses {interval["stage1_size"]} questions, the `{interval["method"]}` interval, and the `{interval["stratifier"]}` strata.
The mean width covers {interval["seeds"]} probes of each model on the saved grades.
The widths are from {interval["lowest_width"]:.3f} to {interval["highest_width"]:.3f}, and the mean is {interval["mean_width"]:.3f}.

{widths}

The largest score range is {interval["largest_score_range_to_mean_width"]:.3f} of the mean interval width.
The interval describes sampling error on fixed grades. It excludes judge noise.

## Judge

{judge_text}

{_settings_table(summary)}

## Requests and cost

- The run made {usage["requests"]:,} requests and got {usage["judgments"]:,} judgments.
- {usage["replies_outside_the_contract"]} replies did not satisfy the output contract, and {usage["requests_with_no_usable_reply"]} requests had no usable reply. The run rejected {usage["rejected_replies"]} replies, which came from another model or repeated an earlier reply. The run repeated these requests, and `judgments.jsonl` keeps all of them.
- The tokens were {usage["input_tokens"]:,} input and {usage["output_tokens"]:,} output. {usage["requests_with_no_token_count"]} requests had no token count.
- The cost was at most ${usage["cost_bound_usd"]:.4f} at the prices of the estimate. The limit was ${usage["limit_usd"]:.2f}.

## Limits

- The judgments show the variation of one judge at one endpoint. They do not show whether the judge is correct.
- The passes measure the noise between repeated calls with the same settings. They do not measure the difference between the saved judgments and this run. The agreement section gives that difference, and the run cannot give its cause.
- The temperature was {summary["judge"]["temperature"]}. A higher temperature can give more noise.
- All passes ran on the dates above. A later model version or another endpoint can differ.
- A repeated request replaces a reply outside the contract. That rule can favor answers for which the judge replies in the correct format.
- Policy v1 does not change. Its interval excludes judge noise.
"""  # noqa: E501
    # A model name from the endpoint can hold half of a character.
    return text.encode("utf-8", errors="replace")


def _answers_table(record: JudgeRecord, inputs: JudgeInputs) -> bytes:
    saved = {item.key: item.saved_grade for item in inputs.items}
    columns = ("model", "index", "saved_grade", *(f"pass_{n}" for n in range(1, PASSES + 1)))
    return _csv(
        (*columns, "correct_votes", "majority", "unanimous", "agrees_with_saved"),
        [
            (
                *key,
                saved[key],
                *grades,
                sum(grades),
                majority(grades),
                int(len(set(grades)) == 1),
                int(majority(grades) == saved[key]),
            )
            for key, grades in record.verdicts.items()
        ],
    )


def _scores_table(summary: Mapping[str, Any]) -> bytes:
    rows = [
        (m["model"], number, correct, m["answers"], score, decision)
        for m in summary["models"]
        for number, (correct, score, decision) in enumerate(
            zip(m["pass_correct"], m["pass_scores"], m["pass_decisions"], strict=True), start=1
        )
    ]
    return _csv(("model", "pass", "correct", "answers", "score", "decision"), rows)


def build_outputs(
    record: JudgeRecord, inputs: JudgeInputs, panel: ReferencePanel, loaded: LoadedPolicy
) -> dict[str, bytes]:
    """All output files, with the manifest hashing the others."""
    summary = summary_document(record, inputs, panel, loaded)
    noise = noise_record(summary, panel_sha256=panel.sha256)
    statement_and_cell(noise)
    lines = [json.dumps(a, sort_keys=True) + "\n" for a in record.attempts]
    outputs = {
        JUDGMENTS: "".join(lines).encode("utf-8"),
        SETTINGS: record.settings_bytes,
        "answers.csv": _answers_table(record, inputs),
        "scores.csv": _scores_table(summary),
        "summary.json": encode_json(summary),
        RECORD_FILE: encode_json(noise),
        "report.md": markdown_report(summary),
    }
    code = Path(__file__).parent
    outputs["manifest.json"] = encode_json(
        {
            "schema_version": 1,
            "command": "aa-lcr-judge report",
            "loopback_test": record.estimate.loopback,
            "inputs": dict(inputs.files),
            "policy": {"key": loaded.key, "sha256": loaded.sha256},
            "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
            "implementation_sha256": {
                name: hashlib.sha256((code / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                for name in IMPLEMENTATION_FILES
            },
            "output_sha256": {n: hashlib.sha256(d).hexdigest() for n, d in outputs.items()},
        }
    )
    return outputs
