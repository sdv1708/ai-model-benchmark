"""Run the two-stage decision, its token cost, and the coverage study on simulated models.

The command runs every benchmark section of the policy file and writes one report.
"""

import argparse
import hashlib
import os
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.threshold_benchmarks import BENCHMARKS, load_reference_panel
from benchmark_reference.threshold_cost import (
    CostEvidence,
    CostModel,
    band_costs,
    cost_by_true_score,
    run_cost_study,
)
from benchmark_reference.threshold_coverage import run_coverage_study, summarize_coverage
from benchmark_reference.threshold_policy import (
    ThresholdPolicy,
    authorize_real_replay,
    load_policy,
)
from benchmark_reference.threshold_report import (
    JUDGE_NOISE,
    BenchmarkRun,
    build_outputs,
    output_names,
)
from benchmark_reference.threshold_study import run_simulated_study, summarize
from benchmark_reference.threshold_tokens import estimate_question_costs, load_token_counts

DEFAULT_PANEL_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "Evals"


def run_benchmark(
    policy: ThresholdPolicy, *, panel_dir: Path, data_root: Path, workers: int
) -> BenchmarkRun:
    """Every study of one policy section on its own reference panel."""
    panel_file = BENCHMARKS[policy.benchmark].panel_file
    panel = load_reference_panel(panel_dir / panel_file, benchmark=policy.benchmark)
    tokens = load_token_counts(
        data_root,
        benchmark=policy.benchmark,
        models=tuple(sorted(panel.references)),
        questions=panel.questions,
        source_sha256=panel.source_sha256,
    )
    question_costs = estimate_question_costs(tokens)
    model = CostModel(question_costs)
    rows = run_simulated_study(panel, policy)
    population = len(panel.questions)
    cost_cells = run_cost_study(panel, policy, model, base_rows=rows, workers=workers)
    cost = CostEvidence(
        tokens=tokens,
        questions=question_costs,
        model=model,
        point=tuple(cost_by_true_score(rows, model)),
        cells=cost_cells,
        bands=band_costs(cost_cells, policy),
    )
    cells = run_coverage_study(panel, policy, costs=model, workers=workers)
    coverage = summarize_coverage(
        cells, subsets=policy.coverage_subsets, alpha=policy.alpha, full_tokens=model.full
    )
    return BenchmarkRun(
        policy=policy,
        panel_file=panel_file,
        panel_sha256=panel.sha256,
        population=population,
        rows=rows,
        summary=summarize(rows, population=population),
        coverage=coverage,
        cost=cost,
    )


def _print_run(run: BenchmarkRun) -> None:
    title = run.benchmark.title
    if run.benchmark.judge_graded:
        print(f"{title}: {JUDGE_NOISE}")
    for row in run.summary:
        print(
            f"{title}, true score {row['true_score']}: decisive "
            f"{row['decisive_fraction']:.3f}, wrong {row['wrong_decisions']}/{row['draws']}"
        )
    for missing in run.cost.tokens.missing:
        print(
            f"{title}: missing token count: {missing.model} question {missing.index} "
            f"({missing.field})"
        )
    full = run.cost.model.full
    print(
        f"{title}, full run: {float(full.mean):,.0f} tokens, mean estimate "
        f"(low {float(full.low):,.0f}, high {float(full.high):,.0f})"
    )
    for band in run.cost.bands:
        low, mean, high = (float(v) for v in band.fraction.values)
        print(
            f"{title}, cost, true score {band.label}, {band.stage_size} questions: "
            f"{mean:.3f} of a full run (low {low:.3f}, high {high:.3f})"
        )
    for method in run.coverage["methods"]:
        if method["passes_every_cell"]:
            verdict = "passes every cell"
        else:
            verdict = f"fails {method['cells_failed']} of {method['cells']} cells"
        print(
            f"{title}, {method['method']}: {verdict}, lowest coverage "
            f"{method['min_coverage']:.4f}, mean width {method['mean_width']:.3f}"
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Decide GO, NO GO, or ESCALATE for simulated models under one policy file."
    )
    parser.add_argument("--policy", type=Path, required=True, help="Versioned policy JSON file")
    parser.add_argument(
        "--panel-dir",
        type=Path,
        default=DEFAULT_PANEL_DIR,
        help="Folder of the reference panels "
        f"({', '.join(b.panel_file for b in BENCHMARKS.values())}); default: task2/data",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Folder that holds 'Part 1/predictions'; only token counts are read. Default: Evals",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--real-grades",
        action="store_true",
        help="Replay on real model grades; requires a frozen policy with a committed hash",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Processes for the cost and coverage studies. The outputs do not change with it.",
    )
    args = parser.parse_args(argv)
    try:
        loaded = load_policy(args.policy)
        if args.real_grades:
            authorize_real_replay(loaded)
            raise AnalysisError("The real-grade replay is not part of this command yet (#63)")
        names = output_names(loaded.benchmarks)
        validate_output_location(args.output_dir, args.panel_dir, output_names=names)
        validate_output_location(args.output_dir, args.data_root, output_names=names)
        if args.policy.resolve() in {(args.output_dir / n).resolve() for n in names}:
            raise AnalysisError(f"An output path would overwrite the policy {args.policy}")
        runs = [
            run_benchmark(
                policy, panel_dir=args.panel_dir, data_root=args.data_root, workers=args.workers
            )
            for policy in loaded.benchmarks.values()
        ]
        outputs = build_outputs(loaded, runs)
        for name in names:
            path = args.output_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, outputs[name])
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"threshold-decision: {exc}\n")
    for run in runs:
        _print_run(run)
    manifest_sha256 = hashlib.sha256(outputs["manifest.json"]).hexdigest()
    simulated = sum(len(run.rows) for run in runs)
    print(f"Wrote {simulated} simulated decisions to {args.output_dir}")
    print(f"Manifest SHA-256: {manifest_sha256}")


if __name__ == "__main__":
    main()
