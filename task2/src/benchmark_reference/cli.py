"""Command-line entry point: validate shipped evaluations and write reference reports."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.analysis import aggregate_samples, analyze_pair
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location, write_outputs


def run_analysis(data_root: Path, output_dir: Path) -> None:
    """Validate every input pair, then write the three report files.

    Discovers all 28 pairs and validates/scores every sample (Part A and MMMU) before
    anything is written, so invalid inputs publish no new reports. Only Part A pairs
    (``include_in_reference``) feed full_scores.json. Refuses an output directory inside
    the input data or one that would overwrite an input file, and prints a summary.
    """
    validate_output_location(output_dir, data_root)
    pairs = discover_pairs(data_root)

    # Validate and score EVERYTHING (Part A and MMMU) before anything is written.
    samples = [sample for pair in pairs for sample in analyze_pair(pair)]
    all_summaries = aggregate_samples(samples)

    reference_keys = {
        (pair.benchmark, pair.model, pair.subset) for pair in pairs if pair.include_in_reference
    }
    summaries = tuple(
        summary
        for summary in all_summaries
        if (summary.benchmark, summary.model, summary.subset) in reference_keys
    )

    write_outputs(
        output_dir, data_root=data_root, pairs=pairs, samples=samples, summaries=summaries
    )

    print(
        f"Validated {len(pairs)} pairs ({len(pairs) * 2} files) and {len(samples)} samples; "
        f"wrote {len(summaries)} Part A summaries to {output_dir}"
    )
    for summary in summaries:
        print(
            f"  {summary.benchmark:<20} {summary.model:<14} {summary.metric:<5} "
            f"mean={summary.mean_score:.4f} ({summary.score_sum:g}/{summary.sample_count})"
        )


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and run the analysis; exit with code 2 and a message on failure."""
    parser = argparse.ArgumentParser(
        description="Validate shipped evaluations and reproduce Part A full reference scores."
    )
    parser.add_argument("--data-root", type=Path, required=True, help="Path to Evals/")
    parser.add_argument("--output-dir", type=Path, required=True, help="Generated report directory")
    args = parser.parse_args(argv)
    try:
        run_analysis(args.data_root, args.output_dir)
    except AnalysisError as exc:
        parser.exit(2, f"benchmark-reference: {exc}\n")
