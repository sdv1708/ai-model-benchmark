"""Auditable experiment artifacts, held-out summaries and seed stability."""

import csv
import hashlib
import io
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

from benchmark_reference.experiments import ExperimentRun
from benchmark_reference.models import FilePair, SampleResult
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.study_metrics import (
    summarize_decisions,
    summarize_pair_transfer,
    threshold_decisions,
)
from benchmark_reference.transfer import PairTransferRun

OUTPUT_NAMES = (
    "scores.json",
    "selections.jsonl",
    "pair_selections.jsonl",
    "fidelity.json",
    "summary.csv",
    "pair_summary.csv",
    "decisions.csv",
    "manifest.json",
)
LIMITATIONS = [
    "Only three historical models; each fold fits on two. This is not proof for a fourth model.",
    "Ordering uses the same subset within a fold, but includes two in-sample reference models.",
    "Held-out scores alone measure transfer; no ranking combines scores from different subsets.",
    "Seed dispersion measures selection sensitivity on fixed grades, not generation uncertainty.",
    "No customer threshold or production operating point is fitted; thresholds are user inputs.",
    "Exact intervals assume uniform within-stratum sampling; fixed hash priorities approximate it.",
    "Intervals concern fixed grades, not future tasks, generation noise, or unseen model families.",
    "Coverage is per fixed run, not simultaneous over methods, ratios, seeds, or searches.",
    "Pair transfer excludes both compared models; only one reference remains in this panel.",
    "Easiest/hardest comparisons have no intervals except when the entire pool is observed.",
    "Index correspondence across models is assumed from the supplied benchmark contract.",
    "No semantic/topic coverage can be claimed: original prompts and coding metadata are absent.",
    "This offline experiment does not satisfy the later evalscope integration requirement.",
]


@dataclass(frozen=True, slots=True)
class ReportProfile:
    """Benchmark-specific claims and provenance for the shared study schema."""

    benchmark: str = "live_code_bench_v5"
    algorithm_version: str = "lcb-pruning-v1"
    analysis_version: str = "lcb-study-v2"
    metric: str = "recorded binary pass; scale 0..1"
    features: str = "reference binary pass vectors only; held-out model removed before selection"
    limitations: tuple[str, ...] = tuple(LIMITATIONS)
    extra_implementation: tuple[str, ...] = ()


DEFAULT_PROFILE = ReportProfile()


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _csv(rows: Sequence[dict[str, object]], *, empty_columns: Sequence[str] = ()) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=list(rows[0]) if rows else list(empty_columns), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _run_key(run: ExperimentRun) -> dict[str, object]:
    return {
        "strategy": run.strategy,
        "role": run.role,
        "keep_ratio": run.keep_ratio,
        "seed": run.seed,
        "held_out_model": run.held_out_model,
        "reference_models": run.reference_models,
    }


