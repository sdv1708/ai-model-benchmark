# Benchmark reference and subset studies

This package analyzes saved benchmark predictions and reviews.
It reproduces full scores and tests smaller question sets without new inference.
It also contains an offline image-pair prototype.

Use Python 3.12 and uv.
The [usage guide](../USAGE.md) contains installation and command procedures.

## Input contract

`inputs.py` expects a fixed directory inventory:

```text
Evals/
  Part 1/
    predictions/         Two benchmarks, three models each
    reviews/             Matching grades
  MMMU/
    predictions/glm-4.5v-fp8/   Twenty-two subject files
    reviews/glm-4.5v-fp8/       Matching subject reviews
```

The coding benchmark has 315 tasks per model.
AA-LCR has 100 questions per model.
MMMU has 30 questions per supplied subject, for 660 rows.
The reference command validates 28 prediction/review pairs and 1,905 joined results.

The loader rejects missing or unexpected files, LFS pointers, invalid JSON, blank lines, duplicate identities, and inconsistent joins.
It also rejects generation errors and invalid grades.
Missing grades remain errors.
They do not become zero scores or disappear from the denominator.

Source references preserve relative file paths and line numbers.
The package validates supplied MMMU rows, but excludes them from the six coding and long-context score summaries.

## Full reference scores

From this directory, run:

```powershell
uv sync --locked
uv run benchmark-reference --data-root ../Evals --output-dir output/reference
```

| Output             | Content                                                         |
| ------------------ | --------------------------------------------------------------- |
| `samples.jsonl`    | Normalized grades, identities, metadata, and source references. |
| `full_scores.json` | Six full-panel means on a 0..1 scale.                           |
| `manifest.json`    | Input hashes, counts, policies, and report hashes.              |

