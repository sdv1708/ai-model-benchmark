"""Measure how much AA-LCR scores change when the judge grades the saved answers again.

- ``estimate`` writes the calls, the tokens, and the cost. It makes no request.
- ``run`` sends each saved answer to the judge 5 times, under an approved estimate.
- ``report`` computes the judge noise of a complete run. It makes no request.
- ``compare`` compares a one-word run (#88) with the JSON run of #76 and the saved grades.
  It makes no request.

``estimate --prompt`` selects the judge prompt, and the estimate file records it.
"""

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from benchmark_reference import judge_compare, judge_estimate
from benchmark_reference.judge_estimate import Estimate, Prices, build_estimate, load_estimate
from benchmark_reference.judge_items import SOURCE_URL, JudgeInputs, load_judge_inputs
from benchmark_reference.judge_prompt import JSON_CONTRACT, ONE_WORD, VARIANTS
from benchmark_reference.judge_report import (
    OUTPUT_NAMES,
    build_outputs,
    load_run,
    load_settings,
)
from benchmark_reference.judge_run import run_judge
from benchmark_reference.judge_statement import RECORD_FILE
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.threshold_benchmarks import AA_LCR, load_reference_panel
from benchmark_reference.threshold_policy import load_policy

TASK2 = Path(__file__).resolve().parents[2]
# The recorded JSON run of #76.
BASELINE_RUN = TASK2.parent / "docs" / "data" / "task2-aa-lcr-judge-rerun"
# The console lines and the exit code of one command.
type Result = tuple[list[str], int]


def _inputs(args: argparse.Namespace) -> JudgeInputs:
    return load_judge_inputs(
        panel_path=args.panel, data_root=args.data_root, source_csv=args.source_csv
    )


def _number(text: str) -> Fraction:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None


def _check_baseline(estimate: Estimate, baseline_run: Path) -> None:
    """A one-word run must use the judge and the endpoint of the JSON run. Check before it."""
    if estimate.variant is ONE_WORD:
        baseline, _approval, _bytes = load_settings(baseline_run)
        judge_compare.check_same_judge(estimate, baseline)


def _estimate(args: argparse.Namespace) -> Result:
    data = build_estimate(
        _inputs(args),
        base_url=args.base_url,
        judge_model=args.judge_model,
        prices=Prices(args.input_price, args.output_price, args.price_source, args.price_date),
        limit_usd=args.limit_usd,
        allow_different_judge=args.allow_different_judge,
        variant=VARIANTS[args.prompt],
    )
    _check_baseline(load_estimate(data), args.baseline_run)
    if args.output.exists():
        raise AnalysisError(f"{args.output} exists. An approved estimate must not change")
    validate_output_location(args.output.parent, args.data_root, output_names=[args.output.name])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(args.output, data)
    return [*judge_estimate.console_lines(load_estimate(data)), f"Wrote {args.output}"], 0


def _run(args: argparse.Namespace) -> Result:
    """Exit code 1 means that the run stopped before the end for an unplanned reason."""
    estimate = load_estimate(args.estimate.read_bytes())
    _check_baseline(estimate, args.baseline_run)
    inputs = _inputs(args)
    validate_output_location(args.run_dir, args.data_root, output_names=[])
    # A loopback judge takes no credential, so the command does not read one.
    key = None if estimate.loopback else os.environ.get(args.api_key_env)
    if not estimate.loopback and not key:
        raise AnalysisError(f"Put the judge key in the environment variable {args.api_key_env}")
    result = run_judge(
        estimate,
        inputs,
        run_dir=args.run_dir,
        key=key,
        approval_url=args.approval_url,
        workers=args.workers,
        max_new_requests=args.max_requests,
    )
    lines = [
        f"{result.judgments:,} of {result.needed:,} judgments after {result.new_requests:,} new "
        f"requests. Cost so far: at most ${float(result.cost_bound):.4f}"
    ]
    if result.stopped:
        lines.append(f"Stopped: {result.stopped}")
    for number, model, index in result.failed_slots:
        lines.append(f"No verdict for pass {number}, {model} question {index}")
    if result.complete:
        command = "compare" if estimate.variant is ONE_WORD else "report"
        lines.append(f"The run is complete. Next: aa-lcr-judge {command}")
    return lines, 0 if result.complete or result.limited else 1


