"""Test if the judge prompt caused the score shift of #76 (#88).

The JSON run of #76 raised 13 of 300 saved grades from INCORRECT to CORRECT. The control
run sends the same answers to the same judge with the old one-word prompt. This module
compares three sets of grades: the saved grades, the majority of the 5 one-word
judgments, and the majority of the 5 JSON judgments.

Issue #88 fixed the decision rule before the run. ``RULE`` is a copy of it.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from benchmark_reference.judge_estimate import PASSES, Estimate
from benchmark_reference.judge_items import JudgeInputs
from benchmark_reference.judge_prompt import JSON_CONTRACT, ONE_WORD, VERDICTS
from benchmark_reference.judge_report import (
    JudgeRecord,
    Verdicts,
    code_hashes,
    csv_table,
    judge_settings,
    judgment_lines,
    majority,
    markdown_table,
    pass_scores,
    rounded,
    usage_summary,
)
from benchmark_reference.judge_run import JUDGMENTS, SETTINGS, SUCCESS
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import AA_LCR
from benchmark_reference.threshold_policy import LoadedPolicy
from benchmark_reference.two_stage import full_set_decision

OUTPUT_NAMES = (
    JUDGMENTS,
    SETTINGS,
    "answers.csv",
    "scores.csv",
    "summary.json",
    "report.md",
    "manifest.json",
)
IMPLEMENTATION_FILES = (
    "judge_prompt.py",
    "judge_items.py",
    "judge_estimate.py",
    "judge_run.py",
    "judge_report.py",
    "judge_compare.py",
    "judge_cli.py",
    "threshold_benchmarks.py",
    "threshold_policy.py",
    "two_stage.py",
)
# The answers of 300 that the JSON run of #76 changed.
CHANGED_ANSWERS = 13
# The lowest and the highest number of the 13 answers that are INCORRECT again.
RULE = (
    (10, 13, "The prompt explains most of the shift"),
    (4, 9, "The prompt explains a part of the shift"),
    (0, 3, "The prompt does not explain the shift"),
)
GROUPS = {
    "decimal": "Decimal below 1, for example `0.1` for 10%",
    "date": "Excel date number, for example `45444`",
    "list": "List with a literal `\\n`",
    "other": "Other",
}
# The Excel date numbers of 2000-01-01 and 2050-01-01.
_DATES = range(36526, 54789)
type Key = tuple[str, int]
type Grades = dict[Key, int]


def conclusion(incorrect_again: int) -> str:
    """The conclusion of the fixed rule."""
    for low, high, text in RULE:
        if low <= incorrect_again <= high:
            return text
    raise AnalysisError(f"The rule covers 0 to {CHANGED_ANSWERS} answers, not {incorrect_again}")


def reference_group(reference: str) -> str:
    """The form of the reference answer."""
    text = reference.strip()
    if "\\n" in text:
        return "list"
    if re.fullmatch(r"0?\.[0-9]+", text):
        return "decimal"
    if re.fullmatch(r"[0-9]{5}", text) and int(text) in _DATES:
        return "date"
    return "other"


def check_same_judge(control: Estimate, baseline: Estimate) -> None:
    """The prompt and its settings are the only intended difference between the two runs."""
    if control.variant is not ONE_WORD or baseline.variant is not JSON_CONTRACT:
        raise AnalysisError(
            "The comparison needs a run with the one-word prompt and a baseline run with the "
            f"JSON prompt, not {control.variant.name} and {baseline.variant.name}"
        )
    for name in ("judge_model", "base_url", "temperature"):
        ours, theirs = getattr(control, name), getattr(baseline, name)
        if ours != theirs:
            raise AnalysisError(f"The {name} is {ours!r}. The baseline run used {theirs!r}")


def changed_answers(verdicts: Verdicts, inputs: JudgeInputs) -> list[Key]:
    """The answers that the JSON run changed. The fixed rule holds for exactly these 13."""
    saved = {item.key: item.saved_grade for item in inputs.items}
    changed = [key for key, votes in verdicts.items() if majority(votes) != saved[key]]
    if any(saved[key] for key in changed):
        raise AnalysisError("The baseline run changes an answer from CORRECT to INCORRECT")
    if len(changed) != CHANGED_ANSWERS:
        raise AnalysisError(
            f"The baseline run changes {len(changed)} answers. The rule needs {CHANGED_ANSWERS}"
        )
    return changed


def _agreement(first: Grades, second: Grades) -> dict[str, Any]:
    table = Counter((grade, second[key]) for key, grade in first.items())
    agree = table[0, 0] + table[1, 1]
    return {
        "answers": len(first),
        "agree": agree,
        "share": rounded(Fraction(agree, len(first))),
        "incorrect_to_correct": table[0, 1],
        "correct_to_incorrect": table[1, 0],
    }


def _voted(verdicts: Verdicts) -> Grades:
    return {key: majority(votes) for key, votes in verdicts.items()}


def _unequal(verdicts: Verdicts, keys: Sequence[Key]) -> int:
    return sum(len(set(verdicts[key])) > 1 for key in keys)


def _agree(first: Grades, second: Grades, keys: Sequence[Key]) -> int:
    return sum(first[key] == second[key] for key in keys)


def _run_row(
    verdicts: Verdicts, saved: Grades, model: str, keys: Sequence[Key], threshold: Fraction
) -> dict[str, Any]:
    """The values of one model in one run."""
    size, voted = len(keys), _voted(verdicts)
    correct, passes = sum(voted[key] for key in keys), pass_scores(verdicts)[model]
    return {
        "correct": correct,
        "score": rounded(Fraction(correct, size)),
        "decision": full_set_decision(correct, size, threshold),
        "pass_correct": list(passes),
        "pass_scores": [rounded(Fraction(count, size)) for count in passes],
        "pass_decisions": [full_set_decision(count, size, threshold) for count in passes],
        "unequal": _unequal(verdicts, keys),
        "agree_with_saved": _agree(voted, saved, keys),
    }


def _model_rows(
    record: JudgeRecord, baseline: JudgeRecord, saved: Grades, threshold: Fraction
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in sorted({key[0] for key in saved}):
        keys = [key for key in saved if key[0] == model]
        correct = sum(saved[key] for key in keys)
        rows.append(
            {
                "model": model,
                "answers": len(keys),
                "saved": {
                    "correct": correct,
                    "score": rounded(Fraction(correct, len(keys))),
                    "decision": full_set_decision(correct, len(keys), threshold),
                },
                "one_word": _run_row(record.verdicts, saved, model, keys, threshold),
                "json": _run_row(baseline.verdicts, saved, model, keys, threshold),
                "one_word_agree_with_json": _agree(
                    _voted(record.verdicts), _voted(baseline.verdicts), keys
                ),
            }
        )
    return rows


def _group_rows(
    record: JudgeRecord,
    baseline: JudgeRecord,
    inputs: JudgeInputs,
    saved: Grades,
    changed: Sequence[Key],
) -> list[dict[str, Any]]:
    groups = {item.key: reference_group(item.reference) for item in inputs.items}
    one_word, with_json = _voted(record.verdicts), _voted(baseline.verdicts)
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        keys = [key for key in saved if groups[key] == group]
        here = [key for key in changed if groups[key] == group]
        rows.append(
            {
                "group": group,
                "answers": len(keys),
                "changed": len(here),
                "incorrect_again": sum(not one_word[key] for key in here),
                "saved_correct": sum(saved[key] for key in keys),
                "one_word_correct": sum(one_word[key] for key in keys),
                "json_correct": sum(with_json[key] for key in keys),
                "one_word_unequal": _unequal(record.verdicts, keys),
                "json_unequal": _unequal(baseline.verdicts, keys),
                "one_word_agree_with_saved": _agree(one_word, saved, keys),
                "json_agree_with_saved": _agree(with_json, saved, keys),
                "one_word_agree_with_json": _agree(one_word, with_json, keys),
            }
        )
    return rows


def _replies(record: JudgeRecord) -> dict[str, int]:
    """The old parser accepts any text, so count the replies that are not one word."""
    judged = [a for a in record.attempts if a["status"] == SUCCESS]
    return {
        "judgments": len(judged),
        "not_one_word": sum(a["reply"].strip() not in VERDICTS for a in judged),
    }


def _run_settings(record: JudgeRecord) -> dict[str, Any]:
    estimate = record.estimate
    return {
        "judge": judge_settings(record),
        "prompt": {**estimate.document["prompt"], "variant": estimate.variant.name},
        "estimate_sha256": estimate.sha256,
        "approval_url": record.approval_url,
        "usage": usage_summary(record),
    }


def summary_document(
    record: JudgeRecord, baseline: JudgeRecord, inputs: JudgeInputs, loaded: LoadedPolicy
) -> dict[str, Any]:
    """Every measured value of the comparison."""
    check_same_judge(record.estimate, baseline.estimate)
    policy = loaded.benchmarks[AA_LCR]
    # The order of the verdicts: the model, then the question.
    saved = dict(sorted((item.key, item.saved_grade) for item in inputs.items))
    one_word, with_json = _voted(record.verdicts), _voted(baseline.verdicts)
    changed = changed_answers(baseline.verdicts, inputs)
    groups = {item.key: reference_group(item.reference) for item in inputs.items}
    again = sum(not one_word[key] for key in changed)
    return {
        "schema_version": 1,
        "command": "aa-lcr-judge compare",
        "loopback_test": record.estimate.loopback,
        "passes": PASSES,
        "decision_rule": {
            "answers": len(changed),
            "incorrect_again": again,
            "conclusion": conclusion(again),
            "rule": [{"low": low, "high": high, "conclusion": t} for low, high, t in RULE],
            "changed_answers": [
                {
                    "model": key[0],
                    "index": key[1],
                    "reference_group": groups[key],
                    "saved_grade": saved[key],
                    "json_votes": sum(baseline.verdicts[key]),
                    "one_word_votes": sum(record.verdicts[key]),
                    "one_word_majority": one_word[key],
                }
                for key in changed
            ],
        },
        "agreement": {
            "saved_and_one_word": _agreement(saved, one_word),
            "saved_and_json": _agreement(saved, with_json),
            "json_and_one_word": _agreement(with_json, one_word),
        },
        "decisions": {"threshold": policy.threshold, "policy": loaded.key},
        "models": _model_rows(record, baseline, saved, Fraction(str(policy.threshold))),
        "reference_groups": _group_rows(record, baseline, inputs, saved, changed),
        "replies": _replies(record),
        "one_word_run": _run_settings(record),
        "json_run": _run_settings(baseline),
    }


def _prompt_source(prompt: Mapping[str, Any]) -> str:
    tag = f" {prompt['tag']}" if "tag" in prompt else ""
    return f"{prompt['source']}{tag} at `{prompt['commit']}`, {prompt['variant']}"


def _settings_table(summary: Mapping[str, Any]) -> str:
    runs = (summary["json_run"], summary["one_word_run"])

    def row(name: str, *values: object) -> tuple[object, ...]:
        return (name, *values)

    return markdown_table(
        ("Setting", JSON_CONTRACT.title, ONE_WORD.title),
        (
            row("Judge model, requested", *(f"`{r['judge']['model']}`" for r in runs)),
            row(
                "Judge model, returned",
                *(", ".join(r["judge"]["response_models"]) or "not returned" for r in runs),
            ),
            row("Endpoint", *(r["judge"]["base_url"] for r in runs)),
            row("Run dates (UTC)", *(", ".join(r["judge"]["run_dates_utc"]) for r in runs)),
            row("Temperature", *(r["judge"]["temperature"] for r in runs)),
            row("Maximum output tokens", *(r["judge"]["max_tokens"] for r in runs)),
            row("Seed", "none sent", "none sent"),
            row("Prompt source", *(_prompt_source(r["prompt"]) for r in runs)),
            row("Prompts SHA-256", *(f"`{r['prompt']['prompts_sha256']}`" for r in runs)),
            row("Approval", *(r["approval_url"] or "not needed" for r in runs)),
            row("Estimate SHA-256", *(f"`{r['estimate_sha256']}`" for r in runs)),
        ),
    )


def _model_table(summary: Mapping[str, Any]) -> str:
    rows: list[tuple[object, ...]] = []
    for m in summary["models"]:
        saved = m["saved"]
        rows.append((m["model"], "Saved", f"{saved['score']:.2f}", saved["decision"], *["-"] * 4))
        for name, title in (("one_word", ONE_WORD.title), ("json", JSON_CONTRACT.title)):
            run = m[name]
            rows.append(
                (
                    m["model"],
                    title,
                    f"{run['score']:.2f}",
                    run["decision"],
                    ", ".join(f"{s:.2f}" for s in run["pass_scores"]),
                    ", ".join(run["pass_decisions"]),
                    f"{run['unequal']} of {m['answers']}",
                    f"{run['agree_with_saved']} of {m['answers']}",
                )
            )
    return markdown_table(
        (
            "Model",
            "Grades",
            "Score of the majority",
            "Decision",
            "Scores in the passes",
            "Decisions in the passes",
            "Answers with unequal judgments",
            "Agreement with the saved grades",
        ),
        rows,
    )


def _changed_table(summary: Mapping[str, Any]) -> str:
    return markdown_table(
        (
            "Model",
            "Question",
            "Reference answer",
            "CORRECT votes, JSON prompt",
            "CORRECT votes, one-word prompt",
            "Majority, one-word prompt",
        ),
        [
            (
                r["model"],
                r["index"],
                GROUPS[r["reference_group"]],
                f"{r['json_votes']} of {summary['passes']}",
                f"{r['one_word_votes']} of {summary['passes']}",
                "CORRECT" if r["one_word_majority"] else "INCORRECT",
            )
            for r in summary["decision_rule"]["changed_answers"]
        ],
    )


def _group_table(summary: Mapping[str, Any]) -> str:
    return markdown_table(
        (
            "Reference answer",
            "Answers",
            "Changed by the JSON prompt",
            "Of these, INCORRECT again",
            "CORRECT: saved, one-word, JSON",
            "Unequal judgments: one-word, JSON",
            "Agreement with the saved grades: one-word, JSON",
            "Agreement of one-word with JSON",
        ),
        [
            (
                GROUPS[g["group"]],
                g["answers"],
                g["changed"],
                g["incorrect_again"],
                f"{g['saved_correct']}, {g['one_word_correct']}, {g['json_correct']}",
                f"{g['one_word_unequal']}, {g['json_unequal']}",
                f"{g['one_word_agree_with_saved']}, {g['json_agree_with_saved']}",
                g["one_word_agree_with_json"],
            )
            for g in summary["reference_groups"]
        ],
    )


def _agreement_table(summary: Mapping[str, Any]) -> str:
    titles = {
        "saved_and_one_word": "Saved, then one-word prompt",
        "saved_and_json": "Saved, then JSON prompt",
        "json_and_one_word": "JSON prompt, then one-word prompt",
    }
    return markdown_table(
        ("Grades", "Agreement", "INCORRECT to CORRECT", "CORRECT to INCORRECT"),
        [
            (
                title,
                f"{a['agree']} of {a['answers']} ({a['share']:.1%})",
                a["incorrect_to_correct"],
                a["correct_to_incorrect"],
            )
            for title, a in ((t, summary["agreement"][name]) for name, t in titles.items())
        ],
    )


def markdown_report(summary: Mapping[str, Any]) -> bytes:
    rule, usage = summary["decision_rule"], summary["one_word_run"]["usage"]
    replies, judge = summary["replies"], summary["one_word_run"]["judge"]
    test_note = (
        "**This is a loopback test with a scripted judge. It measures nothing.**\n\n"
        if summary["loopback_test"]
        else ""
    )
    rule_table = markdown_table(
        (f"Answers of the {rule['answers']} that are INCORRECT again", "Conclusion"),
        [(f"{r['low']} to {r['high']}", r["conclusion"]) for r in rule["rule"]],
    )
    text = f"""# The old one-word judge prompt on the saved AA-LCR answers (#88)

