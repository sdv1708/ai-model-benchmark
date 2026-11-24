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
The [judge-noise measurement](#judge-noise-measurement) sends the saved answers to the judge again.

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

Policy files use `schema_version` 6.
Schema 2 adds the `coverage` section.
Schema 3 adds the `cost` section.
Schema 4 puts the settings in one section for each benchmark.
Schema 5 adds the `error_rate` section.
Schema 6 adds the `protocol` and `selection` blocks of a frozen policy.
The draft moved from schema 5 to schema 6 with no other change, and it has neither block.
The LiveCodeBench draft bands are `0.30` to `0.50`, `0.55` to `0.65`, `0.70` to `0.75`, and `0.80` to `0.90`.
The AA-LCR draft bands are `0.30` to `0.40`, `0.45` to `0.55`, `0.60` to `0.65`, and `0.70` to `0.90`.
Each band is an inclusive `[low, high]` pair.
The bands must be ascending and separate, and each policy true score must be in exactly one band.
A policy can have at most 4 bands, so that each band has its own color, dash pattern, and marker.
The manifest records the SHA-256 of the exact policy file bytes.
`.gitattributes` keeps policy files at LF line endings, so the hash is the same on every platform.

`--real-grades` runs the preregistered replay on real model grades (see [real replay](#real-replay)).
The command refuses it unless the policy is marked `frozen` and its hash matches the entry in `policies/frozen-policies.json`.
The command reads that lock file from git `HEAD`.
An uncommitted edit to the lock file therefore authorizes nothing.
Policy v1 is frozen (see [frozen policy v1](#frozen-policy-v1)).

### Frozen policy v1

[`threshold-v1.json`](policies/threshold-v1.json) is frozen policy `threshold-policy@v1`.
Its SHA-256 is `2b9e1d771567788ad4ee9213ab09484b7d0dce81c884782d949d5dde2814f1a8`.
The lock file [`frozen-policies.json`](policies/frozen-policies.json) records this hash.
The draft stays in the repository and still runs.

A command wrote v1. Nobody edited a chosen value by hand:

```powershell
uv run threshold-decision --policy policies/threshold-draft.json --output-dir output/draft-run
uv run threshold-freeze --simulated-run output/draft-run --output policies/threshold-v1.json --version v1 --public-file external/livecodebench/performances_generation.json
```

`threshold-freeze` reads the summary and the manifest of the simulated run of the draft.
It stops when the manifest names another policy hash, when the run is not simulated, or when the summary bytes differ from the manifest hash.
It applies two fixed rules to each benchmark section ([`threshold_rules.py`](src/benchmark_reference/threshold_rules.py)):

1. Interval method: a method passes the coverage study when it passes every cell, for each stratifier, stage size, and true score. The rule chooses the passing method with the smallest mean width.
2. Stratifier and stage-1 size: the rule takes the error-rate settings of the chosen method only. Of the settings that pass for both generators, it chooses the setting with the lowest expected token cost. The cost is the mean-estimate cost fraction under a uniform prior on the true scores 0.30 to 0.90 of the error-rate grid. Each generator has equal weight.

The candidates are the existing stratifiers only.
The Neyman selector (#61) is deferred and is not a candidate.
The rules read simulated results only.
With `--public-file`, the command checks the developer groups against the 28 public model names. The loader of #75 checks every row of the file, but it gives the command only the names. The command reads no grade.

| Benchmark     | Value                       | v1                                    | Simulated result that chose it                                                                                          |
| ------------- | --------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| LiveCodeBench | Interval method             | `stratified_wilson`                   | Passes 130 of 130 coverage cells with mean width 0.159. Pooled exact is next at 0.167.                                  |
| LiveCodeBench | Stratifier and stage-1 size | `difficulty_stratified`, 63 questions | Mean cost 0.4605 of a full run, both generators pass. `response_stratified` at 63 questions is next at 0.4703.          |
| AA-LCR        | Interval method             | `pooled_exact_hypergeometric`         | Passes 130 of 130 cells with mean width 0.283. Wilson is narrower (0.278), but it fails 1 cell.                         |
| AA-LCR        | Stratifier and stage-1 size | `metadata_stratified`, 30 questions   | Mean cost 0.6363 of a full run, both generators pass. `length_difficulty_stratified` at 30 questions is next at 0.6430. |

The cost of each generator alone gives the same four choices.
The AA-LCR probe grows from 20 to 30 questions.
Its new stratifier, `metadata_stratified`, does not use reference grades, so the simulation generator does not favor it.

A frozen file must hold two blocks beside its sections. The loader rejects a frozen file that lacks either block or any key in them:

- `protocol` holds every value of the real replays. The list below gives its parts.
  - The two stages, and the indifference zone: 0, with 0.02 as a secondary result.
  - The public-panel pin and the hash of the question mapping.
  - The grade rule: `pass@1` of 50 or more, with 100 as a secondary rule.
  - The settings of the unseen-model replay (#63) and of the random-probe baseline.
  - The reference-panel study (#77), with the developer group of each public model.
  - The pruned-set test (#80). Its interval method is the method of the LiveCodeBench section.
  - Every pass criterion, the stated comparisons with the simulated d95, and three disclosures.
- `selection` records the source run (draft hash, summary hash, manifest hash) and the candidates that each rule compared.

The loader re-applies the rules to the recorded candidates.
The result must agree with the recorded choice and with the section values, so a hand edit of a chosen value stops the loader.
The 1,055-question arm of #77 must use the LiveCodeBench stage-1 fraction, rounded up: 211 questions.

`threshold-freeze` never overwrites a policy file or a lock entry.
A later change must create a new version, for example `v2`.
`threshold-decision` refuses to write the results of a frozen policy into a folder that already holds them.

A run of `threshold-decision` with a frozen policy adds a "Frozen policy" section to the report.
The section shows each chosen value with the simulated result that chose it, each fixed value, the pass criteria, the stated comparisons, and the disclosures.
It also re-applies the rules to the coverage and error-rate results of the same run.
Those studies do not depend on the chosen values, so the rules must give the v1 values again.
The section states whether they do.

### Real replay

The real replay tests a frozen policy on the 28 public LiveCodeBench models (#63):

```powershell
uv run lcb-public fetch
uv run threshold-decision --policy policies/threshold-v1.json --real-grades --output-dir ../docs/data/task2-real-replay
```

The command takes every setting from the frozen policy.
It checks these points before it reads a public grade:

- The policy hash matches the committed lock file.
- The reference panel, the question mapping, and the public file match the hashes in the policy.
- The public model names match the developer groups of the policy.
- The `task2` folder has no uncommitted change, so the recorded commit is the code that ran.
- Git `HEAD` has no record of a replay of this policy, and no start marker exists in `output/`.

The replay runs one time.
A second run needs `--rerun-reason`, and the report states the reason.
Use it only for a code fault or to reproduce the result.

[`threshold_replay.py`](src/benchmark_reference/threshold_replay.py) makes the decisions with the functions of the two-stage rule.
The report gives the cost as tokens and as questions.
The cost mark uses the mean token estimate.
The indifference zone forgives a wrong decision only when the full-set score is closer to the threshold than the zone.
Each public model gets new subsets for its coverage check. Their seeds differ from the seeds of every other study.

| Output                  | Content                                                                                |
| ----------------------- | -------------------------------------------------------------------------------------- |
| `cells.csv`             | Each grade rule, probe kind, model, and threshold: outcomes, wrong decisions, and cost |
| `coverage.csv`          | Coverage of each model under each grade rule                                           |
| `models.csv`            | One row for each model: scores, pass@1 facts, and results under both grade rules       |
| `reference_holdout.csv` | Each decision of the secondary replay on the 3 reference models                        |
| `summary.json`          | Every number of the report                                                             |
| `report.md`             | The marks, the comparisons, the limits, the disclosures, and the provenance            |
| `manifest.json`         | The command, the commit, the input hashes, the code hashes, and the output hashes      |

The outputs hold derived values for each model. They hold no grade of one question.
The recorded replay of v1 is in [`docs/data/task2-real-replay`](../docs/data/task2-real-replay/report.md).
It passed the 3 pass criteria.

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
The [judge-noise measurement](#judge-noise-measurement) gives the judge noise on the saved answers.
The simulated grades have no judge noise, and the policy interval excludes it.
The report gives the measured values and this limit beside every AA-LCR result.
It reads them from `data/aa-lcr-judge-noise.json`.

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
The simulated grades have no judge noise. The [judge-noise measurement](#judge-noise-measurement) gives the noise on the saved answers.

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
- The band mean of the AA-LCR cost is 0.815 at 12 questions, 0.775 at 20, 0.670 at 30, 0.692 at 50, and 0.784 at 70. The 30-question probe is the cheapest tested size. Frozen policy v1 uses 30 questions for AA-LCR.
- Pooled exact and Bonferroni exact pass all 130 AA-LCR coverage cells; pooled exact has the lowest coverage `0.948`.
- Stratified Wilson fails 1 of 130 cells: `metadata_stratified`, 20 questions, true score `0.85`, coverage `0.933`.
- The bootstrap fails 79 of 130 cells, with the lowest coverage `0.013`. Most AA-LCR strata have one or two sampled questions at these sizes, and such a stratum adds no bootstrap width.

### Run the decision

```powershell
uv run threshold-decision --policy policies/threshold-draft.json --output-dir output/threshold-decision
```

The command runs every benchmark section of the policy file.
It writes one folder of tables for each benchmark and three shared files:

| File                              | Content                                                                                    |
| --------------------------------- | ------------------------------------------------------------------------------------------ |
| `<benchmark>/decisions.csv`       | One row per simulated model: true score, stage-1 result, decision, stage, and tokens used. |
| `<benchmark>/coverage.csv`        | One row per coverage cell and method: coverage, misses on each side, width.                |
| `<benchmark>/cost.csv`            | One row per cost stage size and true score: escalation rate and token cost.                |
| `<benchmark>/question_tokens.csv` | One row per question: its estimate and the counts of each reference model.                 |
| `summary.json`                    | For each benchmark: decision summary for each true score, coverage verdicts, and limits.   |
| `report.html`                     | Self-contained report with charts and tables, in light and dark modes.                     |
| `manifest.json`                   | Policy hash, input hashes for each benchmark, and output hashes.                           |

`<benchmark>` is `live_code_bench_v5` or `aa_lcr`.
The report starts with a side-by-side table of both benchmarks.
Each benchmark then has its own section with the same charts and tables.
Every AA-LCR chart and table has the measured judge noise and its limit beside it.

The command prints the manifest SHA-256.
Two runs with the same policy file give identical bytes.
`--workers` sets the number of processes for the cost and coverage studies.
The default is the number of CPUs.
The outputs are the same for every worker count.
`--panel-dir` sets the folder that holds the reference panels `lcb-reference-panel.json` and `aa-lcr-reference-panel.json`.
The default is `task2/data`.
`--data-root` sets the folder that holds `Part 1/predictions`.
The default is the `Evals` folder at the repository root.

## Judge-noise measurement

`aa-lcr-judge` measures how much an AA-LCR score changes when the judge grades the same answer again (issue [#76](https://github.com/sdv1708/ai-model-benchmark/issues/76)).
It sends each of the 300 saved answers to the judge 5 times. It generates no answer.

The run of 2026-11-23 is recorded in [`docs/data/task2-aa-lcr-judge-rerun`](../docs/data/task2-aa-lcr-judge-rerun/report.md).
It used the judge `Qwen/Qwen3-235B-A22B-Instruct-2507` on DeepInfra, at temperature `0.0`.
It made 1,500 requests. Each request gave a valid verdict, and the cost was $0.1413.

| Result                                        | gpt-oss-120b | kimi-k2.5 | minimax-m2.5 |
| --------------------------------------------- | -----------: | --------: | -----------: |
| Answers with unequal judgments                |     2 of 100 |  5 of 100 |     1 of 100 |
| Lowest to highest score across the 5 passes   | 0.52 to 0.53 | 0.71 to 0.73 | 0.65 to 0.66 |
| Full-set decision at 0.60 in each pass        |        NO GO |        GO |           GO |
| Mean stage-1 interval width of policy v1      |        0.305 |     0.292 |        0.294 |
| Saved score                                   |         0.48 |      0.66 |         0.64 |
| Majority score of the 5 judgments             |         0.52 |      0.73 |         0.66 |

- The judgments are not all equal for 8 of 300 answers (2.7%).
- No full-set decision at threshold 0.60 changes between passes. The largest score range is 0.02, which is 0.067 of the mean interval width (0.297).
- The majority agrees with the saved judgment for 287 of 300 answers (95.7%). All 13 changes are from INCORRECT to CORRECT, and each model score rises by 0.02 to 0.07.
- That shift is larger than the noise between passes. The run cannot give its cause: the saved reviews record no endpoint, no precision, no settings, and no prompt. The saved decisions at 0.60 do not change. A [control run](#cause-of-the-score-shift) tested the cause.
- The measured values hold for temperature `0.0` and one endpoint on one day.

### Cause of the score shift

The judge prompt explains most of the shift, by the decision rule that issue [#88](https://github.com/sdv1708/ai-model-benchmark/issues/88) fixed before the run.
The control run of 2026-11-24 (UTC) sent the 300 saved answers to the same judge 5 times, with the old one-word prompt.
It is recorded in [`docs/data/task2-aa-lcr-judge-one-word`](../docs/data/task2-aa-lcr-judge-one-word/report.md). It cost $0.0414.

10 of the 13 answers that changed in #76 are INCORRECT again with the old prompt. The rule needs 10 to 13 for "most".

| Grades (majority of 5 for each run) | gpt-oss-120b | kimi-k2.5 | minimax-m2.5 | Agreement with the saved grades |
| ----------------------------------- | -----------: | --------: | -----------: | ------------------------------: |
| Saved                               |         0.48 |      0.66 |         0.64 |                               - |
| One-word prompt                     |         0.49 |      0.66 |         0.65 |              296 of 300 (98.7%) |
| JSON prompt                         |         0.52 |      0.73 |         0.66 |              287 of 300 (95.7%) |

The decisions at 0.60 are the same for all three sets of grades, and for each pass.
The judgments of 5 of 300 answers are not all equal with the old prompt. They are unequal for 8 with the JSON prompt.

| Reference answer                   | Changed by the JSON prompt | Of these, INCORRECT again |
| ---------------------------------- | -------------------------: | ------------------------: |
| Decimal, for example `0.1` for 10% |                          5 |                         5 |
| Excel date number, `45444`         |                          1 |                         1 |
| List with a literal `\n`           |                          4 |                         1 |
| Other                              |                          3 |                         3 |

Four limits apply to this conclusion:

- **It is at the boundary:** 10 is the lowest count for "most". The single passes give 10, 9, 9, 10, and 10. A count of 9 gives "a part of the shift". The 13 answers come from 9 questions, so they are not independent.
- **It does not explain question 74:** the 3 answers that stay CORRECT are all from question 74, a list with a literal `\n`. The old prompt gives CORRECT there in 3, 5, and 5 of 5 judgments.
- **It also changes one other answer:** the old prompt gives INCORRECT for kimi-k2.5, question 55, in all 5 judgments. The saved grade is CORRECT.
- **It does not separate the causes:** one run on another day does not separate the prompt from the endpoint, the precision, and the date of the saved judgments.

This was the reasoning before the run:

- EvalScope v1.1.1 to v1.5.0 (7 releases read) send the same base prompt as the current adapter, with no JSON contract. They ask for one word and store `LLM judge: <raw reply>`.
- All 300 saved explanations are exactly `LLM judge: CORRECT` or `LLM judge: INCORRECT`. This fits those releases.
- The current adapter asks for `reasoning` before `verdict`. The judge can then find that `0.1` and 10% are equal.

An agent read the 13 changed answers. No human checked this reading.

| Reference answer                  | Answers | Changed | Unequal judgments |
| --------------------------------- | ------: | ------: | ----------------: |
| Decimal, for example `0.1` for 10% |      27 |       5 |                 4 |
| Excel date number, `45444`        |       3 |       1 |                 0 |
| List with a literal `\n`          |      24 |       4 |                 1 |
| Other                             |     246 |       3 |                 3 |

- In 12 of the 13 changed answers, the answer matches the reference. The other one (kimi-k2.5, question 23) gives $205 million, and the reference is $204 million.
- The new judge also makes errors. Seven answers equal the reference, but their majority is INCORRECT: question 59 (all 3 models), question 85 (gpt-oss-120b and kimi-k2.5), and question 93 (gpt-oss-120b and minimax-m2.5). Each one has a decimal reference.
- With those 7 answers as CORRECT, the decisions at 0.60 stay the same. The score of gpt-oss-120b is then 0.55.
- A consistent judge can repeat one error in every pass. Low judge noise does not show that the judge is correct.

### Run the judge again

The saved reviews name the judge `qwen-3-235b-a22b-instruct-2507`.
`estimate` refuses another judge unless `--allow-different-judge` is set.
The saved reviews hold no reference answers.
The command reads them from the pinned public AA-LCR v1.0 file and checks its SHA-256.

1. Write the estimate. This step makes no request.

   ```powershell
   uv run aa-lcr-judge estimate --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv --base-url <endpoint> --judge-model <model> --input-price <USD for 1M tokens> --output-price <USD for 1M tokens> --price-source <URL> --limit-usd <USD> --output ../docs/data/task2-aa-lcr-judge-estimate.json
   ```

2. The owner approves the estimate and its SHA-256 in a comment on issue #76. The `run` command checks only the form of the comment address.
3. Put the key in the environment variable `JUDGE_API_KEY`. Collect 5 judgments first, as a check of the endpoint.

   ```powershell
   uv run aa-lcr-judge run --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv --estimate ../docs/data/task2-aa-lcr-judge-estimate.json --run-dir output/judge-run --approval-url <comment URL> --max-requests 5
   ```

   Run the same command without `--max-requests` for the remaining judgments.

4. Write the report and the record of the threshold report.

   ```powershell
   uv run aa-lcr-judge report --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv --run-dir output/judge-run --output-dir ../docs/data/task2-aa-lcr-judge-rerun --record data/aa-lcr-judge-noise.json
   ```

The run takes the endpoint, the model, the prices, and the cost limit from the estimate file only.
It obeys these rules:

- Each judgment is one request with one user message. The text is the judge prompt of the EvalScope AA-LCR adapter, with no change.
- The settings are the EvalScope judge defaults: temperature `0.0` and at most `4096` output tokens. The run sends no seed.
- A reply outside the output contract is not a verdict. One run of the command sends at most 3 requests for it, and keeps every attempt.
- A reply that carries an error of the endpoint is not a verdict.
- A reply of another model, or a reply with a repeated response identifier, is not a verdict. It stops the run.
- The run stops before the next request could pass the cost limit. It counts a lost reply, a server fault, and a reply with no token count at the highest possible cost of the request.
- If the process stops during a request, the record does not hold the cost of that request. After such a stop, compare the account balance with the report.

The run writes the key to no file.
The client sends the key to the approved host only, because it follows no redirect.
The record of an HTTP error holds the status code and no server text.
A loopback judge gets no key and needs no approval. The tests use a scripted loopback judge.

| Output            | Content                                                                              |
| ----------------- | ------------------------------------------------------------------------------------ |
| `judgments.jsonl` | Every attempt: the reply, the verdict, the tokens, the returned model, and the time. |
| `answers.csv`     | The 5 grades, the majority, and the saved grade of each answer.                      |
| `scores.csv`      | The full-set score and the decision of each model in each pass.                      |
| `summary.json`    | Every measured value.                                                                |
| `report.md`       | The result, the judge and its settings, the cost, and the limits.                    |
| `run.json`        | The estimate and the approval comment.                                               |

### Test the old judge prompt

Issue [#88](https://github.com/sdv1708/ai-model-benchmark/issues/88) tested the [cause of the score shift](#cause-of-the-score-shift).
The control run sends the same 300 saved answers to the same judge, at the same endpoint, 5 times each.
It uses the old one-word prompt of EvalScope `v1.4.2`.
The run is recorded in [`docs/data/task2-aa-lcr-judge-one-word`](../docs/data/task2-aa-lcr-judge-one-word/report.md).

| Item                  | JSON prompt (#76)                     | One-word prompt (#88)                                                                   |
| --------------------- | ------------------------------------- | --------------------------------------------------------------------------------------- |
| Prompt                | Base prompt and JSON contract         | Base prompt only                                                                        |
| Verdict               | The `verdict` of the JSON object      | CORRECT when the reply matches `\bCORRECT\b` in any case, else INCORRECT                |
| No verdict            | A reply outside the contract          | An empty reply. EvalScope grades it as INCORRECT, and this run sends the request again  |
| Maximum output tokens | `4096`                                | `1024`                                                                                  |

The issue fixed the decision rule before the run.
The rule covers the 13 answers that changed in #76:

| Answers of the 13 that are INCORRECT again | Conclusion                             |
| ------------------------------------------ | -------------------------------------- |
| 10 to 13                                   | The prompt explains most of the shift  |
| 4 to 9                                     | The prompt explains a part of the shift |
| 0 to 3                                     | The prompt does not explain the shift  |

The commands are the same, with these differences:

1. Compare the old prompt and the old parser with the EvalScope source. Put the two files of `v1.4.2` in one folder, with their repository paths. The tool checks the SHA-256 of each file.

   ```powershell
   uv run python tools/audit_old_judge_prompt.py --evalscope <folder> --data-root ../Evals --panel data/aa-lcr-reference-panel.json --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv
   ```

2. Add `--prompt one-word` to `estimate`. `estimate` and `run` refuse another judge or another endpoint than the run of #76. The owner approves the estimate in a comment on issue #88. The `run` command checks only the form of the comment address.

   ```powershell
   uv run aa-lcr-judge estimate --prompt one-word --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv --base-url https://api.deepinfra.com/v1/openai --judge-model Qwen/Qwen3-235B-A22B-Instruct-2507 --input-price <USD for 1M tokens> --output-price <USD for 1M tokens> --price-source <URL> --limit-usd <USD> --output ../docs/data/task2-aa-lcr-judge-one-word-estimate.json
   ```

3. Use `run` with the new estimate and a new run folder, `output/judge-one-word-run`.
4. Use `compare` in place of `report`.

   ```powershell
   uv run aa-lcr-judge compare --source-csv output/aa-lcr-source/AA-LCR_Dataset.csv --run-dir output/judge-one-word-run --output-dir ../docs/data/task2-aa-lcr-judge-one-word
   ```

`compare` reads the JSON run from `docs/data/task2-aa-lcr-judge-rerun` and changes no file of it.
It applies the rule and compares the three sets of grades for each model and for each form of the reference answer.
One run on another day does not separate the prompt from the endpoint, the precision, and the date of the saved judgments.

### Judge noise and the interval of policy v1

The report of #76 compares the score range across passes with the stage-1 interval width of policy v1 (60 probes: 3 models and 20 seeds).
Policy v1 does not change. Its interval excludes judge noise.

## Public LiveCodeBench results

LiveCodeBench publishes one `pass@1` value for each model and question.
None of these models is in the reference panel.
The 315 reference-panel questions come from the same public dataset, so the public results give a test on real models that the selector never saw.
This package prepares that data path only. It gives and prints no grade.

| Fact (read on 10 November 2026) | Value                                                              |
| ------------------------------- | ------------------------------------------------------------------ |
| Source                          | `https://livecodebench.github.io/performances_generation.json`     |
| Size                            | 6,950,346 bytes                                                    |
| SHA-256 (the pin)               | `17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1` |
| Shape                           | 28 models and 1,055 questions, 29,540 rows, no missing cell        |
| Row fields                      | `question_id`, `model`, `date`, `difficulty`, `pass@1`, `platform` |
| `pass@1`                        | A number from 0 to 100 for each model and question                 |
| License                         | The source repository states no license                            |

The raw file is not committed, because its source states no license.
`uv run lcb-public fetch` downloads it to `task2/external/livecodebench/`, and Git ignores that folder.
The command stops and writes nothing when the SHA-256 differs from the pin.

The model `release_date` field is not a release date: 19 of 28 models share one placeholder value.
No analysis can use it, and the loader does not give it.
The row field `date` is the question date, in Unix milliseconds.

`public_lcb.py` has two loaders:

- `load_public_results` gives the question identifiers, dates, difficulty labels, platforms, and model names, with no restriction.
- `load_public_grades` gives the raw `pass@1` values, 0 to 100. It gives them only after the frozen-policy check of the real-grade replay passes. The check runs before the file is opened. The draft policy is refused.

The grade rule, for example "pass at 50 or more", comes from the frozen policy, not from the loader.
Both loaders check the pin and validate every row.
They reject these faults:

- A missing cell.
- A duplicate model and question pair, or a duplicate model.
- A `pass@1` value outside 0 to 100.
- A model count other than 28, or a question count other than 1,055.

Their error messages name the model and the question, never a `pass@1` value.

[`data/lcb-public-mapping.json`](data/lcb-public-mapping.json) joins the 315 reference-panel questions to public question identifiers.
Each entry holds the panel index, the question fingerprint, and the question identifier only.
The header records the pinned dataset, the SHA-256 of the reference panel, and the pin of the public file.
`uv run --extra public-source lcb-public map` rebuilds the mapping.
It uses the fingerprint rule and the pinned dataset revision of the source verification (`marianna13/livecodebench_code_generation_lite_parquet` at `e70df962`).
It must find exactly 315 unique matches, each in the public results with the same platform.
Otherwise it stops and names each question that fails.
The committed mapping has 315 unique matches.

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
`tools/audit_judge_prompt.py` requires the same checkout. It compares the judge prompt and the reply parser of this package with the adapter, on all 300 saved answers.
`tools/audit_old_judge_prompt.py` does the same for the [old one-word prompt](#test-the-old-judge-prompt). It needs two source files of EvalScope `v1.4.2`, and no installation of EvalScope.
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