def summarize_runs(runs: Sequence[ExperimentRun]) -> list[dict[str, object]]:
    """Report each fold and a descriptive pooled summary; no best-seed cherry-pick."""
    grouped: dict[tuple[str, float, str], list[ExperimentRun]] = defaultdict(list)
    for run in runs:
        grouped[(run.strategy, run.keep_ratio, run.held_out_model)].append(run)
        grouped[(run.strategy, run.keep_ratio, "__all__")].append(run)
    rows: list[dict[str, object]] = []
    for (strategy, ratio, model), group in sorted(grouped.items()):
        signed = [
            run.estimates[run.held_out_model] - run.full_scores[run.held_out_model] for run in group
        ]
        absolute = list(map(abs, signed))
        intervals = [
            (run.score_intervals[run.held_out_model], run.full_scores[run.held_out_model])
            for run in group
            if run.score_intervals[run.held_out_model] is not None
        ]
        # Compare seeds only within the same held-out fold, never across fitted feature sets.
        similarities = []
        for left, right in combinations(group, 2):
            if left.held_out_model == right.held_out_model:
                a, b = {x.index for x in left.selection}, {x.index for x in right.selection}
                similarities.append(len(a & b) / len(a | b))
        rows.append(
            {
                "strategy": strategy,
                "role": group[0].role,
                "keep_ratio": ratio,
                "held_out_model": model,
                "selected_count": len(group[0].selection),
                "realized_keep_ratio": len(group[0].selection) / group[0].population_count,
                "run_count": len(group),
                "held_out_mae": statistics.mean(absolute),
                "held_out_rmse": math.sqrt(statistics.mean(x * x for x in signed)),
                "held_out_bias": statistics.mean(signed),
                "held_out_max_absolute_error": max(absolute),
                "held_out_error_std": statistics.stdev(signed) if len(signed) > 1 else None,
                "interval_count": len(intervals),
                "held_out_interval_coverage": statistics.mean(
                    interval.lower - 1e-12 <= score <= interval.upper + 1e-12
                    for interval, score in intervals
                    if interval is not None
                )
                if intervals
                else None,
                "mean_interval_width": statistics.mean(
                    interval.upper - interval.lower
                    for interval, _ in intervals
                    if interval is not None
                )
                if intervals
                else None,
                "raw_held_out_mae": statistics.mean(
                    abs(
                        run.raw_subset_means[run.held_out_model]
                        - run.full_scores[run.held_out_model]
                    )
                    for run in group
                ),
                "mean_pair_agreement": statistics.mean(
                    run.ordering.pair_agreement for run in group
                ),
                "exact_order_fraction": statistics.mean(
                    run.ordering.pair_agreement == 1 for run in group
                ),
                "mean_seed_jaccard": statistics.mean(similarities) if similarities else None,
            }
        )
    return rows


