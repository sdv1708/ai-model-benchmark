# Task 2 full-benchmark reference analysis

## Operational Handout B (issue #25)

The [half-page PDF](../output/pdf/handout-b.pdf) explains customer value,
tomorrow's practice commands, GO/NO GO/inconclusive interpretation and the
proposed image probe's value. Read the [editable source](HANDOUT_B.md),
[detailed beginner/interview guide and real endpoint runbook](ISSUE_25_GUIDE.md),
and [acceptance evidence](../docs/issue-25-evidence.md).
The defended settings retain all 315 coding / 100 long-context questions;
no savings or live multimodal conclusion are claimed.

## Technical Handout A (issue #24)

The [one-page PDF](../output/pdf/handout-a.pdf) explains the Part A approach,
defended retained sizes, Part B design, assumptions and future experiments.
Read the [editable Markdown](HANDOUT_A.md), [detailed interview guide](ISSUE_24_GUIDE.md),
and [acceptance/verification record](../docs/issue-24-evidence.md).
The selected defaults retain 315/315 coding and 100/100 AA-LCR questions;
no smaller tested candidate passed the illustrative policy. Proposed MMMU
budgets and synthetic harness counts are explicitly distinguished from model results.

## Paired image prototype (issue #23)

Read the [harness contract](MMMU_HARNESS.md), [interview walkthrough](ISSUE_23_GUIDE.md)
and [acceptance evidence](../docs/issue-23-evidence.md). From this directory:

```powershell
uv sync --locked
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
```

The offline prototype creates seven deterministic transformation families,
stable pairs and future request plans, then measures saved responses with QA,
consistency and missing-outcome bounds. The demo is entirely synthetic. It
does not select a full-MMMU probe, call a model or implement a native pruner.

## Full-dataset MMMU probe design (issue #22)

Read the [technical proposal](MMMU_PROBE_DESIGN.md),
[beginner-to-interview walkthrough](ISSUE_22_GUIDE.md) and
[acceptance evidence](../docs/issue-22-evidence.md).
The researched official inventory has 11,550 questions across 30 subjects;
the supplied 660 validation references cover only 22 subjects.
The proposal separates weighted population estimation from diagnostic coverage,
uses paired image/text controls and eight visual stress axes, and specifies
OpenAI-compatible requests, scoring, provenance, uncertainty and cost.
No probe was selected or run, and no accuracy or compression saving is established.
An eventual runnable implementation belongs inside the pinned EvalScope fork.

## Native EvalScope baseline (issue #18)

The [private EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning)
now contains a registered `pruning_smoke` benchmark, with an exact upstream base
and implementation commit recorded in [evalscope-baseline.json](evalscope-baseline.json).
Read the [beginner walkthrough](ISSUE_18_GUIDE.md) and
[acceptance evidence](../docs/issue-18-evidence.md). This is the native integration
foundation. Issues #19 and #20 add native coding and AA-LCR adapters; issue #21
adds the saved-run comparison described below. The analysis commands retain their behavior.

## Full-versus-pruned run comparison (issue #21)

In the separate pinned EvalScope fork, run:

```powershell
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/comparison-smoke
python -m evalscope_ext.tools.compare_runs --full outputs/comparison-smoke/full --pruned outputs/comparison-smoke/pruned --threshold 0.8
```

The credential-free Native smoke produces 12 full / 3 retained synthetic questions,
matching 100% scores and zero-point error, while the subset decision remains
inconclusive with completion bounds [0.25,1.0]. This is integration evidence,
not validated production compression. The module validates matching populations,
settings, grading inputs, complete attempts, weights and report/review consistency.
See the [beginner-to-interview walkthrough](ISSUE_21_GUIDE.md),
[integration pin](evalscope-compare-runs.json) and
[acceptance evidence](../docs/issue-21-evidence.md). The fork's `COMPARE_RUNS.md`
documents the full real coding CLI contract, actual `--work-dir` flag, optional
threshold, multiple-model ordering, output schema and limitations.

