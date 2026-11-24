"""The two AA-LCR judge prompts, each with its reply parser and its settings.

``JSON_CONTRACT`` is the prompt of the EvalScope pruning repository (#76). This module
copies two parts of that repository with no change in behavior: the prompt of the
AA-LCR adapter and the output contract. The adapter prompt ends with "Reply only with
CORRECT or INCORRECT." The contract then asks for a JSON object. The adapter sends
both, so this module sends both. ``tools/audit_judge_prompt.py`` compares the copy with
a checkout of the repository.

``ONE_WORD`` is the prompt of EvalScope v1.4.2 (#88): the same adapter prompt with no
contract. ``tools/audit_old_judge_prompt.py`` compares it with the source at that tag.
"""

import hashlib
import json
import re
from collections.abc import Callable
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


def parse_one_word_reply(reply: str) -> ParsedReply:
    """Read the verdict with the rule of EvalScope v1.4.2: is the word CORRECT in the reply?

    EvalScope also grades an empty reply and a transport error as INCORRECT. Here an
    empty reply is an error, and the run never gives the parser a transport error.
    """
    if not reply.strip():
        return ParsedReply(None, "empty response")
    return ParsedReply(
        "CORRECT" if re.search(r"\bCORRECT\b", reply, re.IGNORECASE) else "INCORRECT"
    )


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


@dataclass(frozen=True, slots=True)
class PromptVariant:
    """One judge prompt: its parser, its source, its settings, and the issue of its run.

    The output tokens are the expected and the high count of one reply, for the estimate.
    """

    name: str
    title: str
    issue: str
    source: str
    commit: str
    tag: str | None
    files: tuple[str, ...]
    suffix: str
    parse: Callable[[str], ParsedReply]
    max_tokens: int
    expected_output_tokens: int
    high_output_tokens: int

    def render(self, *, question: str, reference: str, answer: str) -> str:
        """The exact text of the one user message of a judge call."""
        return (
            JUDGE_PROMPT.format(question=question, correct_answer=reference, response=answer)
            + self.suffix
        )


_ISSUES = "https://github.com/sdv1708/ai-model-benchmark/issues/"
JSON_CONTRACT = PromptVariant(
    name="json-contract",
    title="JSON prompt",
    issue=f"{_ISSUES}76",
    source=SOURCE,
    commit=SOURCE_COMMIT,
    tag=None,
    files=SOURCE_FILES,
    suffix=CONTRACT_INSTRUCTION,
    parse=parse_reply,
    max_tokens=4096,
    expected_output_tokens=120,
    high_output_tokens=300,
)
ONE_WORD = PromptVariant(
    name="one-word",
    title="One-word prompt",
    issue=f"{_ISSUES}88",
    source="https://github.com/modelscope/evalscope",
    commit="457dc8cbc2539aca173b4a71bcb29e352804d4af",
    tag="v1.4.2",
    files=("evalscope/benchmarks/aa_lcr/aa_lcr_adapter.py", "evalscope/metrics/llm_judge.py"),
    suffix="",
    parse=parse_one_word_reply,
    max_tokens=1024,
    expected_output_tokens=3,
    high_output_tokens=20,
)
VARIANTS = {variant.name: variant for variant in (JSON_CONTRACT, ONE_WORD)}


def render_prompt(*, question: str, reference: str, answer: str) -> str:
    """The JSON prompt of #76."""
    return JSON_CONTRACT.render(question=question, reference=reference, answer=answer)