def write_experiment(
    output_dir: Path,
    *,
    data_root: Path,
    pairs: Sequence[FilePair],
    samples: Sequence[SampleResult],
    runs: Sequence[ExperimentRun],
    pair_runs: Sequence[PairTransferRun],
    confidence: float,
    thresholds: Sequence[float],
    profile: ReportProfile = DEFAULT_PROFILE,
    extra_reports: Mapping[str, bytes] | None = None,
) -> None:
    """Serialize completely before publishing; hash outputs and publish manifest last.

    As in issue #14, atomic replacement is per file, not a multi-file transaction.
    One writer and unchanged source files are required; verify output hashes.
    """
    extras = dict(extra_reports or {})
    if any(name in OUTPUT_NAMES or Path(name).name != name for name in extras):
        raise ValueError("Extra reports require unique flat filenames")
    validate_output_location(output_dir, data_root, output_names=(*OUTPUT_NAMES, *extras))
    root = data_root.resolve()
    sources = sorted({p for pair in pairs for p in (pair.predictions, pair.reviews)})
    inputs = [
        {"path": p.resolve().relative_to(root).as_posix(), "sha256": _hash(p)} for p in sources
    ]
    scores = [
        {
            "benchmark": sample.benchmark,
            "subset": sample.subset,
            "model": sample.model,
            "index": sample.index,
            "score": sample.score,
            "prediction_source": {
                "path": sample.prediction_source.path.resolve().relative_to(root).as_posix(),
                "line": sample.prediction_source.line,
            },
            "review_source": {
                "path": sample.review_source.path.resolve().relative_to(root).as_posix(),
                "line": sample.review_source.line,
            },
        }
        for sample in sorted(samples, key=lambda sample: (sample.model, sample.index))
    ]
    selections = b"".join(
        (
            json.dumps(
                _run_key(run) | {"samples": [asdict(item) for item in run.selection]},
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        for run in runs
    )
    fidelity = [
        _run_key(run)
        | {
            "selected_count": len(run.selection),
            "population_count": run.population_count,
            "full_scores": run.full_scores,
            "estimated_scores": run.estimates,
            "raw_subset_means": run.raw_subset_means,
            "score_intervals": {
                model: asdict(interval) if interval is not None else None
                for model, interval in run.score_intervals.items()
            },
            "threshold_decisions": [asdict(d) for d in threshold_decisions(run, thresholds)],
            "held_out_absolute_error": abs(
                run.estimates[run.held_out_model] - run.full_scores[run.held_out_model]
            ),
            "ordering": asdict(run.ordering),
        }
        for run in runs
    ]
    summary = summarize_runs(runs)
    pair_records = []
    pair_selections = []
    for run in pair_runs:
        record = asdict(run)
        selected = record.pop("selection")
        pair_records.append(record)
        pair_selections.append(
            json.dumps(
                {
                    "strategy": run.strategy,
                    "role": run.role,
                    "keep_ratio": run.keep_ratio,
                    "seed": run.seed,
                    "models": run.models,
                    "reference_models": run.reference_models,
                    "samples": selected,
                },
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    pair_summary = summarize_pair_transfer(pair_runs)
    decisions = summarize_decisions(runs, thresholds)
    outputs = {
        "scores.json": _json({"samples": scores}),
        "selections.jsonl": selections,
        "pair_selections.jsonl": "".join(pair_selections).encode("utf-8"),
        "fidelity.json": _json(
            {
                "runs": fidelity,
                "summary": summary,
                "pair_transfer_runs": pair_records,
                "pair_transfer_summary": pair_summary,
                "decision_summary": decisions,
                "limitations": profile.limitations,
            }
        ),
        "summary.csv": _csv(summary),
        "pair_summary.csv": _csv(pair_summary),
        "decisions.csv": _csv(
            decisions,
            empty_columns=(
                "strategy",
                "keep_ratio",
                "held_out_model",
                "threshold",
                "run_count",
                "decisive_fraction",
                "false_go_fraction",
                "false_no_go_fraction",
                "point_decision_agreement",
            ),
        ),
    }
    outputs.update(extras)
    code_root = Path(__file__).parent
    manifest = {
        "schema_version": 2,
        "algorithm_version": profile.algorithm_version,
        "analysis_version": profile.analysis_version,
        "benchmark": profile.benchmark,
        "metric": profile.metric,
        "keep_ratios": sorted({run.keep_ratio for run in runs}),
        "ratio_definition": "fraction retained; count = ceil(N * keep_ratio)",
        "seeds": sorted({run.seed for run in runs}),
        "run_count": len(runs),
        "pair_transfer_run_count": len(pair_runs),
        "confidence": confidence,
        "thresholds": sorted(thresholds),
        "interval_policy": (
            "equal-tail hypergeometric inversion with exact integer tail comparisons; "
            "Bonferroni across strata and both directional discordances for paired differences; "
            "no intervals for deterministic top-k except at census"
        ),
        "inputs": inputs,
        "implementation_hash_policy": "SHA256 of source bytes after CRLF-to-LF normalization",
        "implementation_sha256": {
            name: hashlib.sha256(
                (code_root / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for name in (
                "models.py",
                "inputs.py",
                "analysis.py",
                "reporting.py",
                "pruning.py",
                "experiments.py",
                "pruning_cli.py",
                "pruning_reporting.py",
                "uncertainty.py",
                "transfer.py",
                "study_metrics.py",
                "strategies.py",
                *profile.extra_implementation,
            )
        },
        "features": profile.features,
        "allocation": "one per occupied stratum, then largest proportional deficit; lexical ties",
        "within_stratum": "ascending SHA256(lcb-pruning-v1:seed:index), without replacement",
        "estimator": "sum_h (N_h/N) * mean(selected grades in h); baselines use raw mean",
        "baseline_policy": "comparison only; never candidates or production recommendations",
        "ordering_policy": "common subset per fold; reference-assisted; ties within 1e-12",
        "limitations": profile.limitations,
        "output_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
    }
    outputs["manifest.json"] = _json(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        write_atomic(output_dir / name, data)
