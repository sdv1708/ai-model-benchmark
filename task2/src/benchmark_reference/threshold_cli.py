"""Run issue #56's two-stage threshold decision on simulated LiveCodeBench models."""

import argparse
import hashlib
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.threshold_policy import authorize_real_replay, load_policy
from benchmark_reference.threshold_report import OUTPUT_NAMES, build_outputs
from benchmark_reference.threshold_study import (
    load_reference_panel,
    run_simulated_study,
    summarize,
)

DEFAULT_PANEL = Path(__file__).resolve().parents[2] / "data" / "lcb-reference-panel.json"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Decide GO, NO GO, or ESCALATE for simulated models under one policy file."
    )
    parser.add_argument("--policy", type=Path, required=True, help="Versioned policy JSON file")
    parser.add_argument(
        "--panel",
        type=Path,
        default=DEFAULT_PANEL,
        help="Reference panel JSON; default: task2/data/lcb-reference-panel.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--real-grades",
        action="store_true",
        help="Replay on real model grades; requires a frozen policy with a committed hash",
    )
    args = parser.parse_args(argv)
    try:
        loaded = load_policy(args.policy)
        if args.real_grades:
            authorize_real_replay(loaded)
            raise AnalysisError("The real-grade replay is not part of this command yet (#63)")
        validate_output_location(args.output_dir, args.panel.parent, output_names=OUTPUT_NAMES)
        if args.policy.resolve() in {(args.output_dir / n).resolve() for n in OUTPUT_NAMES}:
            raise AnalysisError(f"An output path would overwrite the policy {args.policy}")
        panel = load_reference_panel(args.panel, benchmark=loaded.policy.benchmark)
        rows = run_simulated_study(panel.references, loaded.policy)
        population = len(next(iter(panel.references.values())))
        summary = summarize(rows, population=population)
        outputs = build_outputs(
            loaded,
            rows,
            summary,
            population=population,
            panel_name=args.panel.name,
            panel_sha256=panel.sha256,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name in OUTPUT_NAMES:
            write_atomic(args.output_dir / name, outputs[name])
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"threshold-decision: {exc}\n")
    for row in summary:
        print(
            f"true score {row['true_score']}: decisive {row['decisive_fraction']:.3f}, "
            f"wrong {row['wrong_decisions']}/{row['draws']}"
        )
    manifest_sha256 = hashlib.sha256(outputs["manifest.json"]).hexdigest()
    print(f"Wrote {len(rows)} simulated decisions to {args.output_dir}")
    print(f"Manifest SHA-256: {manifest_sha256}")


if __name__ == "__main__":
    main()
