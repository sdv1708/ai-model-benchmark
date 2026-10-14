# Task 2 full-benchmark reference analysis

[Issue #14](https://github.com/sdv1708/ai-model-quality-challenge/issues/14) validates
all 56 supplied JSONL files, joins 28 prediction/review pairs, normalizes 1,905 scored
records, and calculates six Part A reference scores. The scaffold is implemented.
Read [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) for architecture, concepts, and trade-offs,
and [acceptance evidence](../docs/issue-14-evidence.md) for the recorded verification.

This package analyzes the supplied offline evidence. The eventual pruning code
must live inside the pinned evalscope fork in later issues; this scaffold does
not satisfy that separate integration requirement.

## Setup and commands

Use Python 3.12 and uv. From the repository root:

```powershell
cd task2
uv sync --locked
uv run python -m benchmark_reference --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

If evaluation files are LFS pointers, run `git lfs pull` from the repository root.
No API keys or live inference are needed.

## Reproduce the reference results

From `task2/`:

```powershell
uv run benchmark-reference --data-root ../Evals --output-dir output/reference
```

Successful runs exit 0 after validating every shipped input, then produce:

- `output/reference/samples.jsonl`: all normalized samples and both source locations.
- `output/reference/full_scores.json`: six Part A summaries, on a 0..1 score scale.
- `output/reference/manifest.json`: source hashes, counts, policy, limits, and output hashes.

MMMU subjects get separate subset identities and are validated here. The 660
reference rows are not the full approximately 12,000-sample MMMU dataset.

## Recorded results and failure policy

| Benchmark        | Model        | Successful samples | Mean     |
| ---------------- | ------------ | ------------------ | -------- |
| AA-LCR           | gpt-oss-120b | 48 / 100           | 0.480000 |
| AA-LCR           | kimi-k2.5    | 66 / 100           | 0.660000 |
| AA-LCR           | minimax-m2.5 | 64 / 100           | 0.640000 |
| LiveCodeBench v5 | gpt-oss-120b | 241 / 315          | 0.765079 |
| LiveCodeBench v5 | kimi-k2.5    | 198 / 315          | 0.628571 |
| LiveCodeBench v5 | minimax-m2.5 | 195 / 315          | 0.619048 |

These describe the supplied stored artifacts, not live endpoints or leaderboards.
Checked-in [scores](../docs/data/task2-full-scores.json) and
[manifest](../docs/data/task2-manifest.json) identify the inputs used.

Validation rejects malformed/ambiguous JSON, LFS pointers, blank lines, invalid
indices, duplicate records, wrong models/counts, mismatched joins, malformed grades,
generation errors, and conflicting metadata. Missing grades are never dropped or
turned into zero. Recognized errors include source context and exit with code 2.
The file inventory deliberately enforces this challenge's fixed dataset contract.

All validation and serialization finish before new reports are published. Writing
inside the input tree is refused, including resolved destination symlinks. Each
report is replaced atomically using a unique temporary file; the manifest is written
last and hashes the other two outputs. This is not a three-file transaction: readers
can detect interrupted publication by checking its output hashes. Prior successful
reports remain on an input-validation failure. Use one writer per output directory
and keep inputs unchanged during analysis; there is no concurrent snapshot isolation.

Stable ordering, UTF-8 bytes, relative source paths, and no timestamps make unchanged
runs byte-identical, including runs in different output directories. Tests use
synthetic fixtures with known answers; no tests are skipped or marked expected failures.
