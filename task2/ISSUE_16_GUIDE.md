# AA-LCR compression: from the simple idea to the statistical details

Issue [#16](https://github.com/sdv1708/ai-model-quality-challenge/issues/16) asks
whether a smaller long-context benchmark can preserve the conclusions of its full
100-question version. Long inputs make evaluations expensive. A useful shortcut
needs to preserve model scores and ordering, rather than merely produce a cheap score.

There is a second problem: another LLM grades these answers. Changing the selected
questions and getting different grades from that judge are different sources of
uncertainty. The supplied files let us investigate the first. They contain only
one judgment per answer, so they cannot identify the second.

## Reproduce the study

From `task2/`, with Python 3.12 and uv:

```powershell
uv sync --locked
uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-pruning
uv run python tools/audit_aa_lcr.py --data-root ../Evals --reports output/aa-lcr-pruning
```

The equivalent module command is `uv run python -m benchmark_reference.long_context_cli`.
It takes the same arguments. No inference, live judging, API key, or internet lookup
is needed. Only the six AA-LCR prediction/review files are read and fingerprinted;
the existing whole-tree inventory contract is still enforced.

Defaults retain **10, 20, 30, 50, or 100 questions**, using seeds **0 through 19**.
The ratio means fraction **retained**, not fraction removed. Counts are
`ceil(N * keep_ratio)`. Two candidates and three explicitly marked comparison
baselines give 1,500 score runs and 1,500 independent-pair runs.

For a small run with illustrative decision thresholds:

```powershell
uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-demo --keep-ratios 0.5 1 --seeds 0 1 2 --thresholds 0.5 0.6 0.7 --flip-counts 0 1 2 5 10
```

Those thresholds and flip budgets are examples, not customer requirements or
estimated judge error rates. Duplicate settings, invalid metadata/grades, and
budgets that cannot cover every occupied stratum fail before report publication.

## What the data actually contains

The three recorded full scores are **48%, 66%, 64%** for gpt-oss-120b,
kimi-k2.5, and minimax-m2.5. There are 300 binary recorded grades.

The 100 shared questions have benchmark `input_tokens` between **71,691 and
114,563**, totaling **9,524,828** tokens per complete question pool. There are
**30 distinct canonical document sets** and **173 unique source URLs**.
Question text, source URLs and benchmark token counts agree across models.
Additional model-specific metadata is ignored.

`sample_metadata.input_tokens` is the length feature. It is not
`model_output.usage.input_tokens`, which varies with model tokenization and prompt
accounting. Output tokens, generated answers, reasoning, latency, and target grades
are unavailable to candidate fitting. Question text is checked for cross-model
identity but is not converted into invented topic labels. Source URLs are parsed
as semicolon-delimited sets, trimmed, deduplicated and sorted; they are not fetched.

## Two defensible candidates

`metadata_stratified` crosses three input-length bands with three document-count
bands. Long-context cost and difficulty can change with the amount of text and
the number of documents that must be combined. Covering both protects against
accidentally keeping only shorter or simpler document bundles. Its features require
no model outcomes, making it the cleaner option for a future model.

`length_difficulty_stratified` crosses the same length bands with the number of
historical reference models that passed. It preserves a mixture of historical
easy, intermediate, and difficult questions at different lengths. The underlying
hypothesis is that some reasoning difficulty transfers between model families;
that assumption is explicitly stress-tested by withholding model outcomes.

Bands use empirical **midrank thirds**: count values below a value plus half of
those equal to it, divide by population size, and map to thirds. Equal values stay
together, so bands need not contain exactly equal counts. No sample IDs break
feature ties. Each candidate has at most nine groups with two reference models.
The historical candidate has at most six with one reference in the pair study.

Every occupied group gets one slot. Remaining slots go to the largest deficit
from proportional allocation, with lexical group ties. SHA-256 priorities choose
members without replacement within groups, reproducibly for each seed. This
reuses the established `lcb-pruning-v1:seed:index` priority salt; the AA-LCR
algorithm and features have their own version in the manifest. Different budgets
need not select nested subsets. No model name or seed is tuned to target fidelity.

Uniform random, easiest-only, and hardest-only appear only as **comparison baselines**.
The candidate API rejects them. Randomness within structured strata is not a
uniform random selection strategy over the entire benchmark.

## Why the weights matter

Small groups may be oversampled to preserve coverage. If one selected question
represents 20 of 100 questions, its contribution to the full score is 0.20,
not necessarily `1 / selected_count`.

For group h, with N_h questions and n_h selected questions, each selected grade
gets weight `N_h / (N * n_h)`. The score is:

`estimated_score = sum_h (N_h / N) * mean(selected grades in h)`.

The reports include both weighted estimates and raw subset means. The weighted
estimate is design-unbiased under uniform sampling within the fixed groups;
it need not be closer for every seed. Deterministic hash priorities approximate
this probability design; their use is an assumption, not a source of exact randomization.

## What is held out, and what that proves

The score study withholds one model **before** fitting historical groups. It uses
the same selected questions and weights to score all three models in that fold.
Only the withheld model's error is transfer evidence; the other two scores are
in-sample diagnostics. Three-model ordering in this study is reference-assisted.

The stricter pair study withholds **both** models being compared before fitting.
Only one reference remains. The pair's scores use one common subset, and paired
differences cancel shared successes/failures. Pair order agrees only when the
sign, including ties, matches the full comparison. No ranking combines estimates
from different selected subsets. Numerical differences within 1e-12 count as ties.

These are fixed-pool model-transfer checks, not document-held-out or future-task
validation. Multiple questions share document sets. A future corpus should be
evaluated separately, ideally holding out whole document sets and model families.
Metadata-only selections repeat across model folds for the same seed: the pooled
60 rows do not constitute 60 independent selections. Seed summaries are descriptive;
they are not standard errors from independent new benchmarks.

## Measured fidelity

Pooled held-out mean absolute error, in percentage points:

| Questions retained | Length + difficulty | Length + document count | Uniform comparison |
| ------------------ | ------------------: | ----------------------: | -----------------: |
| 10                 |               10.73 |                   11.91 |              10.63 |
| 20                 |                7.50 |                    7.47 |               6.48 |
| 30                 |                5.16 |                    4.94 |               4.73 |
| 50                 |                2.90 |                    3.27 |               3.77 |
| 100                |                0.00 |                    0.00 |               0.00 |

At 50 questions, exact three-model ordering agrees in **66.7% / 70.0%** of runs
for the historical / metadata candidates. Independently held-out pair ordering
agrees in **88.3% / 90.0%**, versus **85.0%** for the uniform comparison.
These numbers answer different questions; they should not be conflated.

The candidates do not dominate the uniform comparison at every budget or metric.
At half retention, mean nominal 95% score-interval widths are **47.75 / 48.48
percentage points**. Both candidates' pair intervals are inconclusive in **all**
half-retention runs; their mean pair-interval widths are **84.47 / 87.95 points**.
Coverage consumes precision in a small pool. Uniform comparison has narrower
intervals and some decisive pair results, but is forbidden as the final strategy.

No smallest sufficient pruning ratio is certified here. No customer tolerance has
been supplied, judge noise is unidentified, and preserving a two-point model gap
is considerably harder than estimating a rough score. Half retention is a useful
experimental point, not a production recommendation.

## What the intervals mean

The shared uncertainty module inverts finite-population hypergeometric tails using
exact integer comparisons. Bonferroni allocations across groups yield conservative
score intervals. Paired intervals bound the two directional discordance counts
with additional failure-budget allocation; they need no independence between
models on the same question. The auditor independently uses linear tail inversion,
while production uses binary search.

These intervals cover a **fixed table of recorded grades under the stated sampling
design**. They do not cover future documents, future generations, model families,
or repeated LLM judgments. Coverage is per fixed run, not simultaneous after
searching over methods, ratios and seeds. Census intervals collapse to the stored
score because every stored grade is observed. This does not establish judge correctness.

Threshold decisions use the supplied score threshold: interval entirely at/above
it means GO, entirely below means NO GO, and overlap means inconclusive. Both
abstention and false decisions are reported. Top-k baselines lack design intervals
below census and therefore abstain. Thresholds are never inferred from this panel.

## Judge noise: what can and cannot be quantified

All 300 reviews identify the judge as `qwen-3-235b-a22b-instruct-2507`, strategy
`auto`. There are **zero answers with repeat reviews**. Judge variance and flip
rate are therefore **null**, not zero. Cross-model disagreement compares different
answers, so it cannot estimate within-answer judge nondeterminism. Repeating a
subset seed reuses exactly the same grades and supplies no additional judge evidence.

We can quantify conditional sensitivity. If at most b stored grades per model
are changed, its full recorded score can move by at most `b / 100`. For a fixed
selected subset, each selected grade carries its sampling weight; a single changed
grade may move a weighted estimate by much more than one percentage point.
`judge_noise.json` computes exact extrema by flipping the largest weighted selected
successes downward or failures upward. It allows the entire pool flip budget to
land on selected questions. Reference features and selection remain frozen; it
does not quantify how rejudging reference models would change fitted groups.

The report also widens each finite-pool score interval by `b / N`, clipped to
0..1. These bounds retain the original design coverage **conditional on** a fixed
latent grade table differing in at most b cells. They do not give a probability
that this assumption is true or correct systematic judge bias.

The two-point 66%-versus-64% full-score gap needs only **two total changed grade
cells across the pair to tie, or three to reverse**. The 18-point and 16-point gaps
need respectively 18/19 and 16/17 total changes to tie/reverse. These are worst-case
thresholds, not predictions of how often a ranking changes. Ties have a separate
one-flip tie-breaking field rather than an invented reversal direction.

To estimate judge randomness, freeze each answer, question, rubric and judge
version, obtain at least three independent judgments per answer, retain every
replicate, and report within-answer disagreement and repeat-score/rank variation.
Resample document sets and judge replicates separately. Human adjudication is
needed to investigate systematic bias; repeated agreement alone does not establish truth.

## Artifacts and engineering safeguards

The usual eight study artifacts are joined by `features.json`, `coverage.csv`, and
`judge_noise.json`. Together they retain grades and source lines, selections and
weights, fold membership, full/estimated scores, tie-aware ordering, intervals,
optional decisions, seed stability, source-set/URL coverage and input-token totals.
Input-token fraction is a cost proxy, not measured latency or dollar savings.

The manifest hashes the six raw inputs, implementation sources (normalized LF),
and every other output (exact bytes). Reports serialize before publication, protect
input paths including destination symlinks, replace individual files atomically,
and publish the manifest last. This is not a transaction across eleven files:
check exit status and output hashes, use one writer, and keep source data fixed.

The independent auditor reopens raw grades, verifies provenance, rebuilds metadata
bands and strata independently, reconstructs weighted estimates and exact score/
pair intervals, and checks the full-score flip tipping counts. Tests additionally
exhaustively compare flip envelopes against all changed-label subsets in a small
unequal-weight example. No tests use the shipped answers as their expected truth.

Compact measured summaries and the original run manifest live under `docs/data/`.
The noise summary is explicitly an extract with the full report's SHA-256;
regenerate full selections and per-run sensitivity locally. This experiment
implements issue #16's offline evaluation. The separately required pinned
evalscope integration remains later project work.
