"""AA-LCR feature audit, coverage/cost diagnostics and precise study limitations."""

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence

from benchmark_reference.experiments import ExperimentRun
from benchmark_reference.long_context import TaskMetadata
from benchmark_reference.pruning_reporting import LIMITATIONS, ReportProfile

EXTRA_NAMES = ("features.json", "coverage.csv", "judge_noise.json")
PROFILE = ReportProfile(
    benchmark="aa_lcr",
    algorithm_version="aa-lcr-pruning-v1",
    analysis_version="aa-lcr-study-v1",
    metric="recorded LLM-judge binary acc; scale 0..1",
    features=(
        "Benchmark metadata input_tokens and canonical source-URL counts; "
        "empirical midrank thirds. "
        "Metadata-only candidate crosses length and document count; historical candidate crosses "
        "length and reference pass count. Target grades and model usage excluded before fitting."
    ),
    limitations=(
        *tuple(x for x in LIMITATIONS if not x.startswith("No semantic/topic")),
        "Questions and URLs are available, but these candidates do not "
        "establish semantic/topic coverage.",
        "Length uses shared benchmark input_tokens, not model-dependent model_output.usage.",
        "Repeated document sets create dependence for future-task inference; "
        "design intervals concern only this fixed pool.",
        "Document-count and length coverage do not guarantee coverage of all "
        "source sets at small budgets.",
        "Only one judge review per answer; judge noise and systematic judge "
        "bias are not identifiable.",
        "Judge flip budgets are conditional sensitivity assumptions, not "
        "estimated noise rates or confidence intervals.",
        "Sampling intervals collapse at census, but unmeasured judge uncertainty does not.",
        "Input-token totals are a cost proxy; latency, output tokens, cache "
        "reuse and judge cost are not measured.",
    ),
    extra_implementation=(
        "long_context.py",
        "long_context_cli.py",
        "long_context_reporting.py",
        "judge_noise.py",
    ),
)


def encode_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def metadata_reports(
    metadata: Mapping[int, TaskMetadata], runs: Sequence[ExperimentRun]
) -> dict[str, bytes]:
    all_sets = {task.source_urls for task in metadata.values()}
    all_urls = {url for task in metadata.values() for url in task.source_urls}
    tokens = sum(task.input_tokens for task in metadata.values())
    rows = []
    for run in runs:
        selected = [metadata[item.index] for item in run.selection]
        rows.append(
            {
                "strategy": run.strategy,
                "role": run.role,
                "keep_ratio": run.keep_ratio,
                "seed": run.seed,
                "held_out_model": run.held_out_model,
                "selected_count": len(selected),
                "occupied_strata": len({x.stratum for x in run.selection}),
                "source_sets_covered": len({task.source_urls for task in selected}),
                "source_set_coverage": len({task.source_urls for task in selected}) / len(all_sets),
                "source_url_coverage": len({u for task in selected for u in task.source_urls})
                / len(all_urls),
                "selected_input_tokens": sum(task.input_tokens for task in selected),
                "input_token_fraction": sum(task.input_tokens for task in selected) / tokens,
            }
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return {
        "features.json": encode_json(
            {
                "population_count": len(metadata),
                "source_set_count": len(all_sets),
                "source_url_count": len(all_urls),
                "total_input_tokens": tokens,
                "minimum_input_tokens": min(task.input_tokens for task in metadata.values()),
                "maximum_input_tokens": max(task.input_tokens for task in metadata.values()),
                "bin_policy": (
                    "empirical midrank thirds; ties never split; "
                    "refit on pool metadata, not target grades"
                ),
                "samples": [
                    {
                        "index": index,
                        "input_tokens": task.input_tokens,
                        "document_count": len(task.source_urls),
                        "source_set_sha256": hashlib.sha256(
                            "\n".join(task.source_urls).encode()
                        ).hexdigest(),
                        "source_urls": task.source_urls,
                    }
                    for index, task in sorted(metadata.items())
                ],
            }
        ),
        "coverage.csv": stream.getvalue().encode("utf-8"),
    }