The [root README](../README.md#recorded-results) lists the recorded scores.
The [recorded source manifest](../docs/data/task2-manifest.json) identifies their inputs.
These are historical artifact results, not live endpoint measurements.

## Subset selection

| Benchmark     | Candidate                      | Selection information                             |
| ------------- | ------------------------------ | ------------------------------------------------- |
| LiveCodeBench | `difficulty_stratified`        | Historical reference difficulty.                  |
| LiveCodeBench | `response_stratified`          | Historical reference response patterns.           |
| AA-LCR        | `metadata_stratified`          | Input length and source document count.           |
| AA-LCR        | `length_difficulty_stratified` | Input length and historical reference difficulty. |

The selector divides tasks into strata and samples within each occupied stratum.
A stratum is a group with shared selection characteristics.
Reference grades define historical difficulty; the target model's grades remain excluded.
AA-LCR metadata must agree across models.
Model-specific usage fields do not become benchmark length metadata.

The study also reports `uniform_random`, `easiest_only`, and `hardest_only` as comparison baselines.
These names cannot become eligible production candidates through the candidate selector API.

Default retained fractions are `0.1`, `0.2`, `0.3`, `0.5`, and `1.0`.
Default seeds are `0` through `19`.
The selected count is `ceil(population_count * retained_fraction)`.
Budgets that cannot cover every occupied stratum fail.
Seeds control repeatable hash priorities; subsets at different budgets need not be nested.

### Weighted score example

Suppose a 100-question pool contains two strata.
The first has 80 questions; the second has 20.
The selector retains four questions from the first and two from the second.

Each first-stratum question receives weight `(80 / 100) / 4 = 0.2`.
Each second-stratum question receives weight `(20 / 100) / 2 = 0.1`.
If three first-stratum answers and one second-stratum answer succeed, the weighted estimate is:

```text
weighted score = 3 * 0.2 + 1 * 0.1 = 0.7
raw subset mean = 4 / 6 = 0.666667
```

The weights restore each stratum's population contribution.
The raw mean overweights the more heavily sampled second stratum.
The report retains both estimates for inspection.

## Validation protocol

A score fold excludes one model from selection information.
The selected subset then estimates that held-out model's full score.
With three models, two historical reference models remain.

A pair-transfer fold excludes both compared models.
The remaining model defines selection information.
The selected subset then estimates the difference between the excluded models.
This protocol prevents either compared model from defining its own favorable subset.

Each default study includes 1,500 score evaluations and 1,500 pair-transfer evaluations.
The count includes candidates and comparison baselines.
These evaluations reuse fixed saved grades.
They are not independent new model observations.

## Uncertainty and threshold decisions

Stratified intervals use finite-population bounds with correction across strata.
The interval interpretation assumes uniform sampling within fixed strata.
Hash priorities approximate that sampling design.
Intervals describe the recorded pool, not future tasks or model generation randomness.

| Result       | Rule                                                               |
| ------------ | ------------------------------------------------------------------ |
| GO           | The entire score interval meets or exceeds the supplied threshold. |
| NO GO        | The entire score interval is below the threshold.                  |
| Inconclusive | The interval includes values on both sides of the threshold.       |

For example, interval `[0.68, 0.74]` is inconclusive at threshold `0.70`.
A point estimate of `0.72` does not remove that uncertainty.
Full retention gives zero subset sampling error for the fixed grades.

Pair intervals use discordant outcomes; shared successes and failures cancel.
Pair-order evidence remains separate from reference-assisted whole-panel rankings.
Searching across methods and sizes does not give simultaneous interval coverage for the final selected setting.

AA-LCR has one recorded review per answer.
Judge variance cannot be estimated from that record.
`judge_noise.py` therefore reports hypothetical label-change sensitivity separately.
Changed-judgment counts are analysis assumptions, not measured judge error rates.

## Operating-point policy

`operating_points.py` applies a retrospective illustrative policy to both studies.
The smallest eligible tested candidate is selected.
Comparison baselines remain ineligible.

| Gate                                          |       Default limit |
| --------------------------------------------- | ------------------: |
| Worst held-out fold mean absolute error       |       At most 0.03. |
| Maximum absolute score error                  |       At most 0.08. |
| Maximum score standard deviation across seeds |       At most 0.03. |
| Maximum mean score interval width             |       At most 0.20. |
| Minimum score and pair interval coverage      | At least 0.95 each. |
| Minimum pair-order agreement                  |      At least 0.95. |
| Minimum decisive pair fraction                |      At least 0.80. |
| Maximum wrong pair fraction                   |                  0. |
| Minimum threshold point agreement             |      At least 0.95. |
| Minimum decisive threshold fraction           |      At least 0.80. |
| Maximum false threshold fraction              |                  0. |

Score differences use the 0..1 scale.
For example, `0.03` means three percentage points.
Gates apply to the relevant individual folds, pairs, and thresholds, rather than pooled averages alone.

The recorded analysis uses coding threshold `0.7` and AA-LCR threshold `0.6`.
It selects all 315 coding tasks and all 100 long-context questions.
No smaller tested candidate passes every gate.
The policy is retrospective and does not certify deployment performance.

## Commands and reports

From this directory, run:

```powershell
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning
uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-pruning
uv run part-a-operating-points --data-root ../Evals --output-dir output/operating-points --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
```

Coding and long-context studies write these reports:

| File                    | Purpose                                                                       |
| ----------------------- | ----------------------------------------------------------------------------- |
| `scores.json`           | Validated per-model grades and source locations.                              |
| `selections.jsonl`      | Score-fold indices, strata, weights, and reference identities.                |
| `pair_selections.jsonl` | Independently held-out pair selections.                                       |
| `fidelity.json`         | Score estimates, intervals, ordering, and pair results.                       |
| `summary.csv`           | Score error, seed sensitivity, ordering, and overlap summaries.               |
| `pair_summary.csv`      | Pair differences, order agreement, interval coverage, and decisive fractions. |
| `decisions.csv`         | Threshold agreement, false decisions, and decisive fractions.                 |
| `manifest.json`         | Inputs, implementation hashes, settings, limits, and output hashes.           |

Without thresholds, `decisions.csv` contains only its header.
AA-LCR also writes metadata, coverage, and judge sensitivity reports.
Operating-point output adds `operating_points.json`, `curves.csv`, and benchmark report subdirectories.

## Publication and reproducibility

Validation and serialization finish before report publication starts.
Output locations inside the input tree are refused.
Stable ordering and UTF-8 encoding support repeatable output bytes.
Input hashes identify exact file bytes.
Implementation hashes normalize CRLF to LF.

Each output file is replaced atomically.
The manifest is written last and contains hashes of the other reports.
Several file replacements do not form a transaction.
After an interrupted run, readers must verify manifest hashes.
Inputs must remain unchanged during analysis.
Only one writer should use a report directory.

Recorded summaries under `docs/data/` represent specific historical configurations.
Their manifests can reference full local report files that are regenerated rather than checked in.
Changing documentation does not regenerate or recertify those historical results.

## Native EvalScope boundary

This package does not include native EvalScope adapters or `evalscope_ext`.
Those implementations live in the public [EvalScope pruning repository](https://github.com/sdv1708/evalscope-pruning).
Its README has a synthetic smoke command that needs no credentials.
The following integration records remain available:

| File                          | Recorded integration                                            |
| ----------------------------- | --------------------------------------------------------------- |
| `evalscope-baseline.json`     | Upstream commit and synthetic native adapter baseline.          |
| `evalscope-lcb.json`          | Coding adapter, source identity, and default retained fraction. |
| `evalscope-aa-lcr.json`       | Long-context adapter, source verification, and judge limits.    |
| `evalscope-compare-runs.json` | Saved-run comparison module and schema versions.                |

`tools/export_lcb_panel.py` and `tools/export_aa_lcr_panel.py` produce reference panels.
`tools/audit_evalscope_lcb.py` and `tools/audit_evalscope_aa_lcr.py` require an appropriate native checkout.
Their optional tokenizer integration requires the `integration` dependency extra.
The local reference, subset, and image commands work independently of that checkout.

## Image-pair prototype

The [harness reference](MMMU_HARNESS.md) defines image inputs, request plans, semantic review, and saved-response scoring.
The [study proposal](MMMU_PROBE_DESIGN.md) defines the larger research question and necessary controls.
The synthetic demo does not run that full study.

From this directory, run:

```powershell
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
```

Use a new destination each time.
The command calls no endpoint.

## Verification

From this directory, run:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The tests use synthetic data with known answers.
Raw-data audit tools reconstruct results independently from report summaries.
Audit scripts use assertions, so Python optimization mode must remain disabled.
