# Issue #24: explain Handout A from first principles

Start with the [one-page technical handout](../output/pdf/handout-a.pdf). Its
[Markdown source](HANDOUT_A.md) is the canonical text. This longer guide is for
learning and rehearsal; it is not part of the one-page submission.

The assistant prepared this learner-labelled ticket at your explicit request.
Practise the calculations and commands yourself. In an interview, distinguish
what the software demonstrates, what the historical data supports, and what
still needs an experiment.

## 1. Imagine making a shorter school exam

You have a 100-question exam. Giving all 100 questions takes a long time.
You would like to ask 20 questions and still know whether a student is ready.

Picking only easy questions makes almost everyone look good. Picking only hard
questions makes almost everyone look bad. Picking your favourite questions
reflects your taste. A useful short exam needs to represent the different kinds
of questions and preserve the decisions the full exam would have produced.

Our students are AI models. The coding exam is LiveCodeBench v5: 315 tasks.
The long-reading exam is AA-LCR: 100 tasks. Three models already have recorded
answers and grades. We can try smaller exams using those existing grades without
paying to ask the models again.

The practical objective is **decision fidelity per evaluation cost**: how little
evidence can we collect while keeping the conclusions trustworthy? This work
measures fidelity; live cost savings have not been measured.

## 2. First check which grade belongs to which answer

A prediction is a model's answer. A review contains a grade for that answer.
They arrive in different files, potentially in different orders. Match their
question identity, not their line number. Reject duplicates and missing joins.

Think of returning marked exams: the student's name must match the grade.
A wrong match makes every later calculation unreliable.

There are `315 + 100 = 415` Part A questions per model and three models:
`415 * 3 = 1,245` recorded grades. That does not mean 1,245 distinct questions.

| Model | Coding successes / 315 | Coding score | AA-LCR successes / 100 |
| --- | ---: | ---: | ---: |
| gpt-oss-120b | 241 | 76.51% | 48 |
| kimi-k2.5 | 198 | 62.86% | 66 |
| minimax-m2.5 | 195 | 61.90% | 64 |

These are historical outcomes. This ticket did not generate new model answers.

## 3. Make groups before choosing questions

A **stratum** is a group. **Stratified selection** takes representatives from
each occupied group so a small exam does not accidentally omit an important
kind of question.

Coding uses two candidate strategies. Historical difficulty groups questions by
how many reference models passed. Response-pattern groups distinguish *which*
models passed: `[pass, fail]` and `[fail, pass]` differ even though both have one
pass. AA-LCR groups length with difficulty, or length with document count, so
short documents do not crowd out long or multi-document work.

Every occupied group gets representation; remaining slots are proportional to
group size. A seeded hash priority chooses members reproducibly inside groups.
A seed changes the selection, not the model's already recorded answers. The
hash is a reproducibility mechanism; statistical interpretation assumes it
behaves like uniform selection within each fixed group.

Uniform random selection of the entire pool, easiest-only and hardest-only
methods appear as comparison baselines. They cannot become the final selected
strategy. Random-like selection *within structured groups* is different from
the forbidden whole-pool uniform baseline.

## 4. Weight the groups back to their real proportions

Suppose the exam has 20 short questions and 80 long questions. You select five
of each. Your selected exam is half short, but the original exam is only
one-fifth short.

If a model scores 80% on selected short questions and 40% on selected long ones:

```text
Unweighted subset score = 0.5 * 80% + 0.5 * 40% = 60%
Weighted full estimate  = 0.2 * 80% + 0.8 * 40% = 48%
```

The handout's `sum_h (N_h/N) mean_h` means: for each group `h`, multiply its
average score by its share of the full population, then add the results.
`N_h` is the group's full count and `N` is the full question count.
Equivalently, each selected question's weight is `N_h / (N * n_h)`, where `n_h`
is the selected group count. Weights sum to one.

Weighting repairs unequal group proportions. It cannot guarantee that selected
questions represent every variation *inside* a group, or that the benchmark
matches the customer's workload.

