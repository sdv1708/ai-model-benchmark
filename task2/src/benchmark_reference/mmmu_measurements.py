"""Descriptive paired measurements with explicit QA and missing-outcome bounds."""

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from benchmark_reference.mmmu_images import (
    digest,
    load_json,
    object_value,
    sequence,
    text,
)
from benchmark_reference.mmmu_requests import build_plan, load_bundle

QA_STATES = {"pending", "labels_preserved", "invalid", "destructive_control"}
ATTEMPT_STATES = {"completed", "http_error", "timeout", "truncated", "rejected"}


def normalize_answer(value: str) -> str:
    return " ".join(value.casefold().split())


def score_answer(raw: str, sample: dict[str, Any]) -> tuple[str | None, int]:
    """Frozen strict format, no random fallback and no implicit semantic/numeric judge."""
    match = re.fullmatch(r"ANSWER:[ \t]*([^\r\n]+)", raw.strip())
    if not match:
        return None, 0
    answer = match[1].strip()
    if sample["options"]:
        if len(answer) != 1 or answer not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: len(sample["options"])]:
            return None, 0
        return answer, int(answer in sample["accepted_answers"])
    answer = normalize_answer(answer)
    if not answer:
        return None, 0
    return answer, int(answer in {normalize_answer(a) for a in sample["accepted_answers"]})


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        row
        for row in rows
        if row["original_score"] is not None and row["transformed_score"] is not None
    ]
    comparable = [
        row
        for row in complete
        if row["original_answer"] is not None and row["transformed_answer"] is not None
    ]
    count = len(complete)
    expected = len(rows)
    lower = sum(
        (r["original_score"] if r["original_score"] is not None else 0)
        - (r["transformed_score"] if r["transformed_score"] is not None else 1)
        for r in rows
    )
    upper = sum(
        (r["original_score"] if r["original_score"] is not None else 1)
        - (r["transformed_score"] if r["transformed_score"] is not None else 0)
        for r in rows
    )
    original = sum(r["original_score"] for r in complete) / count if count else None
    transformed = sum(r["transformed_score"] for r in complete) / count if count else None
    return {
        "unique_questions": len({r["sample_id"] for r in rows}),
        "expected_paired_attempts": expected,
        "complete_paired_attempts": count,
        "coverage": count / expected,
        "original_accuracy": original,
        "transformed_accuracy": transformed,
        "accuracy_drop_pp": (
            100 * (original - transformed)
            if original is not None and transformed is not None
            else None
        ),
        "accuracy_drop_bounds_pp": [100 * lower / expected, 100 * upper / expected],
        "answer_consistency": (
            sum(r["original_answer"] == r["transformed_answer"] for r in comparable)
            / len(comparable)
            if comparable
            else None
        ),
        "consistency_denominator": len(comparable),
        "error_categories": dict(sorted(Counter(r["category"] for r in rows).items())),
    }


