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

## Two-stage threshold decision

`threshold-decision` answers one question for each model: is the full-set score at or above the customer threshold `t`?
One command runs LiveCodeBench and AA-LCR, and one report shows both benchmarks side by side.

1. Select a stage-1 probe with the policy stratifier. The selector uses the reference panel only: reference grades and, for AA-LCR, the question metadata.
2. Compute a `1 - alpha` interval for the full-set score with the policy `interval_method`. At alpha `0.05`, this is a 95% interval.
3. If the lower bound is at or above `t`, decide GO and stop.
4. If the upper bound is below `t`, decide NO GO and stop.
5. Otherwise ESCALATE. Grade the remaining questions and decide on the full set.

The census has no sampling error, so ESCALATE always resolves.
Stage 1 spends the policy alpha.
The census spends nothing.
Pair-order metrics are diagnostics only and are not gates.

### Interval methods

The policy `interval_method` names one of four methods.
Each method reads only the passes in each sampled stratum.

| `interval_method`                      | Interval                                                                                                 |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `pooled_exact_hypergeometric`          | Exact hypergeometric interval for all sampled questions as one simple random sample. It ignores strata.  |
| `stratified_bonferroni_hypergeometric` | Exact interval for each stratum at `alpha / H`, with the bounds added. It is the conservative reference. |
| `stratified_wilson`                    | Wilson score interval for the stratified estimate, with the Kish effective sample size and the FPC.      |
| `stratified_bootstrap_percentile`      | Percentile interval of 1,999 Rao-Wu rescaling bootstrap resamples.                                       |

`H` is the number of occupied strata.
FPC is the finite-population correction.
The Kish effective sample size is `1 / sum(W_h^2 * (N_h - n_h) / ((N_h - 1) * n_h))`, where `W_h = N_h / N`.
Without the FPC factor, this is the usual Kish size for the weights `N_h / n_h`.

The Rao-Wu bootstrap draws `n_h - 1` questions with replacement from the sample of each stratum.
With `x` passes in the draw, the stratum mean becomes `p_h + sqrt(1 - n_h / N_h) * (x / (n_h - 1) - p_h)`.
The variance of a replicate is then the unbiased stratified variance with the FPC.
A stratum with one sampled question, or with only passes or only failures, adds no bootstrap width.
The bootstrap seed comes from the stratum counts, so the interval is a fixed function of the data.

Each method clips its interval to the feasible range.
The sampled passes are known, so the full-set pass count is at least `sum(s_h)` and at most `sum(N_h - n_h + s_h)`.
The clip never removes the true score.
A census therefore gives width 0 for every method.

With one stratum, each Wilson bound is within `2 / n` of the exact bound at every observed score.
The bootstrap bounds meet the same tolerance for observed scores from 0.2 to 0.8.
Bonferroni with one stratum is the exact interval.

### Policy files

A versioned JSON file in `policies/` holds every setting.
The file has a `benchmarks` object with one section for each benchmark.
Each section has its own threshold, stage size, interval method, stratifier, and study settings.
The file-level `policy_id`, `version`, and `frozen` apply to every section.
A file can hold one benchmark or both.
The draft is [`threshold-draft.json`](policies/threshold-draft.json):

| Setting           | `live_code_bench_v5`                                             | `aa_lcr`                                                       |
| ----------------- | ---------------------------------------------------------------- | -------------------------------------------------------------- |
| `threshold`       | `0.70`                                                           | `0.60`                                                         |
| `alpha`           | `0.05`                                                           | `0.05`                                                         |
| `stage1_size`     | `63` of 315 questions                                            | `20` of 100 questions                                          |
| `interval_method` | `pooled_exact_hypergeometric`                                    | `pooled_exact_hypergeometric`                                  |
| `stratifier`      | `difficulty_stratified`                                          | `length_difficulty_stratified`                                 |
| `seeds`           | Selector seeds `0` through `19`                                  | Selector seeds `0` through `19`                                |
| `simulation`      | Seed `56`, true scores `0.30` to `0.90` by `0.05`, 50 per seed   | The same                                                       |
| `coverage`        | 2,000 draws per cell, stage sizes `32`, `63`, `95`, `158`, `221` | 2,000 draws per cell, stage sizes `12`, `20`, `30`, `50`, `70` |
| `cost`            | Stage sizes as for coverage; four true-score bands               | Stage sizes as for coverage; four true-score bands             |