## 5. Hide the student's grades while choosing their exam

If you select questions after seeing a student's answers, you can accidentally
build an exam that makes that student look good. This is **leakage**.

Leave-one-model-out selection uses two models as references and tests the third.
Then rotate the excluded model. The excluded model's grades are used afterward
to measure fidelity, never to choose its subset.

Ranking needs a stronger separation: exclude *both* models being compared before
choosing their common subset. With three historical models, that leaves one
reference. Otherwise one member of the comparison could influence the test.

The three-model panel is small, and these folds were reused to develop methods
and select sizes. They are development stress tests. They do not prove a fourth
unseen model will behave the same way. Freeze choices and test on genuinely
untouched model families before making that stronger claim.

## 6. A score, an ordering and a decision are different promises

**Score fidelity:** how far is the estimate from the full recorded score?
An estimate of 63% versus a full 66% has an error of three percentage points.

**Ordering fidelity:** does the same model win? The coding runner-up gap is only
`(198 - 195) / 315 * 100 = 0.95` percentage points. Errors that seem small on a
100-point scale can easily reverse this close pair.

**Decision fidelity:** would you accept the same model? Suppose the requirement
is 65%, the full score is 66%, and the estimate is 63%. A three-point error
turns acceptance into rejection if you force a yes/no answer.

A confidence interval expresses sampling uncertainty under its assumptions. If
it spans the threshold, say **inconclusive**. For a 65% threshold:

| Score interval | Recorded-pool decision | Reason |
| --- | --- | --- |
| [67%, 75%] | GO | Entire interval meets the threshold |
| [53%, 64%] | NO GO | Entire interval is below the threshold |
| [60%, 70%] | Inconclusive | Plausible values lie on both sides |

