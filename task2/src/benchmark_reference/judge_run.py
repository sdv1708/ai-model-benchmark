"""Send each saved answer to the judge 5 times, and keep every attempt.

The order is pass by pass: each pass covers every answer one time. Each judgment is
one new request with one user message, so no judgment sees another judgment.

``judgments.jsonl`` holds one line for each attempt. An attempt is one request. An
attempt with a verdict is a judgment. A second run of the same command continues
after the judgments that the file holds.

Three guards protect the budget and the key:

- The run stops before the next request could pass the cost limit of the estimate.
- The key comes from an environment variable. The run never writes it. The record of
  an HTTP error holds the status code only, because a server can repeat the key.
- The client does not follow a redirect, so the key goes to the approved host only.
"""

import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

from benchmark_reference.judge_estimate import (
    MAX_ATTEMPTS,
    PASSES,
    Estimate,
    model_key,
)
from benchmark_reference.judge_items import JudgeInputs, JudgeItem
from benchmark_reference.judge_prompt import prompt_sha256
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import write_atomic

JUDGMENTS = "judgments.jsonl"
SETTINGS = "run.json"
SUCCESS, PARSE_ERROR, TRANSPORT_ERROR = "success", "parse_error", "transport_error"
# A reply from another model, or a repeated reply. It is not an independent judgment.
REJECTED = "rejected"
STATUSES = (SUCCESS, PARSE_ERROR, TRANSPORT_ERROR, REJECTED)
TIMEOUT_SECONDS = 120
_RETRY_STATUS = {408, 409, 425, 429}
# The bytes of the chat template around the one message. It is a generous bound.
_TEMPLATE_TOKENS = 64
type Slot = tuple[int, str, int]


class StopRun(Exception):
    """A fault that the next request would repeat. Nothing is wrong with the record."""


@dataclass(frozen=True, slots=True)
class Reply:
    """One HTTP reply, or the reason that there is none."""

    body: Mapping[str, Any] | None = None
    error: str | None = None
    status: int | None = None
    retry_after: float | None = None
    # A lost reply, a timeout, or a server fault can have a cost.
    billable: bool = True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@lru_cache
def _opener(loopback: bool) -> urllib.request.OpenerDirector:
    if loopback:
        return urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(_NoRedirect())


def _retry_after(value: str | None) -> float | None:
    return min(float(value), 60.0) if value and re.fullmatch(r"\d+(\.\d+)?", value) else None