The stratifier must belong to its benchmark.
LiveCodeBench uses `difficulty_stratified` or `response_stratified`.
AA-LCR uses `metadata_stratified` or `length_difficulty_stratified`, the stratifiers of the AA-LCR subset study.
The AA-LCR threshold `0.60` is the threshold of the recorded operating-point analysis.
The smallest AA-LCR stage size is `12`, because `length_difficulty_stratified` has 12 occupied strata and each stratum needs one question.

Policy files use `schema_version` 4.
Schema 2 adds the `coverage` section.
Schema 3 adds the `cost` section.
Schema 4 puts the settings in one section for each benchmark.
The LiveCodeBench draft bands are `0.30` to `0.50`, `0.55` to `0.65`, `0.70` to `0.75`, and `0.80` to `0.90`.
The AA-LCR draft bands are `0.30` to `0.40`, `0.45` to `0.55`, `0.60` to `0.65`, and `0.70` to `0.90`.
Each band is an inclusive `[low, high]` pair.
The bands must be ascending and separate, and each policy true score must be in exactly one band.
A policy can have at most 4 bands, so that each band has its own color, dash pattern, and marker.
The manifest records the SHA-256 of the exact policy file bytes.
`.gitattributes` keeps policy files at LF line endings, so the hash is the same on every platform.

`--real-grades` requests a replay on real model grades.
The command refuses it unless the policy is marked `frozen` and its hash matches the entry in `policies/frozen-policies.json`.
The command reads that lock file from git `HEAD`.
An uncommitted edit to the lock file therefore authorizes nothing.
No policy is frozen yet.
The real replay itself is issue #63.

### Simulated models

Each question's difficulty is its pass rate among the three reference models.
A simulated model passes question `i` with odds proportional to `(p + 0.5) / (m + 0.5 - p)`, where `p` of `m` reference models pass it.
The draw has exactly `ceil(true_score * N)` passes, where `N` is 315 for LiveCodeBench and 100 for AA-LCR.
The full-set score is therefore known: it is the smallest score at or above the true score.
A wrong decision differs from the decision on that full-set score.

A simulated AA-LCR model answers the 100 AA-LCR questions.
Its pass probability uses the AA-LCR reference difficulty.
The AA-LCR metadata gives the input length and the source document count of each question.
This metadata defines the strata of both AA-LCR stratifiers.
The metadata also sets the token cost, because input tokens are most of an AA-LCR answer.
The metadata does not change the simulated pass probability.

The generator and the stratifiers `difficulty_stratified`, `response_stratified`, and `length_difficulty_stratified` use the same reference difficulty.
This favors those stratifiers.
The `metadata_stratified` strata do not use reference grades, so the generator does not favor them.
The error-rate study uses a second generator. It flips random grades of one reference model until the pass count reaches the true score.
Both generators start from the reference grades, so a simulated model is not an unseen model.

AA-LCR grades come from an LLM judge, and the saved data has one judgment for each answer.
Judge noise is therefore not measured.
The simulated grades have no judge noise, so the AA-LCR results do not include it.
The report states this limit beside every AA-LCR result.

### Interval coverage study

The command also measures the coverage of all four interval methods.
A cell is one stratifier, one coverage stage size, and one policy true score.
The study runs every cell for both stratifiers.
Each cell has 2,000 draws.
A draw is a new simulated model and a new stratified subset, so the draws are independent.
Every method sees the same draws.
No real model grades are used.
The policy key `coverage.subsets` sets the number of draws.

