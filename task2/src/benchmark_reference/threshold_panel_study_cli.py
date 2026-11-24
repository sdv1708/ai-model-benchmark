"""Run the reference-panel study of a frozen policy one time (#77)."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import DEFAULT_MAPPING_PATH, DEFAULT_SOURCE_PATH
from benchmark_reference.reporting import validate_output_location
from benchmark_reference.threshold_cli import (
    DEFAULT_DATA_ROOT,
    DEFAULT_PANEL_DIR,
    protect_inputs,
    refuse_overwrite,
    write_files,
)
from benchmark_reference.threshold_panel_study_report import OUTPUT_NAMES, build_outputs
from benchmark_reference.threshold_panel_study_run import REPLAY_RECORD, run_panel_study
from benchmark_reference.threshold_policy import authorize_real_replay, load_policy


def _run(args: argparse.Namespace, arguments: Sequence[str]) -> dict[str, bytes]:
    loaded = load_policy(args.policy)
    authorize_real_replay(loaded)
    protect_inputs(args, OUTPUT_NAMES)
    validate_output_location(args.output_dir, args.replay_record, output_names=OUTPUT_NAMES)
    refuse_overwrite(loaded, args.output_dir, OUTPUT_NAMES)
    if args.output_dir.exists() and not args.output_dir.is_dir():
        raise AnalysisError(f"{args.output_dir} is a file, not a folder")
    run = run_panel_study(
        loaded,
        panel_dir=args.panel_dir,
        data_root=args.data_root,
        public_file=args.public_file,
        mapping_file=args.mapping,
        replay_record=args.replay_record,
        command=subprocess.list2cmdline(["threshold-panel-study", *arguments]),
        rerun_reason=args.rerun_reason,
        workers=args.workers,
    )
    outputs = build_outputs(run)
    write_files(args.output_dir, OUTPUT_NAMES, outputs)
    return outputs


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Replay a frozen policy with the public models as the reference panel. The "
        "study runs one time, after the real replay of the same policy."
    )
    parser.add_argument("--policy", type=Path, required=True, help="Frozen policy JSON file")
    parser.add_argument(
        "--panel-dir",
        type=Path,
        default=DEFAULT_PANEL_DIR,
        help="Folder of the reference panels; default: task2/data",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Folder that holds 'Part 1/predictions'; only token counts are read. Default: Evals",
    )
    parser.add_argument(
        "--public-file",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help="Public LiveCodeBench file of 'lcb-public fetch'",
    )
    parser.add_argument(
        "--mapping", type=Path, default=DEFAULT_MAPPING_PATH, help="Committed question mapping"
    )
    parser.add_argument(
        "--replay-record",
        type=Path,
        default=REPLAY_RECORD,
        help="Recorded real replay of the same policy; default: docs/data/task2-real-replay",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--rerun-reason",
        help="Reason for a second run, for example a code fault. The report states it",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Processes for the study. The tables do not change with it.",
    )
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(arguments)
    try:
        outputs = _run(args, arguments)
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"threshold-panel-study: {exc}\n")
    summary = json.loads(outputs["summary.json"])
    for name, arm in summary["arms"].items():
        for key, criterion in arm["criteria"].items():
            print(
                f"{'PASS' if criterion['passed'] else 'FAIL'} {name} questions, {key}: value "
                f"{criterion['value']}, limit {criterion['limit']}"
            )
    print(f"Wrote the reference-panel study of {summary['policy']['key']} to {args.output_dir}")
    print(f"Manifest SHA-256: {hashlib.sha256(outputs['manifest.json']).hexdigest()}")


if __name__ == "__main__":
    main()
