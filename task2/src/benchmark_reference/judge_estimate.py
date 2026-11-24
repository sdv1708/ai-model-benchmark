"""The written estimate of a judge run. The run takes every setting from this file.

The owner approves one estimate file. ``aa-lcr-judge run`` reads the endpoint, the
judge model, the prices, and the cost limit from that file only. A run can therefore
not use a setting that the owner did not approve.

The token counts are estimates, because the project does not hold the judge tokenizer:

- Expected input: one token for each digit, and one for each 4 other characters.
- High input: one token for each digit, and one for each 2.5 other characters.
- Expected and high output: a fixed count for each reply.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any
from urllib.parse import urlsplit

from benchmark_reference.judge_items import JudgeInputs
from benchmark_reference.judge_prompt import SOURCE, SOURCE_COMMIT, SOURCE_FILES
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError

SCHEMA_VERSION = 1
ISSUE = "https://github.com/sdv1708/ai-model-benchmark/issues/76"
PASSES = 5
MAX_ATTEMPTS = 3
EXPECTED_OUTPUT_TOKENS = 120
HIGH_OUTPUT_TOKENS = 300
# The defaults of the EvalScope judge. The saved reviews do not record the settings.
TEMPERATURE = 0.0
MAX_TOKENS = 4096
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True, slots=True)
class Prices:
    """US dollars for one million tokens, their source, and the date of the reading."""

    input: Fraction
    output: Fraction
    source: str
    read_on: str

    def cost(self, input_tokens: int, output_tokens: int) -> Fraction:
        return (self.input * input_tokens + self.output * output_tokens) / 1_000_000


@dataclass(frozen=True, slots=True)
class Estimate:
    """A validated estimate file and the SHA-256 of its exact bytes."""

    sha256: str
    document: Mapping[str, Any]
    base_url: str
    judge_model: str
    original_judge: str | None
    temperature: float
    max_tokens: int
    prices: Prices
    limit_usd: Fraction
    max_requests: int
    prompts_sha256: str

    @property
    def loopback(self) -> bool:
        return is_loopback(self.base_url)

    @property
    def same_judge(self) -> bool | None:
        return same_model(self.original_judge, self.judge_model)


def is_loopback(url: str) -> bool:
    return urlsplit(url).hostname in _LOOPBACK


def check_url(url: str) -> str:
    """Only HTTPS, or HTTP to this computer. A URL must not hold a key or a user name."""
    parts = urlsplit(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and is_loopback(url)):
        raise AnalysisError("The judge URL must use HTTPS, or HTTP on loopback")
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise AnalysisError("The judge URL must be a plain address with no key and no query")
    return url.rstrip("/")


def model_key(name: str) -> str:
    """Provider names of one model differ in the prefix, the case, and the separators."""
    return re.sub(r"[^a-z0-9]", "", name.rsplit("/", 1)[-1].lower())


def same_model(original: str | None, judge: str) -> bool | None:
    """True or False when the saved reviews name the judge, else None."""
    return None if original is None else model_key(original) == model_key(judge)


def _tokens(text: str, characters_per_token: float) -> int:
    digits = sum(c.isdigit() for c in text)
    return digits + math.ceil((len(text) - digits) / characters_per_token)


def _decimal(value: Fraction) -> str:
    """Exact decimal text, so that a reader can check the price. Reject 1/3 and the like."""
    number = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(number) != value:
        raise AnalysisError(f"{value} is not an exact decimal number")
    return f"{number:f}"


def _usd(value: Fraction) -> float:
    return round(float(value), 4)


def build_estimate(
    inputs: JudgeInputs,
    *,
    base_url: str,
    judge_model: str,
    prices: Prices,
    limit_usd: Fraction,
    allow_different_judge: bool = False,
) -> bytes:
    """The estimate document. It stops when the judge is not the judge of the saved reviews."""
    original = inputs.original_judge
    same = same_model(original, judge_model)
    if same is False and not allow_different_judge:
        raise AnalysisError(
            f"The saved reviews name the judge {original!r}, not {judge_model!r}. Issue #76 "
            "requires the original judge. Use --allow-different-judge only when the owner "
            "approves another judge."
        )
    prompts = [item.prompt for item in inputs.items]
    calls = len(prompts) * PASSES
    expected_input = PASSES * sum(_tokens(p, 4) for p in prompts)
    high_input = PASSES * sum(_tokens(p, 2.5) for p in prompts)
    expected_output = calls * EXPECTED_OUTPUT_TOKENS
    high_output = calls * HIGH_OUTPUT_TOKENS
    document = {
        "schema_version": SCHEMA_VERSION,
        "command": "aa-lcr-judge estimate",
        "issue": ISSUE,
        "judge": {
            "model": judge_model,
            "original_model": original,
            "same_judge": same,
            "base_url": check_url(base_url),
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        },
        "prompt": {
            "source": SOURCE,
            "commit": SOURCE_COMMIT,
            "files": list(SOURCE_FILES),
            "prompts_sha256": inputs.prompts_sha256,
        },
        "inputs": dict(inputs.files),
        "calls": {
            "answers": len(prompts),
            "judgments_per_answer": PASSES,
            "judgments": calls,
            "max_requests": calls * MAX_ATTEMPTS,
        },
        "tokens": {
            "expected": {"input": expected_input, "output": expected_output},
            "high": {"input": high_input, "output": high_output},
        },
        "prices_usd_per_million": {
            "input": _decimal(prices.input),
            "output": _decimal(prices.output),
            "source": prices.source,
            "read_on": prices.read_on,
        },
        "cost_usd": {
            "expected": _usd(prices.cost(expected_input, expected_output)),
            "high": _usd(prices.cost(high_input, high_output)),
            "limit": _decimal(limit_usd),
        },
    }
    data = encode_json(document)
    load_estimate(data)
    return data


def _fraction(value: object, name: str) -> Fraction:
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise AnalysisError(f"Estimate {name} must be a number") from exc
    if number < 0:
        raise AnalysisError(f"Estimate {name} must not be negative")
    return number


def load_estimate(data: bytes) -> Estimate:
    """Validate an estimate file."""
    try:
        document = json.loads(data)
        judge, prices, calls = (
            document["judge"],
            document["prices_usd_per_million"],
            document["calls"],
        )
        if document["schema_version"] != SCHEMA_VERSION:
            raise AnalysisError("The estimate has an unknown schema")
        # The report hashes the document again, so the file must have the same bytes.
        if encode_json(document) != data:
            raise AnalysisError(
                "The estimate file differs from the written form. Check its line ends"
            )
        if calls["judgments_per_answer"] != PASSES or calls["max_requests"] != (
            calls["judgments"] * MAX_ATTEMPTS
        ):
            raise AnalysisError("The estimate has another call count than this command")
        limit = _fraction(document["cost_usd"]["limit"], "limit")
        if limit <= 0:
            raise AnalysisError("The cost limit must be above zero")
        return Estimate(
            sha256=hashlib.sha256(data).hexdigest(),
            document=document,
            base_url=check_url(judge["base_url"]),
            judge_model=str(judge["model"]),
            original_judge=judge["original_model"],
            temperature=float(judge["temperature"]),
            max_tokens=int(judge["max_tokens"]),
            prices=Prices(
                _fraction(prices["input"], "input price"),
                _fraction(prices["output"], "output price"),
                str(prices["source"]),
                str(prices["read_on"]),
            ),
            limit_usd=limit,
            max_requests=int(calls["max_requests"]),
            prompts_sha256=str(document["prompt"]["prompts_sha256"]),
        )
    except AnalysisError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise AnalysisError(f"The estimate file is not valid: {exc}") from exc


def console_lines(estimate: Estimate) -> list[str]:
    doc = estimate.document
    tokens, cost, calls = doc["tokens"], doc["cost_usd"], doc["calls"]
    return [
        f"Judge: {estimate.judge_model} at {estimate.base_url} "
        f"(judge of the saved reviews: {estimate.original_judge or 'not recorded'})",
        f"Judgments: {calls['judgments']:,}; at most {calls['max_requests']:,} requests",
        f"Expected: {tokens['expected']['input']:,} input and "
        f"{tokens['expected']['output']:,} output tokens, ${cost['expected']:.2f}",
        f"High: {tokens['high']['input']:,} input and "
        f"{tokens['high']['output']:,} output tokens, ${cost['high']:.2f}",
        f"Cost limit: ${float(estimate.limit_usd):.2f}. The run stops before it passes the limit.",
        f"Estimate SHA-256: {estimate.sha256}",
    ]
