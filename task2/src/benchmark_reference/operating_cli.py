"""Replay both Part A benchmarks and apply one explicitly retrospective policy."""

import argparse
import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import asdict
from functools import partial
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.experiments import DEFAULT_RATIOS, DEFAULT_SEEDS, evaluate_experiment
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.judge_noise import noise_report
from benchmark_reference.long_context import CANDIDATES as AA_CANDIDATES
from benchmark_reference.long_context import extract_metadata, select_long_context
from benchmark_reference.long_context_reporting import (
    EXTRA_NAMES,
    PROFILE,
    encode_json,
    metadata_reports,
)
from benchmark_reference.models import AnalysisError
from benchmark_reference.operating_points import DEFAULT_POLICY, compare_operating_points
from benchmark_reference.pruning_reporting import DEFAULT_PROFILE, OUTPUT_NAMES, write_experiment
from benchmark_reference.reporting import validate_output_location, write_atomic
from benchmark_reference.transfer import evaluate_pair_transfer
from benchmark_reference.uncertainty import validate_threshold

NAMES = ("operating_points.json", "curves.csv", "manifest.json")
BENCHMARKS = ("live_code_bench_v5", "aa_lcr")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--lcb-thresholds",
        required=True,
        nargs="+",
        type=float,
        help="Explicit customer or illustrative GO thresholds on 0..1",
    )
    parser.add_argument("--aa-lcr-thresholds", required=True, nargs="+", type=float)
    parser.add_argument("--keep-ratios", nargs="+", type=float, default=DEFAULT_RATIOS)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    args = parser.parse_args(argv)
    try:
        thresholds = dict(
            zip(BENCHMARKS, (args.lcb_thresholds, args.aa_lcr_thresholds), strict=True)
        )
        for values in thresholds.values():
            if len(set(values)) != len(values):
                raise AnalysisError("thresholds must be unique")
            for value in values:
                validate_threshold(value)
        if len(set(args.seeds)) < 2:
            raise AnalysisError("Operating points require at least two seeds")
        validate_output_location(args.output_dir, args.data_root, output_names=NAMES)
        for benchmark in BENCHMARKS:
            validate_output_location(
                args.output_dir / benchmark,
                args.data_root,
                output_names=(*OUTPUT_NAMES, *EXTRA_NAMES),
            )
        # Freeze settings before evaluating either benchmark. Prior published evidence
        # was already observed: this is deliberately not called independent registration.
        plan = {
            "version": "part-a-operating-policy-v1",
            "confidence": 0.95,
            "policy": asdict(DEFAULT_POLICY),
            "thresholds": thresholds,
            "keep_ratios": sorted(args.keep_ratios),
            "seeds": sorted(args.seeds),
            "production_certified": False,
        }
        inventory = discover_pairs(args.data_root)
        reports = {}
        publications = []
        for benchmark in BENCHMARKS:
            pairs = tuple(p for p in inventory if p.benchmark == benchmark)
            samples = [s for pair in pairs for s in analyze_pair(pair)]
            scores: dict[str, dict[int, float]] = {}
            for sample in samples:
                scores.setdefault(sample.model, {})[sample.index] = sample.score
            options = {"keep_ratios": args.keep_ratios, "seeds": args.seeds}
            extras = {}
            if benchmark == "aa_lcr":
                metadata = extract_metadata(samples)
                selector = partial(select_long_context, metadata=metadata)
                runs = evaluate_experiment(
                    scores,
                    **options,
                    candidate_strategies=AA_CANDIDATES,
                    candidate_selector=selector,
                )
                pair_runs = evaluate_pair_transfer(
                    scores,
                    **options,
                    candidate_strategies=AA_CANDIDATES,
                    candidate_selector=selector,
                )
                extras = metadata_reports(metadata, runs)
                extras["judge_noise.json"] = encode_json(
                    noise_report(samples, runs, flip_counts=(0, 1, 2, 5, 10))
                )
            else:
                runs = evaluate_experiment(scores, **options)
                pair_runs = evaluate_pair_transfer(scores, **options)
            reports[benchmark] = compare_operating_points(
                runs, pair_runs, thresholds=thresholds[benchmark]
            )
            publications.append((benchmark, pairs, samples, runs, pair_runs, extras))
        # All inputs and both studies have validated before the first publication.
        hashes = {}
        for benchmark, pairs, samples, runs, pair_runs, extras in publications:
            destination = args.output_dir / benchmark
            write_experiment(
                destination,
                data_root=args.data_root,
                pairs=pairs,
                samples=samples,
                runs=runs,
                pair_runs=pair_runs,
                confidence=0.95,
                thresholds=thresholds[benchmark],
                profile=PROFILE if benchmark == "aa_lcr" else DEFAULT_PROFILE,
                extra_reports=extras,
            )
            for name in (*OUTPUT_NAMES, *extras):
                hashes[f"{benchmark}/{name}"] = hashlib.sha256(
                    (destination / name).read_bytes()
                ).hexdigest()
        report = encode_json({"plan": plan, "benchmarks": reports})
        stream = io.StringIO(newline="")
        rows = [
            dict(
                benchmark=benchmark,
                strategy=p["strategy"],
                role=p["role"],
                keep_ratio=p["keep_ratio"],
                realized_keep_ratio=p["realized_keep_ratio"],
                selected_count=p["selected_count"],
                **p["metrics"],
                failed_gates=";".join(p["failed_gates"]),
                eligible=p["role"] == "candidate" and not p["failed_gates"],
            )
            for benchmark, comparison in reports.items()
            for p in comparison["points"]
        ]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        outputs = {"operating_points.json": report, "curves.csv": stream.getvalue().encode("utf-8")}
        hashes.update({name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()})
        source_root = Path(__file__).parent
        outputs["manifest.json"] = encode_json(
            plan
            | {
                "output_sha256": hashes,
                "implementation_sha256": {
                    path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                    for path in sorted(source_root.glob("*.py"))
                },
                "implementation_hash_policy": "SHA256 of package source bytes with LF line endings",
                "publication": (
                    "Atomic per file, manifest last; one writer, fixed inputs; verify hashes"
                ),
            }
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items():
            write_atomic(args.output_dir / name, data)
    except (AnalysisError, OSError) as exc:
        parser.exit(2, f"part-a-operating-points: {exc}\n")
    for benchmark, comparison in reports.items():
        selected = comparison["selected"]
        print(
            f"{benchmark}: {selected['selected_count'] if selected else 'no supported'} questions; "
            f"{selected['status'] if selected else 'no point meets policy'}"
        )
    print(f"Wrote retrospective comparison to {args.output_dir}; production certification: false")


if __name__ == "__main__":
    main()