def _report(args: argparse.Namespace) -> Result:
    inputs = _inputs(args)
    record = load_run(args.run_dir, inputs)
    if args.record is not None and record.estimate.loopback:
        raise AnalysisError("A loopback test measures nothing, so it must not write a record")
    for root in (args.data_root, args.run_dir):
        validate_output_location(args.output_dir, root, output_names=OUTPUT_NAMES)
    panel = load_reference_panel(args.panel, benchmark=AA_LCR)
    outputs = build_outputs(record, inputs, panel, load_policy(args.policy))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_NAMES:
        write_atomic(args.output_dir / name, outputs[name])
    lines = [f"Wrote the judge-noise report to {args.output_dir}"]
    if args.record is not None:
        write_atomic(args.record, outputs[RECORD_FILE])
        lines.append(f"Wrote the record of the threshold report to {args.record}")
    return lines, 0


def _compare(args: argparse.Namespace) -> Result:
    inputs = _inputs(args)
    record, baseline = load_run(args.run_dir, inputs), load_run(args.baseline_run, inputs)
    names = judge_compare.OUTPUT_NAMES
    for root in (args.data_root, args.run_dir, args.baseline_run):
        validate_output_location(args.output_dir, root, output_names=names)
    outputs = judge_compare.build_outputs(record, baseline, inputs, load_policy(args.policy))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        write_atomic(args.output_dir / name, outputs[name])
    return [f"Wrote the comparison of the judge prompts to {args.output_dir}"], 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aa-lcr-judge", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--source-csv",
        type=Path,
        required=True,
        help=f"The pinned AA-LCR v1.0 file with the reference answers, from {SOURCE_URL}",
    )
    shared.add_argument(
        "--panel", type=Path, default=TASK2 / "data" / "aa-lcr-reference-panel.json"
    )
    shared.add_argument("--data-root", type=Path, default=TASK2.parent / "Evals")
    with_policy = argparse.ArgumentParser(add_help=False)
    with_policy.add_argument(
        "--policy", type=Path, default=TASK2 / "policies" / "threshold-v1.json"
    )
    with_baseline = argparse.ArgumentParser(add_help=False)
    with_baseline.add_argument(
        "--baseline-run",
        type=Path,
        default=BASELINE_RUN,
        help="Folder of the JSON run that a one-word run repeats (default: the run of #76)",
    )

    estimate = commands.add_parser(
        "estimate", parents=[shared, with_baseline], help="Write the cost estimate"
    )
    estimate.add_argument(
        "--prompt",
        choices=sorted(VARIANTS),
        default=JSON_CONTRACT.name,
        help="Judge prompt. one-word needs the judge and the endpoint of the baseline run",
    )
    estimate.add_argument("--base-url", required=True, help="OpenAI-compatible API address")
    estimate.add_argument("--judge-model", required=True, help="Model name at this endpoint")
    estimate.add_argument("--input-price", type=_number, required=True, help="USD for 1M tokens")
    estimate.add_argument("--output-price", type=_number, required=True, help="USD for 1M tokens")
    estimate.add_argument("--price-source", required=True, help="Where the prices come from")
    estimate.add_argument("--price-date", default=datetime.now(UTC).date().isoformat())
    estimate.add_argument("--limit-usd", type=_number, required=True, help="Hard cost limit")
    estimate.add_argument("--allow-different-judge", action="store_true")
    estimate.add_argument("--output", type=Path, required=True)
    estimate.set_defaults(run=_estimate)

    run = commands.add_parser("run", parents=[shared, with_baseline], help="Collect the judgments")
    run.add_argument("--estimate", type=Path, required=True)
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--approval-url", help="Comment of the owner that approves the estimate")
    run.add_argument("--api-key-env", default="JUDGE_API_KEY", help="Environment variable name")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--max-requests", type=int, help="Stop after this number of new requests")
    run.set_defaults(run=_run)

    report = commands.add_parser(
        "report", parents=[shared, with_policy], help="Compute the judge noise"
    )
    report.add_argument("--run-dir", type=Path, required=True)
    report.add_argument("--output-dir", type=Path, required=True)
    report.add_argument(
        "--record", type=Path, help=f"Also write the {RECORD_FILE} of the threshold report"
    )
    report.set_defaults(run=_report)

    compare = commands.add_parser(
        "compare",
        parents=[shared, with_policy, with_baseline],
        help="Compare a one-word run with the JSON run and the saved grades",
    )
    compare.add_argument("--run-dir", type=Path, required=True)
    compare.add_argument("--output-dir", type=Path, required=True)
    compare.set_defaults(run=_compare)

    args = parser.parse_args(argv)
    try:
        lines, code = args.run(args)
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"aa-lcr-judge {args.command}: {exc}\n")
    for line in lines:
        print(line)
    if code:
        parser.exit(code)


if __name__ == "__main__":
    main()
