"""The judge run against a scripted loopback judge: prompts, retries, budget, and the key."""

import dataclasses
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from judge_fixtures import MODELS, QUESTIONS, Data, Scripted, scripted_judge, verdict, write_data

from benchmark_reference import judge_run
from benchmark_reference.judge_estimate import (
    Estimate,
    Prices,
    build_estimate,
    check_url,
    load_estimate,
    model_key,
)
from benchmark_reference.judge_items import JudgeInputs, load_judge_inputs
from benchmark_reference.judge_prompt import parse_reply, prompt_sha256, render_prompt
from benchmark_reference.judge_run import Reply, RunResult, read_attempts, run_judge
from benchmark_reference.models import AnalysisError

ANSWERS = len(MODELS) * QUESTIONS
PRICES = Prices(Fraction("0.09"), Fraction("0.55"), "test prices", "2026-11-23")
QWEN = "Qwen/Qwen3-235B-A22B-Instruct-2507"
PAID_URL = "https://judge.invalid/v1"
APPROVAL = "https://github.com/sdv1708/ai-model-benchmark/issues/76#issuecomment-1"
KEY = "test-key-0123456789"
CORRECT = '{"reasoning": "", "verdict": "CORRECT"}'


def _load(data: Data) -> JudgeInputs:
    return load_judge_inputs(panel_path=data.panel, data_root=data.root, source_csv=data.csv)


@pytest.fixture
def inputs(tmp_path: Path) -> JudgeInputs:
    return _load(write_data(tmp_path))


def _estimate(inputs: JudgeInputs, url: str, **changes: Any) -> Estimate:
    settings: dict[str, Any] = {
        "judge_model": QWEN,
        "prices": PRICES,
        "limit_usd": Fraction(10),
        **changes,
    }
    return load_estimate(build_estimate(inputs, base_url=url, **settings))


def _run(estimate: Estimate, inputs: JudgeInputs, folder: Path, **changes: Any) -> RunResult:
    settings: dict[str, Any] = {
        "key": None,
        "approval_url": None,
        "sleep": lambda _seconds: None,
        **changes,
    }
    return run_judge(estimate, inputs, run_dir=folder, **settings)


def _post(
    monkeypatch: pytest.MonkeyPatch, reply: Callable[[str | None], Reply]
) -> list[str | None]:
    """Replace the network with a function, for the tests of a paid endpoint."""
    keys: list[str | None] = []

    def post(_estimate: Estimate, _payload: object, key: str | None) -> Reply:
        keys.append(key)
        return reply(key)

    monkeypatch.setattr(judge_run, "post", post)
    return keys


# The prompt and the parser


def test_prompt_has_the_adapter_text_and_the_output_contract() -> None:
    assert render_prompt(question="Q {x}?", reference="R", answer=" A {y}") == (
        "Assess whether the following CANDIDATE ANSWER is CORRECT or INCORRECT. For the "
        "CANDIDATE ANSWER to be correct, it must be consistent with the OFFICIAL ANSWER.\n\n"
        "The question, for reference only: Q {x}?\n"
        "The OFFICIAL ANSWER: R\n"
        "CANDIDATE ANSWER TO ASSESS:  A {y}\n\n"
        "Reply only with CORRECT or INCORRECT.\n\n"
        "Reply with a single JSON object and no other text, containing these required keys "
        "(additional keys are allowed):\n"
        '- "reasoning": a string\n'
        '- "verdict": exactly one of "CORRECT" or "INCORRECT"'
    )


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (CORRECT, "CORRECT"),
        ('```json\n{"verdict": "INCORRECT", "extra": {"a": 1}}\n```', "INCORRECT"),
        ('{"reasoning": "a } brace", "verdict": "CORRECT"}', "CORRECT"),
        ("CORRECT", None),
        ("", None),
        ('{"verdict": "correct"}', None),
        ('{"verdict": "CORRECT"}{"verdict": "INCORRECT"}', None),
        ('{"reasoning": null, "verdict": "CORRECT"}', None),
        ('{"verdict": ["CORRECT"]}', None),
        ('{"verdict": "CORRECT"', None),
    ],
)
def test_only_one_valid_json_verdict_counts(reply: str, expected: str | None) -> None:
    assert parse_reply(reply).verdict == expected