## Part A operating points (issue #17)

[The complete #14–#17 walkthrough](ISSUE_17_GUIDE.md) connects input validation,
selection, weighting, held-out evaluation, judge uncertainty and decision policy.
Run both benchmarks against one explicitly retrospective illustrative policy:

```powershell
uv sync --locked
uv run part-a-operating-points --data-root ../Evals --output-dir output/operating-points --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
uv run python tools/audit_operating_points.py --reports output/operating-points
```

Run from `task2/`. Thresholds are examples, not inferred customer requirements.
The guide includes independent raw-data audit commands. The five-size, twenty-seed
replay retains **315 coding / 100 AA-LCR questions** as full-reference fallbacks:
no smaller tested candidate passes every gate. Census does not remove unmeasured
judge uncertainty. No production compression is certified.
See [acceptance evidence](../docs/issue-17-evidence.md).

[Issue #14](https://github.com/sdv1708/ai-model-quality-challenge/issues/14) validates
all 56 supplied JSONL files, joins 28 prediction/review pairs, normalizes 1,905 scored
records, and calculates six Part A reference scores. The scaffold is implemented.
Read [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) for architecture, concepts, and trade-offs,
and [acceptance evidence](../docs/issue-14-evidence.md) for the recorded verification.

This package analyzes the supplied offline evidence. Framework integration lives
in the separate pinned EvalScope-derived repository introduced in issue #18;
the analysis package itself is not the benchmark runtime.

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
with seeds **0..19**: **1,500 leave-one-model-out score runs plus 1,500
leave-two-models-out pair-transfer runs**, 3,000 evaluations total.
`--keep-ratios 0.2 0.5 --seeds 0 1 2` narrows an exploratory run. The ratio is the
fraction **retained**, with `ceil(N * ratio)` tasks. It is not the fraction removed.
Budgets too small to cover every occupied stratum fail rather than silently losing
coverage. Duplicate ratios/seeds and invalid grades/configuration also fail with
exit code 2 before publication.

`--confidence 0.95` sets nominal design coverage. To demonstrate threshold decisions:

```powershell
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-study-v2 --thresholds 0.6 0.7 0.8
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/lcb-study-v2
```

Thresholds are optional and illustrative here, not invented customer requirements.
An interval wholly above the threshold gives GO, wholly below gives NO GO;
overlap gives **inconclusive**. Equality meets the threshold. Fixed-budget intervals
invert hypergeometric tails with exact integer comparisons and Bonferroni across
strata. They measure uncertainty about the fixed supplied pool under uniform
within-stratum sampling, not generation randomness or future task distributions.
Fixed hash priorities approximate the probability sampling assumption. Coverage is
not simultaneous across a search over methods/budgets/seeds. Easiest/hardest have
no design intervals below full retention. See the guide for discrete endpoints.

Outputs are deterministic UTF-8 files:

- `scores.json`: 945 validated coding grades with source paths and line numbers.
- `selections.jsonl`: each fold/method/ratio/seed, reference models, selected unique
  indices, stratum sizes, selected counts, and population weights.
- `pair_selections.jsonl`: separately auditable selections excluding both compared models.
- `fidelity.json`: full scores, weighted estimates, raw subset means, held-out error,
  exact score intervals, threshold decisions, tie-aware ordering, and pair-transfer results.
- `summary.csv`: held-out MAE/RMSE/bias/worst error, raw-mean MAE, ordering fidelity,
  error spread and mean pairwise Jaccard overlap across seeds within each fold.
- `pair_summary.csv`: independently held-out pair differences, ordering, interval
  coverage/width, decisive and wrong-decisive fractions.
- `decisions.csv`: threshold decision agreement, false GO/NO GO and decisive fractions;
  header only when no thresholds are supplied.
- `manifest.json`: raw input hashes, implementation hashes, configuration, policies,
  limitations, and hashes of the other seven reports (schema version 2).

Implementation hashes normalize CRLF to LF for equivalent Git checkouts; input
and output hashes fingerprint exact bytes.

Only the six coding files are parsed and hashed by this command; the supplied
whole-tree file inventory must still match the reference pipeline's contract.
AA-LCR and MMMU grades are not evaluated here. Reports cannot overwrite input data.
Each file is replaced atomically; the manifest is last. Verify hashes and exit status
because publication is not a transaction across all eight files. Keep inputs static
and use one writer per output directory. Seeds are repeatable hash priorities;
the subsets at different budgets are not guaranteed to be nested.

At 50% retention, difficulty-stratified selection has **1.53 percentage points**
pooled held-out MAE; response-pattern selection has **1.61 points**. Exact three-model
ordering is preserved in **43.3% / 63.3%** of the respective runs. Ranking includes
two in-sample reference models on the same subset; only held-out error tests model
transfer. These experiments do **not** establish a sufficient production pruning
ratio or guarantee a future model's score.

The stricter pair-transfer protocol excludes both compared models and leaves only
one reference. At half retention, both candidates preserve pair order in **86.7%**
of runs, while only **38.3%** of their nominal 95% paired intervals give a decisive
ordering. No decisive error was observed on this panel. Common successes/failures
cancel; bounds apply directly to the two discordance directions. With one reference,
the two candidates have identical strata, so these are not independent wins.
Uniform comparison gives 80.0% order agreement but narrower intervals and more
decisive results; it remains a forbidden production strategy. This exposes the
coverage/precision trade-off rather than claiming every metric improved.

See the [research and interview guide](ISSUE_15_GUIDE.md),
[acceptance evidence](../docs/issue-15-evidence.md), and checked-in
[complete summaries](../docs/data/task2-lcb-pruning-summary.csv). Full audit artifacts
are regenerated locally rather than committing 25 MB of selected-index records.

## AA-LCR candidates and judge sensitivity (issue #16)

For a hands-on introduction, open the [eight-question learning walkthrough](learning/benchmark-walkthrough.html)
and follow the [study order and exercises](learning/README.md). It uses synthetic
data to explain offline replay, weighting and hypothetical judge changes.

Two metadata-aware candidates cover input length plus document count or historical
reference difficulty. The study runs the same five retention levels and twenty
seeds, with 1,500 score runs and 1,500 independently held-out pair runs. From `task2/`:

```powershell
uv sync --locked
uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-pruning
uv run python tools/audit_aa_lcr.py --data-root ../Evals --reports output/aa-lcr-pruning
```

At half retention, pooled held-out score MAE is 2.90 / 3.27 percentage points,
and pair ordering agrees in 88.3% / 90.0% of runs. Wide design intervals remain
inconclusive for all half-retention candidate pair comparisons. There is only one
recorded judge review per answer: judge variance is unidentified. Hypothetical
label-flip sensitivity is reported separately, with `--flip-counts 0 1 2 5 10`;
these counts are assumptions, not measured error rates. Two changed judgments can
tie the closest full-score pair; three can reverse it. No production pruning level
is certified. See the [simple-to-technical guide](ISSUE_16_GUIDE.md),
[acceptance evidence](../docs/issue-16-evidence.md), and
[checked-in summaries](../docs/data/task2-aa-lcr-pruning-summary.csv).

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

## Native coding integration

See [issue #19](ISSUE_19_GUIDE.md) for `live_code_bench_pruned` in the private
EvalScope repository, panel export, native parity checks and live run instructions.
The adapter defaults to the full 315-task reference; no smaller operating point
has been certified by this integration work.

## Native long-context integration

See [issue #20's walkthrough](ISSUE_20_GUIDE.md) for `aa_lcr_pruned`, benchmark
signals, weights, judge noise, source-version findings and runnable verification.
[evalscope-aa-lcr.json](evalscope-aa-lcr.json) pins the native implementation and
the historical source. The default retains all 100 reference questions. Smaller
ratios remain research settings; no judge-robust compression is certified.