def post(estimate: Estimate, payload: Mapping[str, Any], key: str | None) -> Reply:
    """One chat-completion request. It gives a fault as data and never as key text."""
    headers = {"Content-Type": "application/json", "User-Agent": "aa-lcr-judge/1"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        f"{estimate.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with _opener(estimate.loopback).open(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            wait = _retry_after(exc.headers.get("Retry-After"))
        billable = exc.code >= 500 or exc.code == 408
        return Reply(error=f"HTTP {exc.code}", status=exc.code, retry_after=wait, billable=billable)
    except (OSError, http.client.HTTPException) as exc:
        # The text of the exception can hold request data, so keep the type only.
        return Reply(error=type(exc).__name__)
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        return Reply(error="The reply body is not JSON")
    if not isinstance(body, dict):
        return Reply(error="The reply body is not a JSON object")
    return Reply(body=body)


def _payload(estimate: Estimate, item: JudgeItem) -> dict[str, Any]:
    return {
        "model": estimate.judge_model,
        "messages": [{"role": "user", "content": item.prompt}],
        "temperature": estimate.temperature,
        "max_tokens": estimate.max_tokens,
    }


def _call_bound(estimate: Estimate, item: JudgeItem) -> Fraction:
    """The highest cost of one request. A text has at most one token for each UTF-8 byte."""
    tokens = len(item.prompt.encode("utf-8")) + _TEMPLATE_TOKENS
    return estimate.prices.cost(tokens, estimate.max_tokens)


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _content(body: Mapping[str, Any]) -> tuple[str, str | None] | None:
    """The reply text and the finish reason, or None when the reply has no message."""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    text, reason = message.get("content"), choices[0].get("finish_reason")
    if text is not None and not isinstance(text, str):
        return None
    return text or "", reason if isinstance(reason, str) else None


def _attempt_record(
    estimate: Estimate, item: JudgeItem, slot: Slot, number: int, started: datetime, reply: Reply
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "pass": slot[0],
        "model": item.model,
        "index": item.index,
        "attempt": number,
        "started_at": started.isoformat(timespec="milliseconds"),
        "prompt_sha256": prompt_sha256(item.prompt),
        "status": TRANSPORT_ERROR,
        "verdict": None,
        "error": reply.error,
        "reply": None,
        "finish_reason": None,
        "response_model": None,
        "response_id": None,
        "provider": None,
        "system_fingerprint": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_bound_usd": "0",
    }
    bound = _call_bound(estimate, item)
    if reply.body is None:
        record["cost_bound_usd"] = str(bound if reply.billable else Fraction(0))
        return record
    body = reply.body
    for name, source in (
        ("response_model", "model"),
        ("response_id", "id"),
        ("provider", "provider"),
        ("system_fingerprint", "system_fingerprint"),
    ):
        value = body.get(source)
        record[name] = value if isinstance(value, str) else None
    usage = body.get("usage")
    if isinstance(usage, dict):
        record["input_tokens"] = _count(usage.get("prompt_tokens"))
        record["output_tokens"] = _count(usage.get("completion_tokens"))
    if record["input_tokens"] is None or record["output_tokens"] is None:
        record["cost_bound_usd"] = str(bound)
    else:
        record["cost_bound_usd"] = str(
            estimate.prices.cost(record["input_tokens"], record["output_tokens"])
        )
    content = _content(body)
    if content is None:
        record["error"] = "The reply has no message"
        return record
    record["reply"], record["finish_reason"] = content
    # The old parser reads any text, so the text of an error must not reach it.
    if body.get("error") is not None or record["finish_reason"] == "error":
        record["error"] = "The reply carries an error of the endpoint"
        return record
    parsed = estimate.variant.parse(content[0])
    record["status"] = PARSE_ERROR if parsed.verdict is None else SUCCESS
    record["verdict"], record["error"] = parsed.verdict, parsed.error
    return record


def _scrub(value: Any, key: str | None) -> Any:
    """Remove the key from any text that a server returned."""
    if key is None:
        return value
    if isinstance(value, str):
        return value.replace(key, "[removed]")
    if isinstance(value, dict):
        return {k: _scrub(v, key) for k, v in value.items()}
    return value


def read_attempts(path: Path) -> list[dict[str, Any]]:
    """Every recorded attempt. A damaged line stops the command, because it can have a cost."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise AnalysisError(f"The last line of {path} is not complete. Check the file by hand.")
    attempts: list[dict[str, Any]] = []
    for number, line in enumerate(text.split("\n")[:-1], start=1):
        try:
            record = json.loads(line)
            slot_of(record)
            attempt = record["attempt"]
            if Fraction(record["cost_bound_usd"]) < 0 or record["status"] not in STATUSES:
                raise ValueError("invalid cost or status")
            if type(attempt) is not int or attempt < 1:
                raise ValueError("invalid attempt number")
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
            raise AnalysisError(f"{path}:{number}: damaged attempt") from exc
        attempts.append(record)
    return attempts


def slot_of(record: Mapping[str, Any]) -> Slot:
    return record["pass"], record["model"], record["index"]


@dataclass(slots=True)
class RunResult:
    """``complete`` is true when every slot has a verdict. ``stopped`` gives a reason to stop.

    ``limited`` is true when the reason is the request limit of the user.
    """

    judgments: int
    needed: int
    new_requests: int
    cost_bound: Fraction
    stopped: str | None = None
    limited: bool = False
    failed_slots: list[Slot] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.judgments == self.needed


class _Runner:
    """Shared state of the worker threads. ``lock`` protects every field and the file."""

    def __init__(
        self,
        estimate: Estimate,
        *,
        key: str | None,
        path: Path,
        attempts: Sequence[Mapping[str, Any]],
        max_new_requests: int | None,
        sleep: Callable[[float], None],
    ) -> None:
        self.estimate, self.key, self.path, self.sleep = estimate, key, path, sleep
        self.lock = threading.Lock()
        self.spent = sum((Fraction(a["cost_bound_usd"]) for a in attempts), Fraction(0))
        self.reserved = Fraction(0)
        self.requests = len(attempts)
        self.new_requests = 0
        self.max_new_requests = max_new_requests
        self.judgments = sum(a["status"] == SUCCESS for a in attempts)
        self.numbers: dict[Slot, int] = {}
        for attempt in attempts:
            slot = slot_of(attempt)
            self.numbers[slot] = max(self.numbers.get(slot, 0), attempt["attempt"])
        self.response_ids = {
            a["response_id"] for a in attempts if a["status"] == SUCCESS and a["response_id"]
        }
        self.stopped: str | None = None
        self.limited = False
        self.failed: list[Slot] = []

    def stop(self, reason: str) -> None:
        with self.lock:
            self.stopped = self.stopped or reason

    def _reserve(self, slot: Slot, bound: Fraction) -> int:
        with self.lock:
            if self.stopped:
                raise StopRun(self.stopped)
            if self.max_new_requests is not None and self.new_requests >= self.max_new_requests:
                self.stopped = f"the run reached --max-requests {self.max_new_requests}"
                self.limited = True
            elif self.requests >= self.estimate.max_requests:
                self.stopped = f"the run reached {self.requests} requests of the estimate"
            elif self.spent + self.reserved + bound > self.estimate.limit_usd:
                self.stopped = (
                    f"the next request could pass the cost limit of "
                    f"${float(self.estimate.limit_usd):.2f}"
                )
            if self.stopped:
                raise StopRun(self.stopped)
            self.reserved += bound
            self.requests += 1
            self.new_requests += 1
            self.numbers[slot] = self.numbers.get(slot, 0) + 1
            return self.numbers[slot]

    def _write(self, record: dict[str, Any], bound: Fraction) -> None:
        with self.lock:
            self._check_source(record)
            # ASCII output: a reply can hold a Unicode line end or half of a character.
            line = json.dumps(_scrub(record, self.key), sort_keys=True) + "\n"
            self.reserved -= bound
            self.spent += Fraction(record["cost_bound_usd"])
            self.judgments += record["status"] == SUCCESS
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)

    def _check_source(self, record: dict[str, Any]) -> None:
        """Reject a reply of another model, and a reply that the endpoint repeats."""
        returned, identity = record["response_model"], record["response_id"]
        fault = None
        if returned is not None and model_key(returned) != model_key(self.estimate.judge_model):
            fault = f"the endpoint returned another model, {returned!r}"
        elif identity is not None and identity in self.response_ids:
            fault = f"the endpoint repeated the reply {identity!r}"
        if fault is not None:
            record.update(status=REJECTED, verdict=None, error=fault)
            self.stopped = self.stopped or _scrub(fault, self.key)
        elif record["status"] == SUCCESS and identity is not None:
            self.response_ids.add(identity)

    def judge(self, slot: Slot, item: JudgeItem) -> None:
        """Up to ``MAX_ATTEMPTS`` requests for one judgment."""
        bound = _call_bound(self.estimate, item)
        for attempt in range(MAX_ATTEMPTS):
            number = self._reserve(slot, bound)
            started = datetime.now(UTC)
            reply = post(self.estimate, _payload(self.estimate, item), self.key)
            record = _attempt_record(self.estimate, item, slot, number, started, reply)
            self._write(record, bound)
            if record["status"] in (SUCCESS, REJECTED):
                return
            status = reply.status
            if status is not None and status < 500 and status not in _RETRY_STATUS:
                self.stop(f"the endpoint refused the request with HTTP {status}")
                return
            if attempt + 1 < MAX_ATTEMPTS and record["status"] == TRANSPORT_ERROR:
                self.sleep(reply.retry_after if reply.retry_after is not None else 2.0**attempt)
        with self.lock:
            self.failed.append(slot)


def check_approval_url(approval_url: str | None, issue: str) -> None:
    """The URL must be a comment on the issue, where the owner approves the estimate."""
    if approval_url is None or not re.fullmatch(
        re.escape(issue) + r"#issuecomment-\d+", approval_url
    ):
        raise AnalysisError(
            f"A paid run needs --approval-url with the comment of the owner on {issue} "
            "that approves this estimate"
        )


def check_approval(estimate: Estimate, approval_url: str | None, key: str | None) -> None:
    """A paid run needs the approval comment and the key. A loopback run takes no key."""
    if estimate.loopback:
        if key is not None:
            raise AnalysisError("A loopback run takes no key. Remove it, so that no test sends it")
        return
    check_approval_url(approval_url, estimate.variant.issue)
    if not key:
        raise AnalysisError("A paid run needs the judge key in the environment variable")
    # The HTTP library puts an invalid header value in its error text, so check it here.
    if not re.fullmatch(r"[!-~]+", key):
        raise AnalysisError("The judge key has a space, a line end, or another invalid character")


def _settings(estimate: Estimate, approval_url: str | None) -> bytes:
    return encode_json(
        {
            "schema_version": 1,
            "command": "aa-lcr-judge run",
            "estimate_sha256": estimate.sha256,
            "approval_url": approval_url,
            "estimate": dict(estimate.document),
        }
    )


def _claim(run_dir: Path, settings: bytes) -> Path:
    """Bind the folder to one estimate, and refuse a second writer."""
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = run_dir / "run.lock"
    # The lock comes first, so that a second command cannot replace the settings of a run.
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise AnalysisError(
            f"{lock} exists. Another run uses this folder. If no run is active, delete the file."
        ) from None
    try:
        path = run_dir / SETTINGS
        if path.exists():
            if path.read_bytes() != settings:
                raise AnalysisError(f"{run_dir} holds a run of another estimate or approval")
        elif (run_dir / JUDGMENTS).exists():
            raise AnalysisError(f"{run_dir} holds judgments with no {SETTINGS}")
        else:
            write_atomic(path, settings)
    except BaseException:
        lock.unlink(missing_ok=True)
        raise
    return lock


def _wait(threads: Sequence[threading.Thread]) -> None:
    """Wait in short steps. On Windows, a wait with no limit also blocks Ctrl+C."""
    while any(thread.is_alive() for thread in threads):
        for thread in threads:
            thread.join(0.1)


def run_judge(
    estimate: Estimate,
    inputs: JudgeInputs,
    *,
    run_dir: Path,
    key: str | None,
    approval_url: str | None,
    workers: int = 4,
    max_new_requests: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> RunResult:
    """Fill every missing judgment, within the limits of the estimate."""
    check_approval(estimate, approval_url, key)
    if workers < 1 or (max_new_requests is not None and max_new_requests < 1):
        raise AnalysisError("--workers and --max-requests must be 1 or more")
    inputs = inputs.for_variant(estimate.variant)
    if inputs.prompts_sha256 != estimate.prompts_sha256:
        raise AnalysisError("The prompts differ from the prompts of the estimate")
    lock = _claim(run_dir, _settings(estimate, approval_url))
    threads: list[threading.Thread] = []
    try:
        path = run_dir / JUDGMENTS
        attempts = read_attempts(path)
        done = {slot_of(a) for a in attempts if a["status"] == SUCCESS}
        slots: list[tuple[Slot, JudgeItem]] = [
            ((number, item.model, item.index), item)
            for number in range(1, PASSES + 1)
            for item in inputs.items
        ]
        if done - {slot for slot, _ in slots}:
            raise AnalysisError(f"{path} holds a judgment of another answer")
        todo = iter([pair for pair in slots if pair[0] not in done])
        runner = _Runner(
            estimate,
            key=key,
            path=path,
            attempts=attempts,
            max_new_requests=max_new_requests,
            sleep=sleep,
        )
        faults: list[BaseException] = []

        def work() -> None:
            try:
                while True:
                    with runner.lock:
                        pair = next(todo, None)
                    if pair is None:
                        return
                    runner.judge(*pair)
            except StopRun:
                return
            except BaseException as exc:
                runner.stop("a worker had a fault")
                faults.append(exc)

        threads.extend(threading.Thread(target=work) for _ in range(workers))
        for thread in threads:
            thread.start()
        try:
            _wait(threads)
        except KeyboardInterrupt:
            runner.stop("the user stopped the run")
            _wait(threads)
        if faults:
            raise faults[0]
        return RunResult(
            judgments=runner.judgments,
            needed=len(slots),
            new_requests=runner.new_requests,
            cost_bound=runner.spent,
            stopped=runner.stopped,
            limited=runner.limited,
            failed_slots=sorted(runner.failed),
        )
    finally:
        # An active worker can still write, so the lock stays until the last one ends.
        if not any(thread.is_alive() for thread in threads):
            lock.unlink(missing_ok=True)
