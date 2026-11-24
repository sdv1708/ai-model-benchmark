"""Compare the one-word judge prompt and its parser with EvalScope at the pinned tag.

Put the two source files of EvalScope v1.4.2 in one folder, with their repository paths.
The tool checks the SHA-256 of each file, and stops when a file differs. It makes no
model call, needs no key, and does not install or import EvalScope.

It takes ``JUDGE_PROMPT`` and the method ``llm_match_score`` from the source file of the
adapter, and runs that method with a scripted judge. It then compares the prompt of every
saved answer, the verdict of a set of replies, and the default judge settings.

One difference is intended. EvalScope grades an empty reply and a transport error as
INCORRECT. The run of this project rejects both, and sends the request again.
"""

import argparse
import ast
import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmark_reference.judge_estimate import TEMPERATURE
from benchmark_reference.judge_items import load_judge_inputs
from benchmark_reference.judge_prompt import ONE_WORD

# The SHA-256 of each file at the pinned commit, after CRLF-to-LF normalization.
SHA256 = {
    "evalscope/benchmarks/aa_lcr/aa_lcr_adapter.py": (
        "24532e77ead15a8f03ffb5040b120d9c33580821c799672579f875deb1be5297"
    ),
    "evalscope/metrics/llm_judge.py": (
        "7b791efc75ef39c5b7a03cb649ead3cfa67c7e160c38eea9011e80629d872081"
    ),
}
REPLIES = (
    "CORRECT",
    "INCORRECT",
    "correct",
    "Incorrect.",
    " CORRECT\n",
    "**CORRECT**",
    "CORRECT.",
    "CORRECTLY",
    "UNCORRECT",
    "_CORRECT_",
    "NOT CORRECT",
    "INCORRECT, not CORRECT",
    "The candidate answer is CORRECT because it agrees.",
    '{"reasoning": "It agrees.", "verdict": "CORRECT"}',
    '{"reasoning": "It differs.", "verdict": "INCORRECT"}',
    "I cannot tell.",
    "ÉCORRECT",
)
# These replies are an intended difference: EvalScope gives INCORRECT.
NO_VERDICT = ("", " \n")
type Grade = Callable[[str, str, str, str], tuple[str, bool]]


def _source(root: Path, name: str) -> str:
    data = (root / name).read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256[name]:
        print(f"audit-old-judge-prompt: {name} has SHA-256 {digest}", file=sys.stderr)
        raise SystemExit(2)
    return data.decode("utf-8")


def _grade(source: str) -> Grade:
    """The method of the adapter. It gives the prompt that it sends and its verdict."""
    tree = ast.parse(source)
    prompt = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "JUDGE_PROMPT"
    )
    adapter = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AALCRAdapter"
    )
    method = next(
        node
        for node in adapter.body
        if isinstance(node, ast.FunctionDef) and node.name == "llm_match_score"
    )
    names: dict[str, Any] = {"re": re, "Score": SimpleNamespace, "TaskState": object}
    module = ast.Module(body=[prompt, method], type_ignores=[])
    exec(compile(module, "aa_lcr_adapter.py", "exec"), names)

    def grade(question: str, reference: str, answer: str, reply: str) -> tuple[str, bool]:
        sent: list[str] = []

        def judge(prompt: str) -> str:
            sent.append(prompt)
            return reply

        adapter_state = SimpleNamespace(
            llm_judge=SimpleNamespace(judge=judge, model_id="judge"), judge_strategy="auto"
        )
        score = names["llm_match_score"](
            adapter_state,
            answer,
            answer,
            reference,
            SimpleNamespace(metadata={"question": question}),
        )
        (prompt_text,) = sent
        return prompt_text, score.value["acc"] == 1.0

    return grade


def _default_settings(source: str) -> list[dict[str, Any]]:
    """Every literal of the default generation settings in the judge source."""
    return [
        ast.literal_eval(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "max_tokens" for k in node.keys)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evalscope", type=Path, required=True, help="Folder of the source files")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    args = parser.parse_args()

    def stop(message: str) -> None:
        parser.exit(2, f"audit-old-judge-prompt: {message}\n")

    if set(ONE_WORD.files) != set(SHA256):
        stop("the estimate names other source files")
    adapter_file, judge_file = ONE_WORD.files
    grade = _grade(_source(args.evalscope, adapter_file))
    settings = _default_settings(_source(args.evalscope, judge_file))
    ours = {"temperature": TEMPERATURE, "max_tokens": ONE_WORD.max_tokens}
    if settings != [ours]:
        stop(f"the default settings are {settings}, not {ours}")
    inputs = load_judge_inputs(
        panel_path=args.panel, data_root=args.data_root, source_csv=args.source_csv
    ).for_variant(ONE_WORD)
    for item in inputs.items:
        prompt, _correct = grade(item.question, item.reference, item.answer, "CORRECT")
        if prompt != item.prompt:
            stop(f"the prompt differs for {item.key}")
    for reply in REPLIES:
        _prompt, correct = grade("Q", "R", "A", reply)
        if ONE_WORD.parse(reply).verdict != ("CORRECT" if correct else "INCORRECT"):
            stop(f"the parser differs for {reply!r}")
    for reply in NO_VERDICT:
        _prompt, correct = grade("Q", "R", "A", reply)
        if correct or ONE_WORD.parse(reply).verdict is not None:
            stop(f"the intended difference does not hold for {reply!r}")
    print(
        f"{len(inputs.items)} prompts, {len(REPLIES)} replies, and the default settings are the "
        f"same as EvalScope {ONE_WORD.tag} ({ONE_WORD.commit}). {len(NO_VERDICT)} empty replies "
        f"have no verdict here. Prompts SHA-256 {inputs.prompts_sha256}"
    )


if __name__ == "__main__":
    main()
