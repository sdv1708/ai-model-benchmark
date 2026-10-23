"""Compare native AA-LCR registry selections with the independent validated analysis.

Run with the pinned EvalScope environment and this project's src on PYTHONPATH.
Temporary records use real pinned question metadata with tiny synthetic document
contents. They are never inferred or graded; this is historical selection/score replay.
"""

import argparse
import csv
import hashlib
import importlib
import json
import math
import tempfile
from itertools import combinations
from pathlib import Path

from benchmark_reference.analysis import analyze_pair
from benchmark_reference.inputs import discover_pairs
from benchmark_reference.long_context import CANDIDATES, extract_metadata, select_long_context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = importlib.import_module("evalscope.api.registry")
    config_module = importlib.import_module("evalscope.config")
    metric_module = importlib.import_module("evalscope.api.metric")
    pairs = [p for p in discover_pairs(args.data_root) if p.benchmark == "aa_lcr"]
    scores = {p.model: {s.index: s.score for s in analyze_pair(p)} for p in pairs}
    metadata = extract_metadata([sample for pair in pairs for sample in analyze_pair(pair)])
    with args.source_csv.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    cases = 0
    census: dict[str, float] = {}
    # Keep temporary files inside the requested output workspace on Windows.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as folder:
        source = Path(folder) / "loader-only.jsonl"
        texts = Path(folder) / "texts"
        texts.mkdir()
        (texts / "fixture.txt").write_text("Loader-only synthetic context.", encoding="utf-8")
        rows = [
            dict(
                row,
                document_category="",
                document_set_id="",
                data_source_filenames="fixture.txt",
                input_tokens=int(row["input_tokens"]),
            )
            for row in source_rows
        ]
        source.write_text(
            "".join(json.dumps(row) + "\n" for row in reversed(rows)), encoding="utf-8"
        )
        models = sorted(scores)
        exclusions = [*(tuple([model]) for model in models), *combinations(models, 2)]
        for strategy in CANDIDATES:
            for ratio in (0.1, 0.2, 0.3, 0.5, 1.0):
                for seed in range(20):
                    for excluded in exclusions:
                        references = {
                            name: values for name, values in scores.items() if name not in excluded
                        }
                        expected = select_long_context(
                            references,
                            metadata=metadata,
                            strategy=strategy,
                            keep_ratio=ratio,
                            seed=seed,
                        )
                        config = config_module.TaskConfig(
                            model=excluded[0],
                            eval_type="mock_llm",
                            datasets=["aa_lcr_pruned"],
                            seed=seed,
                            dataset_args={
                                "aa_lcr_pruned": {
                                    "local_path": str(source),
                                    "subset_list": ["fixture"],
                                    "extra_params": {
                                        "reference_path": str(args.panel.resolve()),
                                        "text_dir": str(texts),
                                        "pruning_strategy": strategy,
                                        "prune_ratio": ratio,
                                        "excluded_reference_models": list(excluded[1:]),
                                    },
                                }
                            },
                        )
                        adapter = registry.get_benchmark("aa_lcr_pruned", config)
                        samples = list(adapter.load_dataset()["fixture"])
                        actual = [sample.metadata["pruning"] for sample in samples]
                        assert [item["index"] for item in actual] == [
                            item.index for item in expected
                        ]
                        for native, studied in zip(actual, expected, strict=True):
                            assert native["weight"] == studied.weight
                            assert native["stratum"] == studied.stratum
                            assert native["population_count"] == studied.population_count
                            assert native["selected_count"] == studied.selected_count
                            assert native["reference_models"] == sorted(references)
                        for target in excluded:
                            replay = [
                                metric_module.SampleScore(
                                    sample_id=sample.id,
                                    group_id=sample.group_id,
                                    sample_metadata=sample.metadata,
                                    score=metric_module.Score(
                                        value={
                                            "acc": scores[target][
                                                sample.metadata["pruning"]["index"]
                                            ]
                                        }
                                    ),
                                )
                                for sample in samples
                            ]
                            estimate = next(
                                s.score
                                for s in adapter.aggregate_scores(replay)
                                if s.aggregation == "weighted_mean"
                            )
                            expected_score = math.fsum(
                                item.weight * scores[target][item.index] for item in expected
                            )
                            assert math.isclose(estimate, expected_score, abs_tol=1e-12)
                            if ratio == 1:
                                census[target] = estimate
                        cases += 1
    result = {
        "source_csv_sha256": hashlib.sha256(args.source_csv.read_bytes()).hexdigest(),
        "panel_sha256": hashlib.sha256(args.panel.read_bytes()).hexdigest(),
        "selection_cases": cases,
        "score_folds": 600,
        "pair_folds": 600,
        "selected_ids_weights_and_replayed_scores_match": True,
        "full_retention_scores": census,
        "inference_calls": 0,
        "scope": (
            "Registry/loader and historical grade replay; "
            "synthetic-context loader fixtures are never inferred or judged."
        ),
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Verified {cases} native selections and replayed estimates against independent analysis")


if __name__ == "__main__":
    main()