# The saved answers


def test_items_join_each_answer_to_its_reference_by_fingerprint(inputs: JudgeInputs) -> None:
    assert [i.key for i in inputs.items] == [(m, n) for m in MODELS for n in range(QUESTIONS)]
    item = next(i for i in inputs.items if i.key == ("model-b", 7))
    assert (item.reference, item.answer) == ("Reference 7", " Answer 7 of model-b.")
    assert inputs.original_judge == "qwen-3-235b-a22b-instruct-2507"


@pytest.mark.parametrize("changed", ["csv", "review"])
def test_a_changed_input_file_stops_the_load(tmp_path: Path, changed: str) -> None:
    data = write_data(tmp_path)
    review = data.root / "Part 1" / "reviews" / f"aa_lcr__{MODELS[0]}.jsonl"
    path = data.csv if changed == "csv" else review
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(AnalysisError, match="not the recorded"):
        _load(data)


# The estimate


def test_estimate_records_calls_and_prices_and_checks_the_judge(inputs: JudgeInputs) -> None:
    estimate = _estimate(inputs, PAID_URL)
    calls = estimate.document["calls"]
    assert (calls["judgments"], calls["max_requests"]) == (ANSWERS * 5, ANSWERS * 15)
    assert estimate.same_judge is True
    tokens, cost = estimate.document["tokens"], estimate.document["cost_usd"]
    assert tokens["expected"]["output"] == ANSWERS * 5 * 120
    by_hand = (tokens["expected"]["input"] * 0.09 + tokens["expected"]["output"] * 0.55) / 1e6
    assert cost["expected"] == pytest.approx(by_hand, abs=1e-4)
    assert 0 < cost["expected"] < cost["high"]


def test_estimate_refuses_another_judge_unless_the_owner_permits_it(inputs: JudgeInputs) -> None:
    with pytest.raises(AnalysisError, match="requires the original judge"):
        _estimate(inputs, PAID_URL, judge_model="gpt-4.1-mini")
    other = _estimate(inputs, PAID_URL, judge_model="gpt-4.1-mini", allow_different_judge=True)
    assert other.same_judge is False


def test_estimate_accepts_any_judge_when_the_reviews_name_none(tmp_path: Path) -> None:
    inputs = _load(write_data(tmp_path, judge=None))
    assert _estimate(inputs, PAID_URL, judge_model="any-judge").same_judge is None


def test_provider_names_of_one_model_are_equal() -> None:
    assert model_key(QWEN) == model_key("qwen-3-235b-a22b-instruct-2507")
    assert model_key(QWEN) != model_key("Qwen/Qwen3-235B-A22B-Thinking-2507")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://user:secret@example.com/v1",
        "https://example.com/v1?key=secret",
        "file:///tmp/x",
    ],
)
def test_the_endpoint_must_be_a_plain_https_address(url: str) -> None:
    with pytest.raises(AnalysisError):
        check_url(url)


# The run on loopback


