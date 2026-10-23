"""Offline paired-image prototype commands. Never sends requests to an endpoint."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.mmmu_images import build_bundle, create_demo, load_json
from benchmark_reference.mmmu_measurements import paired_report
from benchmark_reference.mmmu_requests import build_plan, write_new_json


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Materialize deterministic image pairs")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    demo = commands.add_parser("demo", help="Generate a clearly synthetic input inventory")
    demo.add_argument("--output-dir", type=Path, required=True)
    plan = commands.add_parser("plan", help="Export answer-blind future requests; no inference")
    plan.add_argument("--bundle", type=Path, required=True)
    plan.add_argument("--profile", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--repeats", type=int, default=2)
    plan.add_argument("--seed", type=int, default=23)
    report = commands.add_parser(
        "report", help="Measure saved attempts; no population/encoder conclusion"
    )
    report.add_argument("--bundle", type=Path, required=True)
    report.add_argument("--plan", type=Path, required=True)
    report.add_argument("--responses", type=Path, required=True)
    report.add_argument("--qa", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            build_bundle(args.input, args.output_dir)
        elif args.command == "demo":
            create_demo(args.output_dir)
        elif args.command == "plan":
            write_new_json(
                args.output,
                build_plan(args.bundle, load_json(args.profile), args.repeats, args.seed),
            )
        else:
            write_new_json(
                args.output, paired_report(args.bundle, args.plan, args.responses, args.qa)
            )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"mmmu-pairs: {exc}\n")


if __name__ == "__main__":
    main()
