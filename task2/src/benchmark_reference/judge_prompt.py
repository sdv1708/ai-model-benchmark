"""The AA-LCR judge prompt and reply parser of the EvalScope pruning repository.

This module copies two parts of that repository with no change in behavior. The
parts are the prompt of the AA-LCR adapter and the output contract.
``tools/audit_judge_prompt.py`` compares this copy with a checkout of the
repository: it compares every rendered prompt and the result of every test reply.

The adapter prompt ends with "Reply only with CORRECT or INCORRECT." The contract
then asks for a JSON object. The adapter sends both, so this module sends both.
"""

import hashlib
import json
from dataclasses import dataclass

SOURCE = "https://github.com/sdv1708/evalscope-pruning"
SOURCE_COMMIT = "67fbe5e092a4739d23f5d8cc95319d8b19dc1a24"
SOURCE_FILES = (
    "evalscope/benchmarks/aa_lcr/aa_lcr_adapter.py",
    "evalscope/api/judge/contracts.py",
)

JUDGE_PROMPT = (
    "Assess whether the following CANDIDATE ANSWER is CORRECT or INCORRECT. "
    "For the CANDIDATE ANSWER to be correct, it must be consistent with the OFFICIAL ANSWER.\n"
    "\n"
    "The question, for reference only: {question}\n"
    "The OFFICIAL ANSWER: {correct_answer}\n"
    "CANDIDATE ANSWER TO ASSESS: {response}\n"
    "\n"
    "Reply only with CORRECT or INCORRECT."
)
CONTRACT_INSTRUCTION = (
    "\n\nReply with a single JSON object and no other text, containing these required keys "
    "(additional keys are allowed):\n"
    '- "reasoning": a string\n'
    '- "verdict": exactly one of "CORRECT" or "INCORRECT"'
)
VERDICTS = ("CORRECT", "INCORRECT")


def render_prompt(*, question: str, reference: str, answer: str) -> str:
    """The exact text of the one user message of a judge call."""
    return (
        JUDGE_PROMPT.format(question=question, correct_answer=reference, response=answer)
        + CONTRACT_INSTRUCTION
    )


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ParsedReply:
    """``verdict`` is None when the reply does not satisfy the output contract."""

    verdict: str | None
    error: str | None = None


def parse_reply(reply: str) -> ParsedReply:
    """Read the verdict. A reply outside the contract is an error, never a zero score."""
    if not reply:
        return ParsedReply(None, "empty response")
    payloads = _payloads(reply)
    if len(payloads) != 1:
        return ParsedReply(None, f"{len(payloads)} JSON objects found where one is required")
    try:
        value = json.loads(payloads[0])
    except (ValueError, RecursionError):
        return ParsedReply(None, "the JSON object is not valid")
    if not isinstance(value.get("reasoning", ""), str):
        return ParsedReply(None, "reasoning is not a string")
    verdict = value.get("verdict")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        return ParsedReply(None, "verdict is not CORRECT or INCORRECT")
    return ParsedReply(verdict)


def _payloads(text: str) -> list[str]:
    """Every top-level JSON object of the reply, with the scan of the contract."""
    found: list[str] = []
    depth = start = 0
    in_string = escaped = False
    for position, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = position
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                found.append(text[start : position + 1])
    return found
