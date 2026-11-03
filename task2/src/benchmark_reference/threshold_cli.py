"""Run the two-stage decision, its token cost, and the coverage study on simulated models."""

import argparse
import hashlib
import os
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.threshold_cost import (
    CostEvidence,
    CostModel,
    band_costs,
    cost_by_true_score,
    run_cost_study,
)
from benchmark_reference.threshold_coverage import run_coverage_study, summarize_coverage
from benchmark_reference.threshold_policy import authorize_real_replay, load_policy
from benchmark_reference.threshold_report import OUTPUT_NAMES, build_outputs
from benchmark_reference.threshold_study import (
    load_reference_panel,
    run_simulated_study,
    summarize,
)
from benchmark_reference.threshold_tokens import estimate_question_costs, load_token_counts

DEFAULT_PANEL = Path(__file__).resolve().parents[2] / "data" / "lcb-reference-panel.json"
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "Evals"


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
        validate_output_location(args.output_dir, args.panel.parent, output_names=OUTPUT_NAMES)
        validate_output_location(args.output_dir, args.data_root, output_names=OUTPUT_NAMES)
        if args.policy.resolve() in {(args.output_dir / n).resolve() for n in OUTPUT_NAMES}:
            raise AnalysisError(f"An output path would overwrite the policy {args.policy}")
        panel = load_reference_panel(args.panel, benchmark=loaded.policy.benchmark)
        questions = tuple(sorted(next(iter(panel.references.values()))))
        tokens = load_token_counts(
            args.data_root,
            benchmark=loaded.policy.benchmark,
            models=tuple(sorted(panel.references)),
            questions=questions,
            source_sha256=panel.source_sha256,
        )
        question_costs = estimate_question_costs(tokens)
        model = CostModel(question_costs)
        rows = run_simulated_study(panel.references, loaded.policy)
        population = len(questions)
        summary = summarize(rows, population=population)
        cost_cells = run_cost_study(
            panel.references, loaded.policy, model, base_rows=rows, workers=args.workers
        )
        cost = CostEvidence(
            tokens=tokens,
            questions=question_costs,
            model=model,
            point=tuple(cost_by_true_score(rows, model)),
            cells=cost_cells,
            bands=band_costs(cost_cells, loaded.policy),
        )
        cells = run_coverage_study(
            panel.references, loaded.policy, costs=model, workers=args.workers
        )
        coverage = summarize_coverage(
            cells,
            subsets=loaded.policy.coverage_subsets,
            alpha=loaded.policy.alpha,
            full_tokens=model.full,
        )
        outputs = build_outputs(
            loaded,
            rows,
            summary,
            coverage,
            cost,
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
    for missing in tokens.missing:
        print(f"Missing token count: {missing.model} question {missing.index} ({missing.field})")
    full = model.full
    print(
        f"Full run: {float(full.mean):,.0f} tokens, mean estimate "
        f"(low {float(full.low):,.0f}, high {float(full.high):,.0f})"
    )
    for band in cost.bands:
        low, mean, high = (float(v) for v in band.fraction.values)
        print(
            f"cost, true score {band.label}, {band.stage_size} questions: "
            f"{mean:.3f} of a full run (low {low:.3f}, high {high:.3f})"
        )
    for method in coverage["methods"]:
        if method["passes_every_cell"]:
            verdict = "passes every cell"
        else:
            verdict = f"fails {method['cells_failed']} of {method['cells']} cells"
        print(
            f"{method['method']}: {verdict}, lowest coverage {method['min_coverage']:.4f}, "
            f"mean width {method['mean_width']:.3f}"
        )
    manifest_sha256 = hashlib.sha256(outputs["manifest.json"]).hexdigest()
    print(f"Wrote {len(rows)} simulated decisions to {args.output_dir}")
    print(f"Manifest SHA-256: {manifest_sha256}")


if __name__ == "__main__":
    main()
