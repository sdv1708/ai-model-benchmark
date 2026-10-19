"""Run issue #16's offline long-context selection experiments; no live model calls."""

import argparse
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.experiments import DEFAULT_RATIOS, DEFAULT_SEEDS, evaluate_experiment
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.judge_noise import noise_report
from benchmark_reference.long_context import CANDIDATES, extract_metadata, select_long_context
from benchmark_reference.long_context_reporting import (
    EXTRA_NAMES,
    PROFILE,
    encode_json,
    metadata_reports,
)
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning_reporting import OUTPUT_NAMES, write_experiment
from benchmark_reference.reporting import validate_output_location
from benchmark_reference.transfer import evaluate_pair_transfer
from benchmark_reference.uncertainty import validate_confidence, validate_threshold


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate metadata-aware AA-LCR pruning.")
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
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="Nominal finite-population interval coverage in (0,1); default .95",
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=(),
        help="Optional full-score GO thresholds in [0,1]; none assumed by default",
    )
    parser.add_argument(
        "--flip-counts",
        type=int,
        nargs="+",
        default=(0, 1, 2, 5, 10),
        help="Hypothetical total changed judgments per model; not measured noise",
    )
    args = parser.parse_args(argv)
    try:
        validate_confidence(args.confidence)
        for threshold in args.thresholds:
            validate_threshold(threshold)
        if len(set(args.thresholds)) != len(args.thresholds):
            raise AnalysisError("thresholds must be unique")
        validate_output_location(
            args.output_dir, args.data_root, output_names=(*OUTPUT_NAMES, *EXTRA_NAMES)
        )
        pairs = tuple(p for p in discover_pairs(args.data_root) if p.benchmark == "aa_lcr")
        samples = [sample for pair in pairs for sample in analyze_pair(pair)]
        scores: dict[str, dict[int, float]] = {}
        for sample in samples:
            scores.setdefault(sample.model, {})[sample.index] = sample.score
        metadata = extract_metadata(samples)
        selector = partial(select_long_context, metadata=metadata)
        runs = evaluate_experiment(
            scores,
            keep_ratios=args.keep_ratios,
            seeds=args.seeds,
            confidence=args.confidence,
            candidate_strategies=CANDIDATES,
            candidate_selector=selector,
        )
        pair_runs = evaluate_pair_transfer(
            scores,
            keep_ratios=args.keep_ratios,
            seeds=args.seeds,
            confidence=args.confidence,
            candidate_strategies=CANDIDATES,
            candidate_selector=selector,
        )
        extras = metadata_reports(metadata, runs)
        extras["judge_noise.json"] = encode_json(
            noise_report(samples, runs, flip_counts=args.flip_counts)
        )
        write_experiment(
            args.output_dir,
            data_root=args.data_root,
            pairs=pairs,
            samples=samples,
            runs=runs,
            pair_runs=pair_runs,
            confidence=args.confidence,
            thresholds=args.thresholds,
            profile=PROFILE,
            extra_reports=extras,
        )
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"aa-lcr-pruning: {exc}\n")
    print(
        f"Evaluated {len(runs)} score runs and {len(pair_runs)} pair-transfer runs "
        f"on {len(samples)} recorded long-context grades; "
        f"wrote audit and fidelity reports to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
