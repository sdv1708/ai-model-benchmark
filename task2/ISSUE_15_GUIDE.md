# Issue #15: research, implementation, and interview defense

## The problem and the honest result

We want fewer coding tasks to approximate the full supplied benchmark's mean
recorded pass score. We also measure whether pruning preserves model ordering.
These are different objectives: a small absolute error can reverse two close models.

This ticket implements and evaluates candidates. It does not choose a customer
acceptance threshold, certify an operating point, or integrate into evalscope.
The latter remains a separate hard requirement of the overall challenge.

The substantial second revision adds exact finite-pool uncertainty, threshold
abstention, and pair-transfer evaluation excluding *both* compared models from
selection. There are now 3,000 evaluations per default run. These additions
strengthen the evidence without treating more algorithms as a substitute for
validating the existing ones.

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

For uncertainty, the [R distribution reference](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/Hypergeometric.html)
defines sampling without replacement and its hypergeometric probabilities. The
[samplingbook implementation note](https://stat.ethz.ch/CRAN/web/packages/samplingbook/vignettes/Sprop-remarks.html)
explains exact interval construction through tail inversion and the weakness of
normal plug-in intervals near zero/one. We implement equal-tail inversion over
integer population counts, followed by a union bound across strata. This is
finite-population inference; a binomial model would ignore the without-replacement
design and a Wald interval can falsely collapse after all-success/all-failure draws.

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

## A stronger test: hold out both compared models

The original common-subset ranking includes two fitted reference models. We now
also hold out each model pair simultaneously, fit on the remaining reference pool,
then evaluate both held-out models on a shared subset. A perturbation test changes
both targets and checks that pair selection remains identical. With three shipped
models this leaves one reference, so both candidates reduce to the same two strata.
This is an honest limit on feature diversity, not two independent pieces of evidence.

The pair protocol adds 3 pairs x 5 methods x 5 budgets x 20 seeds = 1,500 runs.
Its primary point metric is error in the paired difference, not error in fitted
reference scores. Ordering agreement is measured only between these two excluded
models. It also reports interval coverage, width, decisive fraction and wrong-decisive
fraction. A correct forced point ranking and a statistically decisive ranking are
deliberately separate measurements.

## Exact intervals and why abstention matters

Within group h, observe x successes in n_h sampled tasks out of N_h total. For a
hypothesized full-group success count K, X follows Hypergeometric(N_h,K,n_h).
Retain feasible integer K values whose two tail probabilities are each at least
alpha_h/2. Binary search locates the first/last retained counts; binomial
coefficients and rational comparisons make the tail acceptance decisions exact.
The failure budget is split across groups: alpha_h = alpha/H. Adding group lower
and upper success counts and dividing by N gives a conservative full-score interval.
No independence between group confidence events is required for the union bound.

The endpoint convention matters for discrete data. For N=50,n=10,x=3 at 95%, our
inclusive non-rejected counts are [5,31]. K=4 has an upper-tail probability of
about .021754; K=32 has a lower-tail probability about .017635; both are rejected
against .025. Some packages, including samplingbook's illustrated result, expand
outward to [4,32]. Both are conservative conventions; we document ours rather than
claiming identical package outputs. The independent auditor checks [5,31] using a
linear scan instead of the production binary search.

At N=100,n=50,x=0 our interval is [0,.05]. An observed zero-variance sample therefore
does not imply that every unobserved task also fails. At a census the interval
collapses to the exact known score. Tests exhaust all binary-grade placements on
small finite populations, including stratification, and verify nominal coverage.
Rational failure budgets also avoid rounding a very high confidence level to 100%
when splitting the tail probability.

"Exact" describes the finite hypergeometric inversion, conditional on simple
random sampling without replacement inside groups. Fixed deterministic hash seeds
approximate uniform priorities; observed coverage over twenty seeds does not prove
the probability assumption. Intervals concern this fixed benchmark and fixed target
grades, not future questions, generation randomness, or an unseen family of models.
They are not simultaneous guarantees over searching the entire budget/method/seed
curve. Easiest/hardest do not meet the probability-design assumptions and receive
no interval below full retention; their null values are never counted as covered.

For two held-out models, use the paired task outcomes directly. Define P_i=1 when
A passes and B fails, and M_i=1 for the reverse. Then the mean score difference is
mean(P)-mean(M). Both-pass and both-fail tasks cancel. Apply exact group intervals
to these two directional discordance populations, sharing the failure budget over
2H events; subtract [L_P,U_P] and [L_M,U_M] to get [L_P-U_M,U_P-L_M]. This uses no
independence assumption between the models or discordance events. It is generally
more informative than subtracting separate model-score intervals, but can remain
conservative. In a tested N=100,n=50 example with identical observed model outcomes,
the paired interval is [-.06,.06], rather than the much wider independent-score
subtraction; it still permits disagreement on unobserved tasks.

Thresholds are optional CLI inputs, not inferred customer requirements. A full
mean >= threshold is GO. A lower confidence bound >= threshold supports GO; an
upper bound < threshold supports NO GO; otherwise return inconclusive. Report
decisive fraction together with false GO/NO GO fractions (all use the full run count
as denominator), so abstaining on everything cannot masquerade as high accuracy.
The CSV also reports the forced point-estimate decision agreement for comparison.
For a fixed interval, all threshold decisions share its coverage event; searching
for favorable methods or budgets is a separate multiple-comparison problem.

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
The new hypergeometric intervals are reported separately from this descriptive
seed spread; they answer a different question under explicit sampling assumptions.

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

The stricter pair-transfer study at half retention gives 86.7% point-order agreement
and 1.99 pp error in paired differences for both candidates. Their paired nominal
95% intervals cover the recorded truth in all 60 runs, but are decisive in only
38.3%; no decisive error is observed. Uniform comparison has 80.0% agreement,
1.89 pp difference error, and 66.7% decisiveness. Its intervals are narrower because
the stratified union-bound construction pays for more simultaneous group events.
The candidates are not uniformly superior on uncertainty or difference error.

For score estimation at half retention, candidate interval coverage is 100% on the
measured panel, with mean widths 17.37 pp (difficulty) and 19.69 pp (response).
Uniform coverage is 98.3% with width 10.38 pp. These wide conservative intervals
are not contradicted by 1.5–1.6 pp observed MAE: empirical average error and a
model-free finite-population interval encode different levels of protection.

At an illustrative 70% threshold, half-budget difficulty selection is decisive in
13.3% of score runs; response selection is decisive in 0%. Both forced point
decisions agree with the full grades in all runs, showing why an accurate retrospective
point decision should not be confused with strong prospective evidence. This
threshold was supplied for demonstration, not selected as a production criterion.

## Code map and replay

`pruning.py` owns candidate/baseline selection. `experiments.py` owns held-out
evaluation and ordering. `pruning_cli.py` joins the existing validated coding
input pipeline to the experiment. `pruning_reporting.py` publishes audit artifacts.
`uncertainty.py` owns count inversion and paired-discordance intervals; `transfer.py`
owns pair exclusion; `study_metrics.py` summarizes decisions and independent pairs.
The reference pipeline continues to support issue #14 unchanged.

Run the commands in [README.md](README.md). `tools/audit_lcb.py` independently
reads raw reviews and saved selections with the standard library; it imports none
of the pipeline. It verifies input/output/implementation hashes, normalized grades,
selection uniqueness, weight totals, all estimated means, and held-out MAE/maxima.
It now reconstructs stratum membership from historical grades, verifies all exact
score and paired intervals with independent linear inversion, and checks threshold
classifications and pair-difference summaries.
It is a verification tool, so run it with normal Python (without `-O`, which disables
assertions). The machine-readable results include both input and implementation
fingerprints. Byte-identical reruns are verified for all eight artifacts.
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
   budget, validate uncertainty calibration on untouched models, and use full
   evaluation for ambiguous cases.
8. **Is this ready inside evalscope?** This ticket is the offline candidate study.
   The later adapter must pin upstream, preserve ID correspondence, freeze reference
   features, support the chosen scoring weights, and validate its real CLI behavior.
9. **Why isn't 100% empirical interval coverage a guarantee?** Only twenty fixed
   seeds and three target folds are observed; the theoretical statement is
   conditional on the sampling design and fixed grades. Wide bounds can cover
   everything while giving few useful decisions. Always report width and abstention.
10. **Why test pairs with only one reference?** That is the strongest available
    exclusion protocol for ranking with three models. It removes the optimism of
    scoring a model used to construct its own strata, while exposing the limited
    historical evidence instead of hiding it.