A method covers a draw when its interval holds the full-set score of the simulated model.
A method passes a cell when its coverage is at least 0.935.
That value is 0.95 minus 3 standard errors for 2,000 draws, rounded to 3 decimals.
The report shows coverage against true score for each setting, one line for each method, with the 0.935 line marked.
It also gives the lowest coverage and the mean interval width for each method and setting.

Coverage is measured over simulated models, not for one fixed model.
The coverage study uses the same generator as the decision study.

### Token cost

A saving in questions is not the same as a saving in tokens.
The command therefore gives every operating point a cost in tokens.
The unit is input plus output tokens of the model answers.

The loader reads the `usage` record of each saved answer in `Evals/Part 1/predictions/`.
It reads no grade.
Each predictions file must have the SHA-256 that the reference panel records, so the counts come from the same run as the reference grades.
A count is missing when the answer is absent, when `usage` is null, or when `input_tokens` or `output_tokens` is absent or null.
The command reports each missing count and never treats it as zero.
Any other bad value, such as a negative count, stops the command.
The committed predictions have no missing count.

An unseen model has no counts.
For each question, the estimate is the low, mean, and high total across the reference models that have a count.
A set of questions sums each estimate.
Low and high are therefore an envelope of the reference models, not a confidence interval.

A run decided at stage 1 uses the tokens of its probe.
A run that escalates keeps its stage-1 answers and grades the remaining questions, so it uses one full run.
For one probe, the expected cost is `T1 + p * (T - T1)`.
`T1` is the stage-1 tokens, `p` is the escalation probability, and `T` is the full-set tokens.
The cost for a true score is the mean over the selector seeds, weighted by the runs of each seed.
That value is equal to the mean tokens of the runs.
The cost fraction is the expected cost as a share of a full run.
Each estimate divides by its own `T`.

The policy `cost` section sets the stage sizes and the true-score bands of the cost curve.
For each cost stage size, the command runs the decision study with that stage-1 size.
The band cost is the mean over its true scores, each with equal weight.
The coverage draws also give the expected cost of every interval method.
The summary compares the two estimates for the policy method as a cross-check.

Result on the draft policy, mean estimate:

- A full LiveCodeBench run uses 4,532,328 tokens (low 1,555,578, high 7,177,805). That is 14,388 tokens for each answer. Output tokens are 96% of the total.
- A full AA-LCR run uses 9,616,201 tokens under the mean estimate. That is 96,162 tokens for each answer, 98% of them input.
- The 63-question probe uses 901,365 tokens, 0.199 of a full run.
- At 63 questions, the expected cost is 0.199 of a full run far from the threshold and 0.985 at true score 0.70.
- The band means at 63 questions are 0.204 (true score 0.30 to 0.50), 0.650 (0.55 to 0.65), 0.944 (0.70 to 0.75), and 0.338 (0.80 to 0.90).
- The low and high token totals differ by a factor of 4.6, but the cost fraction changes by less than 0.006. The ratio cancels most of the difference in answer length between the models.
- The two cost estimates for the policy method differ by at most 0.022 over 65 cells.

Near the threshold, a larger probe costs less, because fewer runs escalate.
Far from the threshold, a smaller probe costs less.
The comparison below uses 63 questions and `difficulty_stratified`.
The value is the mean cost fraction over the true scores.

- Stratified Wilson costs 0.444 of a full run. It passes every coverage cell.
- Pooled exact costs 0.453. It passes every coverage cell.
- Bonferroni exact costs 0.790. It passes every coverage cell.
- The bootstrap costs 0.400, but it fails coverage at 95 questions or fewer.

Issue #58 gave about 73,000 input tokens for an AA-LCR answer and about 1,700 tokens for a LiveCodeBench task.
The saved predictions do not agree.
The mean is 94,319 input tokens for an AA-LCR answer and 14,388 total tokens for a LiveCodeBench answer.
The token loader test checks the totals of all six predictions files.

