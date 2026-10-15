"""Run issue #15's offline coding selection experiments; no live model calls."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.experiments import DEFAULT_RATIOS, DEFAULT_SEEDS, evaluate_experiment
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning_reporting import OUTPUT_NAMES, write_experiment
from benchmark_reference.reporting import validate_output_location


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate reference-only LiveCodeBench pruning.")
    parser.add_argument("--data-root", type=Path, required=True, help="Path to supplied Evals/")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--keep-ratios",
        type=float,
        nargs="+",
        default=DEFAULT_RATIOS,
        help="Fractions retained in (0,1]; default: 0.1 0.2 0.3 0.5 1",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=DEFAULT_SEEDS,
        help="Unique integer seeds; default: 0 through 19",
    )
    args = parser.parse_args(argv)
    try:
        validate_output_location(args.output_dir, args.data_root, output_names=OUTPUT_NAMES)
        pairs = tuple(
            p for p in discover_pairs(args.data_root) if p.benchmark == "live_code_bench_v5"
        )
        samples = [sample for pair in pairs for sample in analyze_pair(pair)]
        scores: dict[str, dict[int, float]] = {}
        for sample in samples:
            scores.setdefault(sample.model, {})[sample.index] = sample.score
        runs = evaluate_experiment(scores, keep_ratios=args.keep_ratios, seeds=args.seeds)
        write_experiment(
            args.output_dir, data_root=args.data_root, pairs=pairs, samples=samples, runs=runs
        )
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"lcb-pruning: {exc}\n")
    print(
        f"Evaluated {len(runs)} leave-one-model-out runs on {len(samples)} recorded coding grades; "
        f"wrote audit and fidelity reports to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
