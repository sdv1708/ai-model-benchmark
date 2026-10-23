"""Export a fingerprint-bound historical panel for the native EvalScope adapter.

Requires the optional integration extra. Decoding uses recorded prompt tokens,
not model inference. Cross-model task identity follows the supplied shared index.
"""

import argparse
import hashlib
import importlib
import json
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.inputs import discover_pairs, read_jsonl, row_index
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location


def recorded_questions(predictions: Path) -> dict[int, str]:
    """Recover question text from the supplied GPT-OSS Harmony prompt tokens."""
    tokenizer = importlib.import_module("tiktoken").get_encoding("o200k_harmony")
    questions: dict[int, str] = {}
    for row in read_jsonl(predictions):
        index = row_index(row)
        output = row.value.get("model_output")
        if not isinstance(output, dict):
            raise AnalysisError(f"Invalid model_output at index {index}")
        tokens = output.get("prompt_token_ids")
        if not isinstance(tokens, list) or any(type(token) is not int for token in tokens):
            raise AnalysisError(f"Missing original prompt tokens at index {index}")
        prompt: str = tokenizer.decode(tokens)
        user_marker = "<|start|>user<|message|>### Question:\n"
        format_marker = "\n\n### Format:"
        if prompt.count(user_marker) != 1 or format_marker not in prompt:
            raise AnalysisError(f"Unsupported recorded coding prompt at index {index}")
        question = prompt.split(user_marker, 1)[1].rsplit(format_marker, 1)[0]
        if not question.strip() or index in questions:
            raise AnalysisError(f"Empty or duplicate coding question at index {index}")
        questions[index] = question.replace("\r\n", "\n").replace("\r", "\n").strip()
    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_output_location(
            args.output.parent, args.data_root, output_names=[args.output.name]
        )
        pairs = [p for p in discover_pairs(args.data_root) if p.benchmark == "live_code_bench_v5"]
        scores = {p.model: {s.index: int(s.score) for s in analyze_pair(p)} for p in pairs}
        identity_source = next(p.predictions for p in pairs if p.model == "gpt-oss-120b")
        questions = recorded_questions(identity_source)
        if len(questions) != 315 or any(
            set(values) != set(questions) for values in scores.values()
        ):
            raise AnalysisError("The complete aligned 315-question coding panel is required")
        tasks = [
            {
                "index": index,
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "scores": {model: scores[model][index] for model in sorted(scores)},
            }
            for index, question in sorted(questions.items())
        ]
        if len({task["question_sha256"] for task in tasks}) != len(tasks):
            raise AnalysisError("Question text fingerprints are ambiguous")
        files = sorted({p.predictions for p in pairs} | {p.reviews for p in pairs})
        panel = {
            "schema_version": 1,
            "tasks": tasks,
            "provenance": {
                "benchmark": "live_code_bench_v5",
                "identity_method": (
                    "question text recovered from recorded GPT-OSS Harmony prompt tokens"
                ),
                "tokenizer": "tiktoken 0.14.0 / o200k_harmony",
                "cross_model_identity": "supplied shared index; original problem IDs are absent",
                "source_sha256": {
                    path.relative_to(args.data_root).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in files
                },
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(panel, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    except (AnalysisError, OSError, ImportError, ValueError) as exc:
        parser.exit(2, f"export-lcb-panel: {exc}\n")
    print(f"Exported {len(tasks)} fingerprint-bound questions to {args.output}; no inference calls")


if __name__ == "__main__":
    main()
