"""Compare the judge prompt copy of this project with the EvalScope AA-LCR adapter.

Run with the Python environment of an EvalScope pruning checkout, with this project's
``src`` on PYTHONPATH. The tool makes no model call and needs no key.

It renders the prompt of every saved answer with both code paths, and parses a set of
replies with both parsers. It stops at the first difference.
"""

import argparse
import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmark_reference.judge_items import load_judge_inputs
from benchmark_reference.judge_prompt import parse_reply, render_prompt

REPLIES = (
    "",
    "CORRECT",
    '{"verdict":"CORRECT"}',
    '{"reasoning":"It agrees.","verdict":"INCORRECT"}',
    '```json\n{"reasoning":"It agrees.","verdict":"CORRECT"}\n```',
    '<think>a {b} c</think>{"verdict":"CORRECT"}',
    '{"verdict":"correct"}',
    '{"verdict":true}',
    '{"verdict":["CORRECT"]}',
    '{"reasoning":1,"verdict":"CORRECT"}',
    '{"reasoning":null,"verdict":"CORRECT"}',
    '{"reasoning":"a } brace","verdict":"CORRECT","extra":{"a":1}}',
    '{"verdict":"CORRECT"}{"verdict":"INCORRECT"}',
    '{"verdict":"CORRECT"',
    "{'verdict':'CORRECT'}",
    '{"verdict":"CORRECT","verdict":"INCORRECT"}',
    '{"reasoning":"line\nbreak","verdict":"CORRECT"}',
    'An odd " quote {"verdict":"CORRECT"}',
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    args = parser.parse_args()
    adapter: Any = importlib.import_module("evalscope.benchmarks.aa_lcr.aa_lcr_adapter")
    inputs = load_judge_inputs(
        panel_path=args.panel, data_root=args.data_root, source_csv=args.source_csv
    )
    for item in inputs.items:
        # The real judge_definition of the adapter builds the request; it reads no self state.
        context = SimpleNamespace(
            task_state=SimpleNamespace(metadata={"question": item.question}),
            reference=item.reference,
            filtered_prediction=item.answer,
        )
        definition = adapter.AALCRAdapter.judge_definition(None, context)
        (case,) = definition.build_cases(context)
        messages = definition.build_request(case, None, [], context).messages
        native = [(m.role, m.content) for m in messages]
        ours = render_prompt(question=item.question, reference=item.reference, answer=item.answer)
        if native != [("user", ours)]:
            parser.exit(2, f"audit-judge-prompt: the prompt differs for {item.key}\n")
    for reply in REPLIES:
        result = adapter.GRADE_CONTRACT.parse(reply)
        native_verdict = result.value.verdict if result.ok else None
        if native_verdict != parse_reply(reply).verdict:
            parser.exit(2, f"audit-judge-prompt: the parser differs for {reply!r}\n")
    print(
        f"{len(inputs.items)} prompts and {len(REPLIES)} replies are the same. "
        f"Prompts SHA-256 {inputs.prompts_sha256}"
    )


if __name__ == "__main__":
    main()