### AA-LCR on the draft policy

The draft AA-LCR section uses threshold `0.60`, a 20-question probe, the pooled exact interval, and `length_difficulty_stratified`.
The run draws 1,000 simulated AA-LCR models at each true score, 13,000 models in total.
Judge noise is not measured: the saved data has one judgment for each answer, and the simulated grades have none.

| Result                                | LiveCodeBench, 63 of 315 |  AA-LCR, 20 of 100 |
| ------------------------------------- | -----------------------: | -----------------: |
| Share decided at stage 1              |                    0.684 |              0.314 |
| Wrong decisions                       |                 8/13,000 |           6/13,000 |
| Highest wrong-decision rate           |       0.007 at true 0.70 | 0.006 at true 0.60 |
| Mean expected cost across true scores |                    0.452 |              0.749 |
| Input share of tokens                 |                       4% |                98% |
| Largest input ratio between models    |                    1.352 |              1.030 |

- Every wrong-decision rate is below the one-tail bound `0.025`. The 6 AA-LCR wrong decisions are all at true score `0.60`, which is exactly the threshold.
- A 20-question AA-LCR probe gives a wide interval. The probe decides 86.6% of models at true score `0.30` and 86.0% at `0.90`, but fewer than 10% from `0.50` to `0.75`.
- For one AA-LCR question, the input counts of the three reference models differ by at most 3.0%. The input cost therefore depends on the documents, not on the model. At each true score, the low and high cost fractions differ by less than 0.0003.
- The band mean of the AA-LCR cost is 0.815 at 12 questions, 0.775 at 20, 0.670 at 30, 0.692 at 50, and 0.784 at 70. The 30-question probe is the cheapest tested size. Issue #62 sets the frozen stage size.
- Pooled exact and Bonferroni exact pass all 130 AA-LCR coverage cells; pooled exact has the lowest coverage `0.948`.
- Stratified Wilson fails 1 of 130 cells: `metadata_stratified`, 20 questions, true score `0.85`, coverage `0.933`.
- The bootstrap fails 79 of 130 cells, with the lowest coverage `0.013`. Most AA-LCR strata have one or two sampled questions at these sizes, and such a stratum adds no bootstrap width.

### Run the decision

```powershell
uv run threshold-decision --policy policies/threshold-draft.json --output-dir output/threshold-decision
```

The command runs every benchmark section of the policy file.
It writes one folder of tables for each benchmark and three shared files:

| File                             | Content                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| `<benchmark>/decisions.csv`      | One row per simulated model: true score, stage-1 result, decision, stage, and tokens used. |
| `<benchmark>/coverage.csv`       | One row per coverage cell and method: coverage, misses on each side, width.                |
| `<benchmark>/cost.csv`           | One row per cost stage size and true score: escalation rate and token cost.                |
| `<benchmark>/question_tokens.csv` | One row per question: its estimate and the counts of each reference model.                |
| `summary.json`                   | For each benchmark: decision summary for each true score, coverage verdicts, and limits.   |
| `report.html`                    | Self-contained report with charts and tables, in light and dark modes.                     |
| `manifest.json`                  | Policy hash, input hashes for each benchmark, and output hashes.                           |

`<benchmark>` is `live_code_bench_v5` or `aa_lcr`.
The report starts with a side-by-side table of both benchmarks.
Each benchmark then has its own section with the same charts and tables.
Every AA-LCR chart and table has the judge-noise limit beside it.

The command prints the manifest SHA-256.
Two runs with the same policy file give identical bytes.
`--workers` sets the number of processes for the cost and coverage studies.
The default is the number of CPUs.
The outputs are the same for every worker count.
`--panel-dir` sets the folder that holds the reference panels `lcb-reference-panel.json` and `aa-lcr-reference-panel.json`.
The default is `task2/data`.
`--data-root` sets the folder that holds `Part 1/predictions`.
The default is the `Evals` folder at the repository root.

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