def test_run_makes_five_independent_calls_for_each_answer(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        estimate = _estimate(inputs, judge.url)
        result = _run(estimate, inputs, tmp_path / "run")
    assert (result.complete, result.judgments, result.stopped) == (True, ANSWERS * 5, None)
    assert judge.seen == {item.prompt: 5 for item in inputs.items}
    assert set(judge.paths) == {"/v1/chat/completions"}
    for body in judge.bodies:
        assert [m["role"] for m in body["messages"]] == ["user"]
        assert (body["model"], body["temperature"], body["max_tokens"]) == (QWEN, 0.0, 4096)
        assert set(body) == {"model", "messages", "temperature", "max_tokens"}
    # No credential goes to a loopback judge.
    assert not any("authorization" in {k.lower() for k in h} for h in judge.headers)
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    assert len(attempts) == ANSWERS * 5
    assert {a["prompt_sha256"] for a in attempts} == {prompt_sha256(i.prompt) for i in inputs.items}
    assert result.cost_bound == ANSWERS * 5 * PRICES.cost(300, 20)


def test_run_keeps_failed_attempts_and_repeats_them(inputs: JudgeInputs, tmp_path: Path) -> None:
    def script(_prompt: str, number: int) -> Scripted:
        if number == 1:
            return Scripted("CORRECT")
        if number == 2:
            return Scripted(status=429, headers={"Retry-After": "7"})
        return verdict(False)

    waits: list[float] = []
    with scripted_judge(script) as judge:
        result = _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", sleep=waits.append)
    assert result.complete
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    status = [a["status"] for a in attempts]
    assert status.count("parse_error") == status.count("transport_error") == ANSWERS
    assert status.count("success") == ANSWERS * 5
    assert {a["reply"] for a in attempts if a["status"] == "parse_error"} == {"CORRECT"}
    assert waits and set(waits) == {7.0}


def test_run_stops_at_a_request_limit_and_continues_later(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        estimate = _estimate(inputs, judge.url)
        first = _run(estimate, inputs, tmp_path / "run", max_new_requests=7)
        assert (first.judgments, first.new_requests, first.complete) == (7, 7, False)
        # The first requests are pass 1 only, so a stopped run holds complete passes.
        attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
        assert {a["pass"] for a in attempts} == {1}
        second = _run(estimate, inputs, tmp_path / "run")
    assert second.complete
    assert second.new_requests == ANSWERS * 5 - 7
    assert judge.seen == {item.prompt: 5 for item in inputs.items}


def test_run_never_passes_the_cost_limit(inputs: JudgeInputs, tmp_path: Path) -> None:
    # A reply with no token count costs the highest possible amount of its request.
    with scripted_judge(lambda _prompt, _n: Scripted(usage=None)) as judge:
        estimate = _estimate(inputs, judge.url, limit_usd=Fraction("0.02"))
        result = _run(estimate, inputs, tmp_path / "run")
        assert result.stopped is not None and "cost limit" in result.stopped
        assert 0 < result.cost_bound <= Fraction("0.02")
        assert not result.complete
        again = _run(estimate, inputs, tmp_path / "run")
    assert again.new_requests == 0


def test_run_counts_every_request_against_the_request_limit(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    with scripted_judge(lambda _prompt, _n: Scripted("no verdict")) as judge:
        estimate = _estimate(inputs, judge.url)
        first = _run(estimate, inputs, tmp_path / "run")
        second = _run(estimate, inputs, tmp_path / "run")
    assert first.new_requests == ANSWERS * 15 and len(first.failed_slots) == ANSWERS * 5
    assert second.new_requests == 0
    assert second.stopped is not None and "requests of the estimate" in second.stopped


@pytest.mark.parametrize("status", [302, 400, 401, 402, 404])
def test_a_refused_request_stops_the_run_and_keeps_no_server_text(
    inputs: JudgeInputs, tmp_path: Path, status: int
) -> None:
    headers = {"Location": "http://127.0.0.1:9/steal"} if status == 302 else {}
    reply = Scripted(status=status, raw=b'{"error": "secret echo"}', headers=headers)
    with scripted_judge(lambda _prompt, _n: reply) as judge:
        result = _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", workers=1)
    assert result.new_requests == 1
    assert result.stopped == f"the endpoint refused the request with HTTP {status}"
    text = (tmp_path / "run" / "judgments.jsonl").read_text(encoding="utf-8")
    assert "secret echo" not in text
    assert result.cost_bound == 0


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"choices": []}'])
def test_a_malformed_reply_is_a_failed_attempt(
    inputs: JudgeInputs, tmp_path: Path, raw: bytes
) -> None:
    with scripted_judge(lambda _prompt, _n: Scripted(raw=raw)) as judge:
        result = _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", max_new_requests=3)
    assert result.judgments == 0
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    assert {a["status"] for a in attempts} == {"transport_error"}
    assert result.cost_bound > 0


@pytest.mark.parametrize("text", ["\u2028", "\u0085", "\ud800", "caf\u00e9"])
def test_any_reply_text_survives_the_record(inputs: JudgeInputs, tmp_path: Path, text: str) -> None:
    reply = Scripted(json.dumps({"reasoning": "x", "verdict": "CORRECT"}) + text)
    with scripted_judge(lambda _prompt, _n: reply) as judge:
        estimate = _estimate(inputs, judge.url)
        _run(estimate, inputs, tmp_path / "run", max_new_requests=2)
        attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
        assert [a["reply"] for a in attempts] == [reply.content] * 2
        assert _run(estimate, inputs, tmp_path / "run", max_new_requests=2).judgments == 4


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (Scripted(model="Qwen/Qwen3.5-9B"), "another model"),
        (Scripted(identity="cached"), "repeated the reply"),
    ],
)
def test_a_reply_that_is_not_independent_stops_the_run(
    inputs: JudgeInputs, tmp_path: Path, reply: Scripted, message: str
) -> None:
    with scripted_judge(lambda _prompt, _n: reply) as judge:
        result = _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", workers=1)
    assert result.stopped is not None and message in result.stopped
    last = read_attempts(tmp_path / "run" / "judgments.jsonl")[-1]
    assert (last["status"], last["verdict"]) == ("rejected", None)
    assert Fraction(last["cost_bound_usd"]) > 0


