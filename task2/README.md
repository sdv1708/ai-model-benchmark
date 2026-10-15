# Task 2 full-benchmark reference analysis

[Issue #14](https://github.com/sdv1708/ai-model-quality-challenge/issues/14) validates
all 56 supplied JSONL files, joins 28 prediction/review pairs, normalizes 1,905 scored
records, and calculates six Part A reference scores. The scaffold is implemented.
Read [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) for architecture, concepts, and trade-offs,
and [acceptance evidence](../docs/issue-14-evidence.md) for the recorded verification.

This package analyzes the supplied offline evidence. The eventual pruning code
must live inside the pinned evalscope fork in later issues; this scaffold does
not satisfy that separate integration requirement.

## LiveCodeBench candidate experiments (issue #15)

Two reference-only candidates are implemented: `difficulty_stratified` groups tasks
by historical pass count; `response_stratified` preserves each historical pass/fail
pattern, including opposite disagreements. Both cover every occupied group, sample
without replacement, and return population weights. Uniform random, easiest-only,
and hardest-only are explicitly labelled comparison baselines and rejected by the
candidate selector API.

From `task2/`, after `uv sync --locked`:

```powershell
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/lcb-pruning
```

The module form is `uv run python -m benchmark_reference.pruning_cli ...`.
Default retention fractions are **0.1, 0.2, 0.3, 0.5, 1.0** (32/63/95/158/315 tasks),
with seeds **0..19** and three leave-one-model-out folds: **1,500 runs** total.
`--keep-ratios 0.2 0.5 --seeds 0 1 2` narrows an exploratory run. The ratio is the
fraction **retained**, with `ceil(N * ratio)` tasks. It is not the fraction removed.
Budgets too small to cover every occupied stratum fail rather than silently losing
coverage. Duplicate ratios/seeds and invalid grades/configuration also fail with
exit code 2 before publication.

Outputs are deterministic UTF-8 files:

- `scores.json`: 945 validated coding grades with source paths and line numbers.
- `selections.jsonl`: each fold/method/ratio/seed, reference models, selected unique
  indices, stratum sizes, selected counts, and population weights.
- `fidelity.json`: full scores, weighted estimates, raw subset means, held-out error,
  tie-aware pair agreement and Kendall tau-b, plus fold and pooled summaries.
- `summary.csv`: held-out MAE/RMSE/bias/worst error, raw-mean MAE, ordering fidelity,
  error spread and mean pairwise Jaccard overlap across seeds within each fold.
- `manifest.json`: raw input hashes, implementation hashes, configuration, policies,
  limitations, and hashes of the other four reports.

Implementation hashes normalize CRLF to LF for equivalent Git checkouts; input
and output hashes fingerprint exact bytes.

Only the six coding files are parsed and hashed by this command; the supplied
whole-tree file inventory must still match the reference pipeline's contract.
AA-LCR and MMMU grades are not evaluated here. Reports cannot overwrite input data.
Each file is replaced atomically; the manifest is last. Verify hashes and exit status
because publication is not a transaction across all five files. Keep inputs static
and use one writer per output directory. Seeds are repeatable hash priorities;
the subsets at different budgets are not guaranteed to be nested.

At 50% retention, difficulty-stratified selection has **1.53 percentage points**
pooled held-out MAE; response-pattern selection has **1.61 points**. Exact three-model
ordering is preserved in **43.3% / 63.3%** of the respective runs. Ranking includes
two in-sample reference models on the same subset; only held-out error tests model
transfer. These experiments do **not** establish a sufficient production pruning
ratio or guarantee a future model's score.

See the [research and interview guide](ISSUE_15_GUIDE.md),
[acceptance evidence](../docs/issue-15-evidence.md), and checked-in
[complete summaries](../docs/data/task2-lcb-pruning-summary.csv). Full audit artifacts
are regenerated locally rather than committing 25 MB of selected-index records.

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