{test_note}The control run sent each saved answer to the judge {summary["passes"]} times, with the old one-word prompt.
It used the judge and the endpoint of the JSON run (#76). It generated no new answer.
Each grade of a run is the majority of {summary["passes"]} judgments.

## Result

{rule["incorrect_again"]} of the {rule["answers"]} answers are INCORRECT again.
**{rule["conclusion"]}.**

Issue #88 fixed this rule before the run. It covers the {rule["answers"]} answers that the JSON prompt changed from INCORRECT to CORRECT:

{rule_table}

{_changed_table(summary)}

## Agreement on all answers

{_agreement_table(summary)}

## The three sets of grades

The threshold is {summary["decisions"]["threshold"]:.2f}. The saved data has one judgment for each answer.

{_model_table(summary)}

## Reference answers

The table gives the number of answers in each cell.

{_group_table(summary)}

## Settings

{_settings_table(summary)}

## Replies and cost

- {replies["not_one_word"]} of {replies["judgments"]:,} one-word judgments come from a reply that is not exactly CORRECT or INCORRECT. The old parser looks for the word CORRECT in any reply.
- The run made {usage["requests"]:,} requests. {usage["replies_outside_the_contract"]} replies were empty. {usage["requests_with_no_usable_reply"]} requests had no usable reply. The run rejected {usage["rejected_replies"]} replies. None of these became INCORRECT. The run repeated these requests, and `judgments.jsonl` keeps all of them.
- The tokens were {usage["input_tokens"]:,} input and {usage["output_tokens"]:,} output. {usage["requests_with_no_token_count"]} requests had no token count.
- The cost was at most ${usage["cost_bound_usd"]:.4f} at the prices of the estimate. The limit was ${usage["limit_usd"]:.2f}.

## Limits

- One run on another day does not separate the prompt from the endpoint, the precision, and the date of the saved judgments. The saved reviews record no endpoint and no precision.
- The two prompts also have different maximum output tokens. These are the defaults of the two EvalScope versions.
- The saved data has one judgment for each answer. A majority of {summary["passes"]} judgments can differ from one judgment of the same judge.
- The comparison shows which grades agree. It does not show which grades are correct.
- The temperature was {judge["temperature"]}. All one-word judgments ran on the dates above.
- EvalScope grades an empty reply and a transport error as INCORRECT. This run rejects them.
- Policy v1 and the recorded outputs of #76 do not change.
"""  # noqa: E501
    # A model name from the endpoint can hold half of a character.
    return text.encode("utf-8", errors="replace")


def _answers_table(
    record: JudgeRecord, baseline: JudgeRecord, inputs: JudgeInputs, changed: Sequence[Key]
) -> bytes:
    passes = range(1, PASSES + 1)
    items = {item.key: item for item in inputs.items}
    return csv_table(
        (
            "model",
            "index",
            "reference_group",
            "changed_by_json_prompt",
            "saved_grade",
            *(f"one_word_pass_{n}" for n in passes),
            "one_word_votes",
            "one_word_majority",
            *(f"json_pass_{n}" for n in passes),
            "json_votes",
            "json_majority",
        ),
        [
            (
                *key,
                reference_group(items[key].reference),
                int(key in changed),
                items[key].saved_grade,
                *votes,
                sum(votes),
                majority(votes),
                *baseline.verdicts[key],
                sum(baseline.verdicts[key]),
                majority(baseline.verdicts[key]),
            )
            for key, votes in record.verdicts.items()
        ],
    )


def _scores_table(summary: Mapping[str, Any]) -> bytes:
    """The pass ``majority`` is the vote of the 5 judgments of each answer."""
    rows: list[tuple[object, ...]] = []
    for m in summary["models"]:
        for name in ("saved", "one_word", "json"):
            run, size = m[name], m["answers"]
            if name != "saved":
                passes = zip(
                    run["pass_correct"], run["pass_scores"], run["pass_decisions"], strict=True
                )
                rows.extend(
                    (m["model"], name, number, correct, size, score, decision)
                    for number, (correct, score, decision) in enumerate(passes, start=1)
                )
            label = "saved" if name == "saved" else "majority"
            rows.append(
                (m["model"], name, label, run["correct"], size, run["score"], run["decision"])
            )
    return csv_table(("model", "grades", "pass", "correct", "answers", "score", "decision"), rows)


def build_outputs(
    record: JudgeRecord, baseline: JudgeRecord, inputs: JudgeInputs, loaded: LoadedPolicy
) -> dict[str, bytes]:
    """All output files, with the manifest hashing the others."""
    summary = summary_document(record, baseline, inputs, loaded)
    changed = changed_answers(baseline.verdicts, inputs)
    outputs = {
        JUDGMENTS: judgment_lines(record),
        SETTINGS: record.settings_bytes,
        "answers.csv": _answers_table(record, baseline, inputs, changed),
        "scores.csv": _scores_table(summary),
        "summary.json": encode_json(summary),
        "report.md": markdown_report(summary),
    }
    outputs["manifest.json"] = encode_json(
        {
            "schema_version": 1,
            "command": "aa-lcr-judge compare",
            "loopback_test": record.estimate.loopback,
            "inputs": dict(inputs.files),
            "baseline_run": {
                JUDGMENTS: hashlib.sha256(judgment_lines(baseline)).hexdigest(),
                SETTINGS: hashlib.sha256(baseline.settings_bytes).hexdigest(),
            },
            "policy": {"key": loaded.key, "sha256": loaded.sha256},
            "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
            "implementation_sha256": code_hashes(IMPLEMENTATION_FILES),
            "output_sha256": {n: hashlib.sha256(d).hexdigest() for n, d in outputs.items()},
        }
    )
    return outputs