An interval method with 95% coverage aims to cover the fixed population's true
value in at least 95% of repeated samples under its design assumptions. It is
not a 95% guarantee for an unseen model or customer workload. Conservative
intervals can be wider and cover more often. The implemented finite-pool method
uses hypergeometric bounds for sampling without replacement and conservative
allocations across groups; it does not use the normal-mean example on the
[NIST interpretation page](https://itl.nist.gov/div898/handbook/prc/section1/prc14.htm).

## 7. Why we ended up keeping the entire exam

We tested 10%, 20%, 30%, 50% and 100% retention, over 20 seeds. Coding rounds
half retention up to 158/315; AA-LCR half retention is 50/100.

The example policy checks twelve separate metrics. The three-point error gate
applies to **each held-out model's mean absolute error**, not to an average that
can hide a weak model. Other gates check worst error, interval width/coverage,
ordering, decisions and seed sensitivity. It requires both low observed error
and enough decisive answers; never deciding could otherwise look perfectly safe.
The handout spells out every metric and threshold. They are illustrative,
retrospective requirements, not customer-approved requirements.

| Candidate at half retention | Attractive result | Why it still fails |
| --- | --- | --- |
| Coding difficulty | Worst-fold MAE 1.83 pp, below 3 pp | Weakest pair ordering agreement 60%, below 95%; its interval decisiveness 0%, below 80% |
| AA-LCR length+difficulty | Pooled MAE 2.90 pp, below 3 pp | Worst-fold MAE 3.16 pp, above 3 pp |

Imagine three children with errors of 1, 2 and 6. Their average is 3, but one
child has error 6. A promise that *each* child's average error is at most 3 is
broken. This is the difference between pooled and worst-fold error.

No smaller tested candidate met every gate. The defended defaults are therefore
315/315 coding and 100/100 AA-LCR: **0% pruned**. We did not test every size
between half and full retention. We cannot claim full retention is a universal
mathematical minimum, nor that a different agreed screening policy could never
support compression.

This is a useful negative result: the evidence prevented an unsupported claim
of savings. Full retention exactly reproduces the fixed recorded pool, while
real-world distribution differences, generation randomness and judge error remain.

## 8. The grader can be uncertain too

AA-LCR uses an AI judge. Regrading the *same answer* might change the grade.
The supplied records have one judgment per answer, so repeat-judge variance is
unknown. It is not zero. Differences between two models' different answers do
not estimate how often a judge changes its mind about a fixed answer.

On 100 questions, one changed grade moves a model's score by one percentage
point. Kimi's 66% and Minimax's 64% can tie after two suitably directed changes
across the pair, and reverse after three. These are sensitivity examples, not
measured probabilities of a reversal.

To measure randomness, rejudge identical fixed answers several times. To assess
systematic bias, compare with qualified human adjudication or independent judges.
More repeated judgments do not automatically remove systematic bias.

## 9. Where the engineering runs

The statistical package in this repository provides historical replay evidence.
The deliverable pruners and full-versus-pruned comparison live in the private
[EvalScope fork](https://github.com/sdv1708/evalscope-pruning), inside its native
dataset, evaluation and report flow. Upstream base:
`66f0945d145ce6c30de40253cd78144003c6f1fe`. The comparison extension was recorded
at `5fd26289972f6d01b13ea95bb30481ebd103fa2d`; see the
[version/provenance record](evalscope-compare-runs.json) and
[complete native command guide](ISSUE_21_GUIDE.md).

The comparison command consumes compatible saved Native runs:

```powershell
python -m evalscope_ext.tools.compare_runs --full results_full --pruned results_pruned
```

It checks identities and settings, counts unique questions and attempts, reports
weighted scores and disagreement, and warns about unsupported claims.

The recorded loopback fixture used 12 full questions and three retained
questions. Both scores were 1.0, but conservative completion bounds for the
subset were `[0.25, 1.0]`. A required score of 0.8 sits inside that range, so the
subset decision was inconclusive. All three observed answers being correct does
not tell us what the nine unobserved answers would have been. These are
completion bounds, not probabilistic sampling confidence intervals.

That fixture validates software integration. Its 75% count reduction is not
evidence of production compression or model quality.

## 10. Now test a robot's picture-reading path

A robot gets a picture of red and blue bars and a question: which is taller?
It needs to see the bars, connect them to the words, reason and format an answer.
A wrong answer could come from any of those stages.

Part B proposes a visual probe for the full pinned MMMU inventory: 11,550
questions across 30 subjects. The supplied 660 examples cover only 22 subjects
for one model; they cannot stand in for that whole population. Development and
validation are for calibration; the proposed confirmatory frame is the 10,500
test questions. Released test answers need an audited source-ID join.

Use two proposed panels with different jobs:

- **Panel R:** initially 360 test questions, stratified by subject/difficulty,
  with recorded inclusion probabilities and population weights.
- **Panel S:** initially 120 additional questions selected to cover rare visual
  stressors. It is a diagnostic panel, reported separately without a claim to
  estimate population accuracy. Coverage feasibility may require a larger budget.

These counts are initial design budgets, not proven sufficient sample sizes.
Pilot precision/power and coverage audits determine whether they need to grow.

Tiny labels stress resolution and text extraction. Dense charts stress legends,
scales and close marks. Thin diagrams stress arrows and connections. Clutter,
spatial detail, color distinctions and specialized imagery exercise additional
ways task-relevant information can be lost. These target the visual path; they
do not each correspond uniquely to one encoder component.

## 11. Change one picture, keep the puzzle fixed

Show the same question with the original image and a controlled changed image:
downsampled, blurred, JPEG-degraded, partly covered, lower contrast/saturation,
or blurred in annotated text regions. Keep other image slots and words fixed.

This is **pairing**. The same question is its own control, reducing variation
from question difficulty. Each treatment starts from the same original. Pin
image/model/request settings and interleave repeated attempts to expose variation.

Two reviewers must confirm that necessary facts and labels survive before a
pair contributes to robustness summaries. Erasing a minus sign changes the
puzzle; a different answer could be correct for the damaged picture. Destructive
controls are useful, but are excluded from label-preserving robustness claims.

Worked example, invented for explanation:

| Question | Original | Changed |
| --- | --- | --- |
| 1 | Correct | Correct |
| 2 | Correct | Wrong |
| 3 | Wrong | Correct |
| 4 | Same wrong answer | Same wrong answer |

Both accuracies are 50%; paired drop is zero percentage points. Only two answers
stay the same, so answer consistency is 50%. Regressions and improvements cancel
in the mean. Consistency can also be 100% when every answer is wrong.

Report both metrics and failure categories. A completed malformed answer scores
zero under the frozen format rules; a missing or transport-failed answer remains
unknown. Publish paired coverage and best/worst completion bounds. Repeats of one
question are not independent new questions.

The implemented offline demo has three synthetic image families, 38 transformed
pairs and a plan for 82 calls. Its 79 responses and QA are scripted. It tests
image identities, requests and calculations, not human semantic validity or live
model robustness. The full two-panel selection, real annotations and endpoint
experiment remain proposed.

## 12. Why this does not prove the encoder caused a failure

From an OpenAI-compatible API, we see inputs and outputs. We cannot inspect
whether information was lost in resizing, encoding, fusion, reasoning or output
formatting.

Add a no-image condition to detect questions solvable from words or memorized
knowledge. Supply equivalent factual text to check reasoning when perception is
bypassed, without giving away the solution. Ask for visual facts such as an axis
label to measure extraction before solving the main problem.

The [MMStar research](https://arxiv.org/abs/2403.20330) motivates these controls:
its authors find that visual input is unnecessary for many benchmark examples.
Our probe design uses original MMMU and does not substitute MMStar's dataset.

Failure on an image plus success on equivalent text can suggest a visual-path
bottleneck. It does not uniquely identify the encoder: the modality and prompt
also changed. A causal encoder comparison needs an intervention that changes
only the encoder while keeping other components and serving settings fixed.

## 13. What more resources would change

| Resource | Concrete next experiment | What it would resolve |
| --- | --- | --- |
| More data | Untouched model families and customer tasks; hold out whole AA-LCR document sets | Transfer beyond the three-model development panel and benchmark distribution |
| Live endpoint | Freeze policy; run a fresh model full/subset; repeat generations and identical-answer judging; human-audit judges | Transfer, generation/judge variation, bias, and actual token/time/cost effects |
| Live image endpoint | Audited original MMMU images/labels, semantic QA, provider preflight and the control conditions | Actual paired visual sensitivity rather than synthetic software behavior |
| More time | Explore intermediate sizes, audit duplicate/coverage structure, calibrate statistical power, freeze independent confirmation | A better supported size and a clean final validation |

Adding more seeds only changes which old questions are selected. It cannot
replace new model families, repeated judgments or a customer workload sample.
More method/size search also increases the need for untouched final evaluation;
[scikit-learn's validation example](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html)
explains how tuning and evaluating on the same evidence makes estimates optimistic.
Our historical stress tests are not claimed to implement nested validation.

## 14. Your 90-second explanation

“I treated compression as preserving decisions, not just reducing question count.
I validated the recorded answer/grade joins, then tried structured selection with
population weights. I held out one model for score estimation and both models
for pair comparisons, and checked multiple sizes over fixed seeds.

“The retrospective policy required accurate scores, reliable ordering, useful
threshold decisions and bounded uncertainty for every fold. Half-size coding
estimates were close in score but unreliable for the closest ranking; AA-LCR
also failed the worst-fold error gate. No smaller tested candidate passed, so the
defended default keeps all 315 and 100 questions, with no claimed savings.

“The runnable extensions and comparison live in pinned EvalScope. Synthetic
integration evidence verifies that software works, without claiming real model
quality. For multimodal testing I propose weighted population sampling plus a
separate stress panel, paired image changes and reasoning controls. The offline
harness is implemented, but live visual conclusions and encoder-only causality
still require additional experiments.”

## 15. Interview questions to practise aloud

**Why did you prune zero questions?** The measured smaller candidates failed
declared illustrative requirements. Forcing savings would misstate the evidence.
Full retention is the smallest passing tested point, not a proof of impossibility.

**Why not just random sample?** Whole-pool uniform selection is forbidden by the
brief and can omit small important groups. The candidates preserve declared
structure and use weights. Random selection remains a diagnostic comparator.

**Why do weights matter?** Our quota allocation can overrepresent small groups.
Weights restore their full-pool proportions, as in the 60%-versus-48% example.

**Is the policy preregistered?** No. It was fixed before issue #17's replay but
after earlier results were known. It is retrospective and illustrative.

**What makes a subset sufficient?** It must meet the intended-use error,
uncertainty, ranking and decision requirements on independent evidence. These
historical folds support development; they do not certify an unseen model.

**Why can a good average be bad?** Averages hide weak folds and close rankings.
AA-LCR pooled MAE is 2.90 pp, while its worst-fold MAE is 3.16 pp and fails.

**Why isn't a census perfectly trustworthy?** It removes subset sampling error
for the recorded pool. It cannot remove wrong labels, judge bias, future-model
variation or customer-distribution shift.

**Are all your intervals the same?** No. Historical sampling confidence bounds
depend on the fixed sampling design. Comparison/harness completion bounds use
best/worst unknown outcomes and are not sampling confidence intervals.

**Did you show 75% savings in EvalScope?** The 12-to-3 fixture showed a smaller
synthetic run and correct serialization/comparison. Its decision stayed
inconclusive, and it did not measure production cost or savings.

**What did you prove about image encoders?** The implemented synthetic harness
proves no model property. The proposed live experiment measures visual-path
sensitivity; encoder causality needs an encoder-only controlled intervention.

**What would you do first with a live endpoint?** Agree customer tolerances,
freeze selection and scoring, then validate a genuinely fresh model on the full
pool and subsets. Preserve settings and measure latency/cost and judge repeats.

## 16. Reproduce the handout and evidence

From the repository root, use Python 3.12 for the existing Task 2 environment:

```powershell
cd task2
uv sync --locked
uv run part-a-operating-points --data-root ../Evals --output-dir output/issue24-operating --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/issue24-operating/live_code_bench_v5
uv run python tools/audit_aa_lcr.py --data-root ../Evals --reports output/issue24-operating/aa_lcr
uv run python tools/audit_operating_points.py --reports output/issue24-operating
```

The PDF renderer uses documentation-only dependencies; the benchmark package
does not need them. From the root, create a separate environment:

```powershell
uv venv task2/output/handout-env --python 3.12
uv pip install --python task2/output/handout-env/Scripts/python.exe reportlab==4.4.9 pypdf==6.10.0
.\task2\output\handout-env\Scripts\python.exe docs/scripts/render_handout_a.py
```

The renderer reads the Markdown, checks all evidence-link targets, creates a
staged PDF, and refuses publication if it spills beyond one page. Body text is
10.2 pt; evidence is 8.5 pt. Render the PDF with `pdftoppm` and inspect it after
edits. It is intentionally a small renderer for this document's paragraph,
heading, bold and link syntax, not a general Markdown converter.

## 17. Rehearse without hidden analysis

1. Read only the one-page handout and give the 90-second explanation.
2. Calculate `415 * 3`, `241 / 315`, the weighted 48%, and the 0.95 pp pair gap.
3. Explain why 60% pair agreement fails even when score MAE is below 3 pp.
4. Explain the difference between a keep ratio and a prune ratio: 100% kept is
   0% removed. Half retention rounds up to 158 coding questions.
5. Draw the one-model versus two-model exclusion rules from memory.
6. Explain why one AA-LCR judgment per answer cannot reveal repeat-judge variance.
7. Draw the four-question paired example and calculate both metrics.
8. Name a failure that could come from preprocessing rather than the encoder.
9. Point to one measured claim, one synthetic validation and one proposed budget
   in the handout, then follow its evidence link.
10. Explain why the remaining validation is worth doing despite the conservative
    no-compression result.

See the [acceptance and verification record](../docs/issue-24-evidence.md) for
the exact prompt mapping, research trail and checks performed for this ticket.