def paired_report(
    root: Path, plan_path: Path, responses_path: Path, qa_path: Path
) -> dict[str, Any]:
    """Join by frozen attempt IDs, not row order. Never makes a population/live conclusion."""
    bundle = load_bundle(root)
    plan = object_value(load_json(plan_path))
    expected_plan = build_plan(root, plan["profile"], plan["repeats"], plan["schedule_seed"])
    if plan != expected_plan:
        raise ValueError("Request plan does not match this bundle/protocol")
    responses = object_value(load_json(responses_path))
    kind = responses.get("evidence_kind")
    if kind not in {"synthetic", "saved_endpoint_records"}:
        raise ValueError("evidence_kind must be synthetic or saved_endpoint_records")
    if responses.get("plan_sha256") != digest(plan_path.read_bytes()):
        raise ValueError("Responses are bound to a different request plan")
    calls = {call["attempt_id"]: call for call in plan["calls"]}
    samples = {sample["sample_id"]: sample for sample in bundle["samples"]}
    outcomes: dict[tuple[str, int], dict[str, Any]] = {}
    seen: set[str] = set()
    response_states: Counter[str] = Counter()
    resolved_models: set[str] = set()
    for raw in sequence(responses.get("attempts")):
        attempt = object_value(raw)
        attempt_id = text(attempt.get("attempt_id"))
        if attempt_id not in calls or attempt_id in seen:
            raise ValueError("Unknown or duplicate attempt_id")
        seen.add(attempt_id)
        call = calls[attempt_id]
        if attempt.get("request_sha256") != call["request_sha256"]:
            raise ValueError("Response request hash mismatch")
        state = attempt.get("status")
        if not isinstance(state, str) or state not in ATTEMPT_STATES:
            raise ValueError("Invalid attempt status")
        response_states[state] += 1
        answer, grade = None, None
        if state == "completed":
            if attempt.get("finish_reason") != "stop":
                raise ValueError(
                    "Completed attempts need finish_reason=stop; use truncated otherwise"
                )
            raw_answer = attempt.get("raw_answer")
            if not isinstance(raw_answer, str):
                raise ValueError(
                    "Completed attempt needs string raw_answer (empty is a format failure)"
                )
            answer, grade = score_answer(raw_answer, samples[call["sample_id"]])
            if kind == "saved_endpoint_records":
                text(attempt.get("response_id"))
                resolved_models.add(text(attempt.get("resolved_model")))
        outcomes[call["condition_id"], call["repeat"]] = {
            "answer": answer,
            "score": grade,
            "status": state,
        }
    response_states["missing"] = len(calls) - len(seen)

    pair_ids = {pair["pair_id"] for pair in bundle["pairs"]}
    qa: dict[str, dict[str, Any]] = {}
    for raw in sequence(load_json(qa_path)):
        annotation = object_value(raw)
        pair_id = text(annotation.get("pair_id"))
        if pair_id not in pair_ids or pair_id in qa:
            raise ValueError("Unknown or duplicate QA pair_id")
        status = annotation.get("status")
        if not isinstance(status, str) or status not in QA_STATES:
            raise ValueError("Invalid QA status")
        if status == "labels_preserved":
            reviewers = [text(r) for r in sequence(annotation.get("reviewers"))]
            if len({reviewer.strip().casefold() for reviewer in reviewers}) < 2:
                raise ValueError("Label preservation needs two distinct reviewers")
            text(annotation.get("notes"))
        qa[pair_id] = annotation

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    qa_counts: Counter[str] = Counter()
    details = []
    missing = {"answer": None, "score": None, "status": "missing"}
    for pair in bundle["pairs"]:
        pair_id, sample_id = pair["pair_id"], pair["sample_id"]
        status = qa.get(pair_id, {}).get("status", "pending")
        qa_counts[status] += 1
        pair_rows = []
        for repeat in range(plan["repeats"]):
            original = outcomes.get((sample_id, repeat), missing)
            transformed = outcomes.get((pair_id, repeat), missing)
            a, b = original["score"], transformed["score"]
            if a is None or b is None:
                category = "missing_or_transport"
            elif original["answer"] is None or transformed["answer"] is None:
                category = "format_failure"
            elif a == b == 1:
                category = "stable_correct"
            elif a == 1:
                category = "regression"
            elif b == 1:
                category = "improvement"
            elif original["answer"] == transformed["answer"]:
                category = "stable_wrong"
            else:
                category = "changed_wrong"
            row = {
                "sample_id": sample_id,
                "repeat": repeat,
                "original_score": a,
                "transformed_score": b,
                "original_answer": original["answer"],
                "transformed_answer": transformed["answer"],
                "original_status": original["status"],
                "transformed_status": transformed["status"],
                "category": category,
            }
            pair_rows.append(row)
            if status == "labels_preserved":
                groups[pair["transform"]["name"], pair["transform"]["severity"]].append(row)
        details.append(
            {
                "pair_id": pair_id,
                "source_id": pair["source_id"],
                "qa_status": status,
                "transform": pair["transform"],
                "attempts": pair_rows,
            }
        )
    return {
        "protocol": bundle["protocol"],
        "evidence_kind": kind,
        "endpoint_evidence_independently_verified": False,
        "full_live_model_conclusion": False,
        "encoder_causal_claim": False,
        "population_estimate": False,
        "input_sha256": {
            "bundle": digest((root / "manifest.json").read_bytes()),
            "plan": digest(plan_path.read_bytes()),
            "responses": digest(responses_path.read_bytes()),
            "qa": digest(qa_path.read_bytes()),
        },
        "scorer_sha256": digest(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
        "profile": plan["profile"],
        "resolved_models": sorted(resolved_models),
        "resolved_model_drift": len(resolved_models) > 1,
        "response_coverage": dict(sorted(response_states.items())),
        "qa_counts": dict(sorted(qa_counts.items())),
        "inapplicable": bundle["inapplicable"],
        "metric_scope": "Unweighted diagnostics by transform/severity on QA-approved pairs",
        "accuracy_denominator": "Complete paired attempts; completed format failures score zero",
        "bounds_meaning": "Worst/best missing-outcome bounds; these are not confidence intervals",
        "uncertainty": "No sampling CI; repeats and shared originals are clustered by question",
        "groups": [
            {"transform": name, "severity": severity, **summarize(rows)}
            for (name, severity), rows in sorted(groups.items())
        ],
        "pairs": details,
    }
