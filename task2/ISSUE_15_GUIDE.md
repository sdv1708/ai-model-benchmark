# Issue #15: research, implementation, and interview defense

## The problem and the honest result

We want fewer coding tasks to approximate the full supplied benchmark's mean
recorded pass score. We also measure whether pruning preserves model ordering.
These are different objectives: a small absolute error can reverse two close models.

This ticket implements and evaluates candidates. It does not choose a customer
acceptance threshold, certify an operating point, or integrate into evalscope.
The latter remains a separate hard requirement of the overall challenge.

The full reference means are 241/315 = 76.51% for gpt-oss-120b, 198/315 = 62.86%
for kimi-k2.5, and 195/315 = 61.90% for minimax-m2.5. The latter two differ by only
3 tasks, or 0.952 percentage points. At half the benchmark, our candidates' average
held-out errors are roughly 1.5–1.6 points. That is useful evidence about score
approximation, but cannot justify reliably ranking such a close pair.

## Research and what we actually adopted

[Statistics Canada's stratified-sampling treatment](https://www150.statcan.gc.ca/n1/edu/power-pouvoir/ch13/prob/5214899-eng.htm)
describes dividing the population into disjoint strata and sampling independently
within them. Its [allocation paper](https://www150.statcan.gc.ca/n1/pub/12-001-x/2015002/article/14249/02-eng.htm)
gives the population-total estimator as the sum of each stratum's population size
times its sample mean. Dividing by total population size yields our weighted mean.
We use near-proportional allocation with a minimum of one per occupied group.
We do not claim this integer rule is Neyman-optimal allocation.

[tinyBenchmarks, Polo et al. (ICML 2024)](https://arxiv.org/abs/2402.14992)
is relevant evidence that benchmark compression deserves study. Its reported
results concern its own benchmarks and estimation methods. We borrow the question,
not its claimed accuracy: we do not reproduce its learned IRT estimator, train a
latent ability model, or assume its compression results transfer to these 315 tasks.

[Wei, Iyer, and Bilmes (ICML 2015)](https://proceedings.mlr.press/v37/wei15.html)
provide representative-selection prior art using submodularity. We considered
representative/diversity objectives but did not implement a facility-location or
embedding selector. Here two historical models provide at most four binary behavior
patterns; explicit strata are simpler and auditable. A representative objective's
coverage guarantee would not itself establish accuracy of the benchmark mean.

[SciPy's Kendall tau documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kendalltau.html)
supplies the tie-adjusted tau-b definition used by our small standard-library
implementation. SciPy is not a runtime dependency. We test reversal and tie examples
with known numerical answers.

## Why these features are available for a future model

Historical models have already been run over the full task pool. Their per-task
binary grades can therefore be stored before evaluating a new model. The new model
only needs to answer the selected tasks. Fitting does require that historical pool;
this is not a cold-start method when no prior evaluations exist.

The shipped coding metadata is empty. The stored `messages` are assistant responses
and reasoning, not original user problem prompts. We deliberately do not embed or
classify that text as if it were model-independent problem content. No task IDs,
model names, or manually chosen examples are treated as predictors.

Historical outcomes define *behavioral coverage*, not semantic algorithm/topic
coverage. Tasks sharing a pass pattern are redundant with respect to those few
reference outcomes, not necessarily equivalent for a new model. Index correspondence
across models is assumed from the supplied contract; absent original problem IDs
or prompts, we cannot independently prove semantic identity for every task.

## The two candidates

For each task i, construct its pass vector from reference models only. With two
references, the possible vectors are 00, 01, 10, 11.

`difficulty_stratified` groups by number of reference passes: 0, 1, or 2.
Both disagreement directions share the middle stratum. This samples the whole
historical difficulty range rather than taking the easiest or hardest tail.

`response_stratified` uses the complete vector. It distinguishes a task only A
solves from one only B solves. This preserves historical disagreement diversity
while avoiding concentration on a large redundant pass/fail group.

We call both nontrivial because their allocation deliberately uses coverage
structure. Choosing repeatable random-like representatives within a designed
stratification is not the forbidden uniform-random selector over the whole pool.
With degenerate reference behavior there may be only one occupied stratum; then
they reduce to the uniform comparison. That is an evidence limitation, not a reason
to invent artificial groups or claim an advantage that cannot exist.

## Budget, allocation, and stable selection

The public input is a retention fraction r in (0,1]; k = ceil(N*r).
For 315 tasks, our fractions 0.1/0.2/0.3/0.5/1 retain 32/63/95/158/315 tasks.
Always say "retain" when explaining this: some tools use prune ratio to mean removed.

Allocate one slot to every occupied stratum. Repeatedly give the next slot to the
non-full stratum with greatest deficit from its ideal proportional allocation.
The comparison uses integers k*N_h - n_h*N to avoid floating tie ambiguity; group
labels break ties lexically. This is deterministic and respects stratum capacity.
If k is smaller than the number of occupied strata, fail explicitly.

Within each stratum, rank tasks by SHA-256 of `lcb-pruning-v1:seed:index` and take
the required prefix without replacement. This gives portable repeatable
pseudorandom priorities, independent of input row/model order and global RNG state.
Seeds 0..19 were fixed as the default panel, not searched for a favorable result.
The same priority scheme is used for all methods' random tie-breaking.
Different budgets are not guaranteed to produce nested subsets.

Return selected tasks in index order, each with its stratum, N_h, n_h, and weight.
Every selected ID occurs once. Inspect these records in `selections.jsonl`.

## Why the score needs weights

The full score is a population mean, not "accuracy on any interesting problems."
For each selected task in stratum h, assign w_i = N_h / (N*n_h). Then:

    estimated full mean = sum_i w_i * y_i
                        = sum_h (N_h/N) * selected_mean_h

The weights sum to one. Under uniform sampling within fixed strata, each stratum's
sample mean is unbiased for its finite-population mean. This motivates the estimator;
fixed pseudorandom seeds do not guarantee that any one subset is accurate.

Worked example: eight tasks form groups of sizes 1, 1, 1, 5. A budget of four
takes one task from each group. Its weights are 1/8, 1/8, 1/8, 5/8. If grades are
0, 1, 0, 1 and the last group is all successful, the weighted estimate is 6/8 = 75%.
The unweighted subset mean is 2/4 = 50%. Equal averaging would badly overrepresent
rare groups. This literal example is in the tests.

We report raw subset means alongside weighted estimates. This is essential for
the later integration: an evalscope adapter that only returns IDs and uses its
ordinary unweighted mean will not reproduce these weighted results.

## How leave-one-model-out prevents leakage

For each held-out model, remove it from the reference-score mapping before feature
construction, group allocation, hashing, or selection. Fit on the remaining two,
freeze the selected IDs and weights, then read held-out grades to measure error.
Changing every held-out grade must leave that fold's selection unchanged; a test
checks exactly that. Changes to it may affect *other* folds, where it is a reference.

Each method uses 5 ratios x 20 seeds x 3 held-out models = 300 runs. Two candidates
plus three baselines produce 1,500 runs. Baselines are uniform random, easiest-only,
and hardest-only, using only reference grades for difficulty. They are marked
`comparison_baseline`; the candidate API rejects their names.

All three models are scored on the *same selected subset within each fold* for
ordering comparisons. Two were used to fit the selector, so that ranking is
reference-assisted, not an independent three-unseen-model experiment. In particular,
response strata make each reference grade constant within a stratum, reproducing
reference means exactly. Never sell that as evidence of target generalization.
We do not stitch held-out scores from different subsets into an ordinary leaderboard.

## What each metric means

Held-out absolute error is |estimated mean - full mean|. MAE averages it over
seeds, and the pooled row averages over all three held-out folds. RMSE penalizes
large misses; signed bias reveals systematic direction; maximum error exposes
bad seeds. All machine-readable scores/errors use 0..1 units: multiply by 100
for percentage points. Per-fold error standard deviation describes seed dispersion;
pooled standard deviation includes differences between models as well.

Pair agreement counts preserved strict comparisons plus preserved ties, divided
by the number of model pairs. An introduced tie is not a preserved strict order.
Kendall tau-b is (C-D)/sqrt((C+D+T_full)*(C+D+T_subset)), where C/D are concordant/
discordant counts and the T terms are ties in one ranking only. Joint ties enter
pair agreement but not that denominator. An all-tied ranking has undefined tau-b,
reported as JSON null rather than misleadingly as 1. Exact order requires every
pair relation to match; numerical differences <=1e-12 are treated as ties.

Jaccard stability is |A intersection B| / |A union B|, averaged over seed pairs
within the same fold. Different IDs need not mean different quality; stability
and fidelity answer separate questions. These are descriptive seed measurements,
not confidence intervals, generation variance, or a probability of future success.

## Measured results

Pooled across 60 runs per method/ratio (3 held-out models x 20 seeds):

| Retained | Tasks | Difficulty MAE, pp | Response MAE, pp | Uniform MAE, pp |
| --- | ---: | ---: | ---: | ---: |
| 10% | 32 | 4.94 | 5.38 | 7.41 |
| 20% | 63 | 3.38 | 3.41 | 3.96 |
| 30% | 95 | 2.50 | 2.64 | 2.77 |
| 50% | 158 | 1.53 | 1.61 | 1.78 |
| 100% | 315 | 0.00 | 0.00 | 0.00 |

At 50% retention, worst errors are 3.73 pp for difficulty and 3.38 pp for response.
Exact ordering fractions are 43.3% and 63.3%, respectively (uniform: 40.0%).
At 10%, worst errors remain 15.50/15.14 pp. Easiest/hardest baselines have much
larger score bias: half-retention MAEs are about 23.48/23.38 pp.

Response-pattern coverage improves ordering on this panel but does not win mean
score error. More detailed strata do not automatically improve transfer with only
two references. Ratios need not show monotonic ranking fidelity across a finite
seed panel, especially when the close pair's ordering is unstable.

The defensible conclusion is that both candidates improve score approximation
relative to uniform on this measured panel, while aggressive pruning is risky and
ordering remains weak. These are empirical comparisons, not statistical significance
claims. We have not predeclared customer tolerances or proved a minimum sufficient
subset. Three leave-one-out folds are a useful stress test, not a model population.

## Code map and replay

`pruning.py` owns candidate/baseline selection. `experiments.py` owns held-out
evaluation and ordering. `pruning_cli.py` joins the existing validated coding
input pipeline to the experiment. `pruning_reporting.py` publishes audit artifacts.
The reference pipeline continues to support issue #14 unchanged.

Run the commands in [README.md](README.md). `tools/audit_lcb.py` independently
reads raw reviews and saved selections with the standard library; it imports none
of the pipeline. It verifies input/output/implementation hashes, normalized grades,
selection uniqueness, weight totals, all estimated means, and held-out MAE/maxima.
It is a verification tool, so run it with normal Python (without `-O`, which disables
assertions). The machine-readable results include both input and implementation
fingerprints. Byte-identical reruns are verified for all five artifacts.
Source fingerprints normalize CRLF to LF so Git's line-ending settings do not
change the implementation identity; data and report fingerprints use exact bytes.

## Interview questions to rehearse

1. **Why isn't stratified sampling just forbidden random sampling?** The design
   constrains coverage across historical difficulty/behavior groups; random-like
   priorities select representatives within them. Whole-population uniform sampling
   is a separate comparison, and a one-stratum degeneration is disclosed.
2. **How can you select for an unseen model using model grades?** Use historical
   models' already available grades. The unseen model's outcomes are not fit inputs.
3. **Isn't fitting on two models fragile?** Yes. With binary outcomes, two references
   offer very coarse structure. We quantify transfer and avoid universal claims.
4. **Why no prompt embeddings?** The artifacts do not supply original prompts.
   Assistant reasoning is not a defensible substitute for model-independent input.
5. **What prevents score bias?** Population weights correct disproportionate group
   allocation. They do not remove uncertainty within a sampled group.
6. **Why don't good score errors guarantee correct rankings?** The close model gap
   is smaller than typical subset error. A coarse ranking coefficient can hide that.
7. **What would you change with more evidence?** Add independently verified problem
   IDs/prompts and semantic/topic features, a broader historical model panel, and
   genuinely untouched models. Define score/decision tolerances before choosing a
   budget, quantify design uncertainty, and use full evaluation for ambiguous cases.
8. **Is this ready inside evalscope?** This ticket is the offline candidate study.
   The later adapter must pin upstream, preserve ID correspondence, freeze reference
   features, support the chosen scoring weights, and validate its real CLI behavior.