def test_a_server_fault_counts_at_the_highest_cost(inputs: JudgeInputs, tmp_path: Path) -> None:
    def script(_prompt: str, _number: int) -> Scripted:
        return Scripted(status=504)

    with scripted_judge(script) as judge:
        estimate = _estimate(inputs, judge.url, limit_usd=Fraction("0.02"))
        result = _run(estimate, inputs, tmp_path / "run")
    assert 0 < result.cost_bound <= Fraction("0.02")
    assert result.stopped is not None and "cost limit" in result.stopped


def test_an_interrupt_stops_the_run_and_releases_the_lock(
    inputs: JudgeInputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, calls = judge_run._wait, []

    def wait(threads: Any) -> None:
        calls.append(threads)
        if len(calls) == 1:
            raise KeyboardInterrupt
        real(threads)

    monkeypatch.setattr(judge_run, "_wait", wait)
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        result = _run(_estimate(inputs, judge.url), inputs, tmp_path / "run")
    assert result.stopped == "the user stopped the run" and not result.complete
    assert not (tmp_path / "run" / "run.lock").exists()


def test_the_lock_stays_while_a_worker_is_active(
    inputs: JudgeInputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def script(_prompt: str, _number: int) -> Scripted:
        release.wait(10)
        return verdict(True)

    def wait(_threads: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(judge_run, "_wait", wait)
    with scripted_judge(script) as judge:
        estimate = _estimate(inputs, judge.url)
        with pytest.raises(KeyboardInterrupt):
            _run(estimate, inputs, tmp_path / "run")
        assert (tmp_path / "run" / "run.lock").exists()
        with pytest.raises(AnalysisError, match="Another run"):
            _run(estimate, inputs, tmp_path / "run")
        release.set()


def test_an_estimate_with_other_line_ends_is_refused(inputs: JudgeInputs) -> None:
    data = build_estimate(
        inputs, base_url=PAID_URL, judge_model=QWEN, prices=PRICES, limit_usd=Fraction(1)
    )
    with pytest.raises(AnalysisError, match="line ends"):
        load_estimate(data.replace(b"\n", b"\r\n"))


def test_a_price_must_be_an_exact_decimal(inputs: JudgeInputs) -> None:
    with pytest.raises(AnalysisError, match="exact decimal"):
        _estimate(inputs, PAID_URL, limit_usd=Fraction(1, 3))


@pytest.mark.parametrize(
    "change", [{"cost_bound_usd": "-1"}, {"cost_bound_usd": "1/0"}, {"attempt": 0}]
)
def test_a_changed_attempt_stops_the_command(
    inputs: JudgeInputs, tmp_path: Path, change: dict[str, Any]
) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", max_new_requests=1)
    path = tmp_path / "run" / "judgments.jsonl"
    path.write_text(json.dumps({**json.loads(path.read_bytes()), **change}) + "\n", newline="\n")
    with pytest.raises(AnalysisError, match="damaged attempt"):
        read_attempts(path)


# A paid endpoint: no test calls one


def test_a_paid_run_needs_the_approval_comment_and_the_key(
    inputs: JudgeInputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _post(monkeypatch, lambda _key: Reply(error="no call", status=500, billable=False))
    estimate = _estimate(inputs, PAID_URL)
    run = tmp_path / "run"
    other_issue = APPROVAL.replace("/76#", "/78#")
    for approval in (None, "yes", APPROVAL.split("#")[0], other_issue):
        with pytest.raises(AnalysisError, match="approval-url"):
            _run(estimate, inputs, run, key=KEY, approval_url=approval)
    for key in (None, ""):
        with pytest.raises(AnalysisError, match="needs the judge key"):
            _run(estimate, inputs, run, key=key, approval_url=APPROVAL)
    for key in (f"{KEY}\n", f"{KEY} x", "clé"):
        with pytest.raises(AnalysisError, match="invalid character") as fault:
            _run(estimate, inputs, run, key=key, approval_url=APPROVAL)
        assert KEY not in str(fault.value)
    assert calls == [] and not run.exists()


def test_a_loopback_run_refuses_a_key(inputs: JudgeInputs, tmp_path: Path) -> None:
    estimate = _estimate(inputs, "http://127.0.0.1:9/v1")
    with pytest.raises(AnalysisError, match="takes no key"):
        _run(estimate, inputs, tmp_path / "run", key=KEY)


def test_the_key_reaches_the_judge_and_never_a_file(
    inputs: JudgeInputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {
        "provider": f"echo-{KEY}",
        "choices": [{"message": {"content": f"{KEY} {CORRECT}"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    keys = _post(monkeypatch, lambda _key: Reply(body=body))
    result = _run(
        _estimate(inputs, PAID_URL),
        inputs,
        tmp_path / "run",
        key=KEY,
        approval_url=APPROVAL,
        max_new_requests=4,
    )
    assert keys == [KEY] * 4 and result.judgments == 4
    for path in (tmp_path / "run").iterdir():
        assert KEY not in path.read_text(encoding="utf-8")


def test_the_authorization_header_holds_the_key(inputs: JudgeInputs) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        payload = {"model": "m", "messages": [{"role": "user", "content": "p"}]}
        judge_run.post(_estimate(inputs, judge.url), payload, KEY)
    assert judge.headers[0]["Authorization"] == f"Bearer {KEY}"


# The run folder


def test_a_run_folder_belongs_to_one_estimate(inputs: JudgeInputs, tmp_path: Path) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", max_new_requests=1)
        other = _estimate(inputs, judge.url, limit_usd=Fraction(20))
        with pytest.raises(AnalysisError, match="another estimate"):
            _run(other, inputs, tmp_path / "run")


def test_a_run_refuses_changed_prompts(inputs: JudgeInputs, tmp_path: Path) -> None:
    estimate = _estimate(inputs, "http://127.0.0.1:9/v1")
    first = dataclasses.replace(inputs.items[0], answer="Another answer.")
    changed = dataclasses.replace(inputs, items=(first, *inputs.items[1:]))
    with pytest.raises(AnalysisError, match="prompts differ"):
        _run(estimate, changed, tmp_path / "run")


def test_a_run_refuses_a_second_writer_and_a_damaged_record(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    run = tmp_path / "run"
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        estimate = _estimate(inputs, judge.url)
        _run(estimate, inputs, run, max_new_requests=1)
        (run / "run.lock").touch()
        with pytest.raises(AnalysisError, match="Another run"):
            _run(estimate, inputs, run)
        (run / "run.lock").unlink()
        with (run / "judgments.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"pass": 1')
        with pytest.raises(AnalysisError, match="not complete"):
            _run(estimate, inputs, run)
    assert not (run / "run.lock").exists()


def test_each_record_has_the_utc_time_of_its_request(inputs: JudgeInputs, tmp_path: Path) -> None:
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        _run(_estimate(inputs, judge.url), inputs, tmp_path / "run", max_new_requests=1)
    (record,) = read_attempts(tmp_path / "run" / "judgments.jsonl")
    started = datetime.fromisoformat(record["started_at"])
    assert started.utcoffset() is not None
    assert abs((datetime.now(UTC) - started).total_seconds()) < 60
    assert json.loads((tmp_path / "run" / "run.json").read_bytes())["approval_url"] is None
