"""Deterministic reports with validated identities, source hashes, and run limits."""

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference.analysis import aggregate_samples
from benchmark_reference.models import AnalysisError, BenchmarkSummary, FilePair, SampleResult

SCORING_POLICY = {
    "score_scale": "0..1 (each sample scored 0 or 1 by the recorded grader)",
    "weighting": "equal: every sample counts once; mean = sum(scores) / count",
    "missing_data": "validation error; never dropped or counted as zero",
    "benchmarks": "reported separately; no combined capability score, no pass@k",
}
LIMITATIONS = [
    "Fixed recorded outputs: exact for the supplied artifacts only.",
    "One judge result per answer; judge nondeterminism is not estimated.",
    "No estimate of generation noise; no confidence intervals are reported.",
    "MMMU rows are validated reference samples, not the full MMMU dataset.",
]


def _dumps(value: object, *, indent: int | None = 2) -> str:
    """Serialize deterministically: sorted keys, UTF-8 friendly, no NaN/Infinity."""
    return json.dumps(value, indent=indent, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _relative(path: Path, data_root: Path) -> str:
    """Return ``path`` relative to ``data_root`` in POSIX form for portable references."""
    try:
        return path.resolve().relative_to(data_root.resolve()).as_posix()
    except ValueError as exc:
        raise AnalysisError(f"{path} is not inside data root {data_root}") from exc


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AnalysisError(f"Cannot hash {path}: {exc.strerror or exc}") from exc
    return digest.hexdigest()


OUTPUT_FILES = ("samples.jsonl", "full_scores.json", "manifest.json")


def validate_output_location(output_dir: Path, data_root: Path) -> None:
    """Protect inputs even when a report's existing path is a symlink."""
    root, out = data_root.resolve(), output_dir.resolve()
    for destination in (out, *(out / name for name in OUTPUT_FILES)):
        resolved = destination.resolve()
        if resolved == root or root in resolved.parents:
            raise AnalysisError(f"Output path {destination} is inside the input data {data_root}")


def _write_atomic(path: Path, data: bytes) -> None:
    """Replace a single file using a unique sibling temp file, with cleanup."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as f:
            temporary = Path(f.name)
            f.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_outputs(
    output_dir: Path,
    *,
    data_root: Path,
    pairs: Sequence[FilePair],
    samples: Sequence[SampleResult],
    summaries: Sequence[BenchmarkSummary],
) -> None:
    """Write samples.jsonl, full_scores.json and manifest.json to ``output_dir``.

    samples.jsonl lists every validated sample (including MMMU) with relative source
    paths and lines; full_scores.json holds the summaries the caller selected;
    manifest.json records each input's SHA-256, row counts, identity, scoring policy
    and limitations. Output is deterministic (sorted, no timestamps), and everything
    is validated and serialized before writing. Individual files are replaced
    atomically; the manifest is written last and hashes the other two reports.
    Readers can check those hashes to detect an interrupted multi-file publication.
    """
    validate_output_location(output_dir, data_root)
    counts = Counter((s.benchmark, s.model, s.subset) for s in samples)
    pair_of = {(p.benchmark, p.model, p.subset): p for p in pairs}
    if not pairs or len(pair_of) != len(pairs):
        raise AnalysisError("Report inventory must contain unique, nonempty file pairs")
    for key, pair in pair_of.items():
        if counts[key] != pair.expected_samples:
            raise AnalysisError(
                f"{'/'.join(key)}: {counts[key]} validated samples, "
                f"expected {pair.expected_samples}"
            )
    if counts.keys() != pair_of.keys():
        raise AnalysisError("Report samples contain identities outside the input inventory")
    # Recheck this public boundary: it can also receive manually constructed records.
    aggregate_samples(samples)
    reference_samples = []
    for sample in samples:
        pair = pair_of[(sample.benchmark, sample.model, sample.subset)]
        if sample.metric != pair.metric:
            raise AnalysisError("Sample metric does not match its file pair")
        for source, path in (
            (sample.prediction_source, pair.predictions),
            (sample.review_source, pair.reviews),
        ):
            if source.path.resolve() != path.resolve():
                raise AnalysisError("Sample source does not match its file pair")
            if (
                isinstance(source.line, bool)
                or not isinstance(source.line, int)
                or not 1 <= source.line <= pair.expected_samples
            ):
                raise AnalysisError("Sample source line is outside the validated file")
        if pair.include_in_reference:
            reference_samples.append(sample)
    expected_summaries = aggregate_samples(reference_samples)
    if (
        tuple(sorted(summaries, key=lambda s: (s.benchmark, s.model, s.subset)))
        != expected_summaries
    ):
        raise AnalysisError("Report summaries do not match the validated reference samples")
    # Build every output before writing; validation failure does not publish new files.
    ordered = sorted(samples, key=lambda s: (s.benchmark, s.model, s.subset, s.index))
    sample_lines = [
        _dumps(
            {
                "benchmark": s.benchmark,
                "model": s.model,
                "subset": s.subset,
                "index": s.index,
                "metric": s.metric,
                "score": s.score,
                "metadata": s.metadata,
                "prediction_source": {
                    "path": _relative(s.prediction_source.path, data_root),
                    "line": s.prediction_source.line,
                },
                "review_source": {
                    "path": _relative(s.review_source.path, data_root),
                    "line": s.review_source.line,
                },
            },
            indent=None,
        )
        for s in ordered
    ]
    samples_bytes = "".join(line + "\n" for line in sample_lines).encode("utf-8")

    full_scores = {
        "scale": "0..1",
        "summaries": [
            {
                "benchmark": s.benchmark,
                "model": s.model,
                "subset": s.subset,
                "metric": s.metric,
                "sample_count": s.sample_count,
                "score_sum": s.score_sum,
                "mean_score": s.mean_score,
            }
            for s in sorted(summaries, key=lambda s: (s.benchmark, s.model, s.subset, s.metric))
        ],
    }
    scores_bytes = (_dumps(full_scores) + "\n").encode("utf-8")

    inputs = []
    for pair in sorted(pairs, key=lambda p: (p.benchmark, p.model, p.subset)):
        rows = counts[(pair.benchmark, pair.model, pair.subset)]
        if rows != pair.expected_samples:
            raise AnalysisError(
                f"{pair.benchmark}/{pair.model}/{pair.subset}: "
                f"{rows} validated samples, expected {pair.expected_samples}"
            )
        for role, path in (("predictions", pair.predictions), ("reviews", pair.reviews)):
            inputs.append(
                {
                    "path": _relative(path, data_root),
                    "role": role,
                    "sha256": _sha256(path),
                    "rows": rows,
                    "expected_samples": pair.expected_samples,
                    "benchmark": pair.benchmark,
                    "model": pair.model,
                    "subset": pair.subset,
                    "metric": pair.metric,
                    "include_in_reference": pair.include_in_reference,
                }
            )
    manifest = {
        "schema_version": 1,
        "inputs": inputs,
        "output_sha256": {
            "samples.jsonl": hashlib.sha256(samples_bytes).hexdigest(),
            "full_scores.json": hashlib.sha256(scores_bytes).hexdigest(),
        },
        "scoring_policy": SCORING_POLICY,
        "limitations": LIMITATIONS,
    }
    manifest_bytes = (_dumps(manifest) + "\n").encode("utf-8")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(output_dir / "samples.jsonl", samples_bytes)
        _write_atomic(output_dir / "full_scores.json", scores_bytes)
        _write_atomic(output_dir / "manifest.json", manifest_bytes)
    except OSError as exc:
        raise AnalysisError(f"Cannot write reports to {output_dir}: {exc.strerror or exc}") from exc
