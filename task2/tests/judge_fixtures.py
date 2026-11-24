"""A small synthetic AA-LCR data set and a scripted judge on loopback. No credentials."""

import csv
import hashlib
import io
import json
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from benchmark_reference.public_lcb import question_fingerprint

MODELS = ("model-a", "model-b", "model-c")
QUESTIONS = 40
SAVED_JUDGE = "qwen-3-235b-a22b-instruct-2507"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def saved_grade(model: str, index: int) -> int:
    return int((index + MODELS.index(model)) % 3 != 0)


@dataclass(frozen=True, slots=True)
class Data:
    panel: Path
    root: Path
    csv: Path

    @property
    def arguments(self) -> list[str]:
        return [
            *("--panel", str(self.panel)),
            *("--data-root", str(self.root)),
            *("--source-csv", str(self.csv)),
        ]


def write_data(
    folder: Path, *, judge: str | None = SAVED_JUDGE, references: Mapping[int, str] | None = None
) -> Data:
    """A panel, saved reviews, and reference answers with consistent hashes.

    ``references`` replaces the reference answer of some questions.
    """
    answers = {i: f"Reference {i}" for i in range(QUESTIONS)} | dict(references or {})
    questions = [f"What is the value of item {i}, with {{braces}}?" for i in range(QUESTIONS)]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("question", "answer"))
    # The file order differs from the panel order, so the join cannot use the position.
    writer.writerows((q, answers[i]) for i, q in reversed(list(enumerate(questions))))
    csv_path = folder / "AA-LCR_Dataset.csv"
    csv_path.write_bytes(buffer.getvalue().encode("utf-8"))
    root = folder / "Evals"
    reviews = root / "Part 1" / "reviews"
    reviews.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for model in MODELS:
        lines = []
        for i in range(QUESTIONS):
            metadata = {"source": "llm_judge"} | ({"model": judge} if judge else {})
            score = {
                "value": {"acc": float(saved_grade(model, i))},
                "extracted_prediction": f" Answer {i} of {model}.",
                "metadata": metadata,
            }
            lines.append(json.dumps({"index": i, "sample_score": {"score": score}}) + "\n")
        data = "".join(lines).encode("utf-8")
        (reviews / f"aa_lcr__{model}.jsonl").write_bytes(data)
        hashes[f"Part 1/reviews/aa_lcr__{model}.jsonl"] = _sha(data)
    panel = {
        "schema_version": 1,
        "provenance": {
            "benchmark": "aa_lcr",
            "source_sha256": hashes,
            "source_verification": {"csv_sha256": _sha(csv_path.read_bytes())},
        },
        "tasks": [
            {
                "index": i,
                "question_sha256": question_fingerprint(q),
                "scores": {m: saved_grade(m, i) for m in MODELS},
                "input_tokens": 1000 + i,
                "source_urls": [f"https://example.com/{n}" for n in range(1 + i % 3)],
            }
            for i, q in enumerate(questions)
        ],
    }
    panel_path = folder / "aa-lcr-reference-panel.json"
    panel_path.write_text(json.dumps(panel), encoding="utf-8")
    return Data(panel_path, root, csv_path)


@dataclass(slots=True)
class Judge:
    """What the scripted endpoint received. ``seen`` counts the calls of each prompt."""

    url: str = ""
    bodies: list[dict[str, Any]] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    seen: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Scripted:
    """One scripted HTTP reply."""

    content: str | None = '{"reasoning": "It agrees.", "verdict": "CORRECT"}'
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)
    raw: bytes | None = None
    model: str | None = None
    identity: str | None = None
    finish_reason: str = "stop"
    error: Any = None
    usage: Mapping[str, int] | None = field(
        default_factory=lambda: {"prompt_tokens": 300, "completion_tokens": 20}
    )


type Script = Callable[[str, int], Scripted]


def verdict(correct: bool) -> Scripted:
    label = "CORRECT" if correct else "INCORRECT"
    return Scripted(json.dumps({"reasoning": "Scripted.", "verdict": label}))


@contextmanager
def scripted_judge(script: Script) -> Iterator[Judge]:
    """An OpenAI-compatible endpoint on 127.0.0.1. ``script`` gets the prompt and its call count."""
    state, lock = Judge(), threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            prompt = body["messages"][0]["content"]
            with lock:
                state.bodies.append(body)
                state.headers.append(dict(self.headers.items()))
                state.paths.append(self.path)
                state.seen[prompt] = state.seen.get(prompt, 0) + 1
                number = state.seen[prompt]
                call = len(state.bodies)
            reply = script(prompt, number)
            document: dict[str, Any] = {
                "id": reply.identity or f"call-{call}",
                "object": "chat.completion",
                "model": reply.model or body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": reply.finish_reason,
                        "message": {"role": "assistant", "content": reply.content},
                    }
                ],
            }
            if reply.error is not None:
                document["error"] = reply.error
            if reply.usage is not None:
                document["usage"] = dict(reply.usage)
            data = reply.raw if reply.raw is not None else json.dumps(document).encode("utf-8")
            self.send_response(reply.status)
            for name, value in reply.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
