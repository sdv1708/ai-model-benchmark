# Issue #21: understanding the comparison command from first principles

## 1. The job in one picture

Imagine a teacher has a book of 100 questions. Answering every question takes a
long time. We want a shorter test that still tells us whether a student is ready.

- **Full run:** answer the whole agreed question book.
- **Pruned run:** answer a carefully selected smaller set.
- **Comparison:** check how much the smaller test changes the conclusion.

The command is the scorekeeper. It does not select questions, call a model, or
ask a judge to grade answers. Issues #19 and #20 provide those native evaluation
paths. Issue #21 reads the saved evidence and checks that the comparison is fair.

The implementation lives in the separate private EvalScope fork,
`sdv1708/evalscope-pruning`, inside `evalscope_ext/tools/`. This repository holds
the explanation, integration lock and acceptance evidence. Your explicit request
authorized implementation of this learner-labelled ticket; reading this guide
and reproducing the examples is how to build your own understanding.

## 2. Where it fits in the project

The chain is:

1. #14 validated the historical evaluation files and reproduced full scores.
2. #15 and #16 researched coding and long-context subsets.
3. #17 evaluated conservative operating points. No smaller tested candidate
   passed every gate, so the defended fallback retains everything.
4. #18 established the native EvalScope extension.
5. #19 and #20 put the coding and AA-LCR pruners inside that framework.
6. #21 compares the resulting saved runs.

This ticket completes a measurement workflow. It does not change #17's scientific
conclusion or prove that a future model can safely use a smaller benchmark.

## 3. The files are three kinds of evidence

An exact Native run root contains:

```text
results_full/
  configs/task_config.yaml
  reports/<model>/<benchmark>.json
  reviews/<model>/<benchmark>_<subset>.jsonl
```

Think of the configuration as the exam instructions, the report as the report
card, and the reviews as each marked answer sheet. A report card saying 90%
is not enough: we check the answer sheets and the exam instructions too.

`predictions/` also exists in normal runs, but this command does not require it:
the reviews already contain the evaluated input, target and grade. Prediction-only
or incomplete runs cannot be compared. The historical challenge `Evals/` directory
does not contain the full Native contract and is not silently treated as one.

Primary sources researched were the pinned framework's `CacheManager`,
`ReviewResult`, `SampleScore`, `Report`, evaluation identities, native aggregation,
and CLI help; also the official
[run-directory documentation](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html)
and [judge/parameter documentation](https://evalscope.readthedocs.io/en/v1.14.0/get_started/parameters.html).
The exact framework source wins over rolling documentation when they differ.
The inherited upstream source pin is `66f0945d145ce6c30de40253cd78144003c6f1fe`.

## 4. How the command works

```powershell
python -m evalscope_ext.tools.compare_runs --full results_full --pruned results_pruned --threshold 0.7
```

`python -m` asks Python to run a package module. `--full` and `--pruned` identify
the exact directories. `--threshold 0.7` says the caller's minimum acceptable
accuracy is 70%; it is an example requirement, not a discovered customer fact.

The loader validates every input before the command prints comparison JSON.
It matches model, benchmark and subset keys, checks the settings, reads successful
binary grades, reconstructs unique questions and checks the selection design.
The comparator then calculates scores, differences, bounds and optional decisions.
With multiple matched models it also reports ordering within a benchmark/subset.

Code map in the EvalScope fork:

- `compare_runs.py`: argument parsing, pair compatibility, comparisons, decisions,
  cross-model ordering checks, JSON and exit status.
- `saved_runs.py`: file loading, validated Pydantic evidence objects, stable input
  identity, complete attempts, pruning weights and report reconciliation.
- `tests/tools/test_compare_runs.py`: tests through the public subprocess command.
- `examples/aa_lcr_pruned/smoke.py --compare`: real Native CLI integration fixture.
- `COMPARE_RUNS.md`: complete installation, real endpoint and smoke commands.

Exit **0** means the comparison succeeded. It does not mean the model passed.
Invalid inputs produce exit **2**, an error on stderr, and no partial JSON on stdout.
The shell can still create an empty redirected file on failure; check the exit code.

## 5. First make sure we are comparing the same exam

One student cannot take easy questions while the other takes unrelated hard
questions and have their percentages treated as a fair comparison. The same
principle applies to full and pruned model runs.

The command checks model identity, generation configuration, judge configuration,
source revision, prompt, filtering, repeats, sandbox configuration and evaluation
version. Ratios and selection settings can differ as expected. Local paths may
refer to different mirrors, but the evaluated inputs still must match.

Execution row numbers are not question identities. A pruned run reindexes its
smaller question list starting at zero. Instead, the comparison hashes the input
messages, expected answer and coding grading test cases. Ephemeral message IDs
and generated answers do not define the question. Native pruning traces also
check the panel hash, original identity, stratum and population counts.

This catches a subtle coding bug: two visible questions may look identical while
their hidden grading tests changed. Matching only the prompt would miss it.

Use the reference adapter at ratio **1.0** for the full run. It evaluates the whole
frozen population and preserves the same provenance and AA-LCR document order.
The original full adapters are supported when inputs/settings match, but produce
a warning because full historical population identity cannot be proven without
their missing pruning traces. A default coding source with 880 rows is not the
315-question reference population.

## 6. Why unique questions and repeated attempts are different

Suppose the model answers each of two questions twice:

| Question | Attempt grades | Question mean |
| --- | --- | --- |
| A | 1, 0 | 0.5 |
| B | 1, 1 | 1.0 |

There are **2 questions and 4 attempts**. Repeating A does not add a new question
to our coverage. We average attempts within each question before weighting it.
Missing or duplicated generation positions fail; they are not silently dropped.

Different Native metrics count differently: original AA-LCR's ordinary `mean`
reports attempt count, while the pruned population metric reports unique questions.
The loader respects that distinction but always exposes both counts explicitly.
Average-attempt accuracy is also different from pass@k: passing at least once in
several attempts answers a different question than average success per attempt.

## 7. Why an ordinary average can be wrong

Imagine eight questions: two in a small group and six in a large group. We retain
one question from each group. The small-group question fails; the large-group
question passes. A simple average of the two grades says **50%**.

But the retained questions represent different numbers of original questions:
the first represents 2/8 and the second represents 6/8. The population estimate is:

```text
0 × 2/8 + 1 × 6/8 = 0.75 = 75%
```

The general question weight is `N_h / (N × n_h)`, where `N_h` is the full size
of its group, `N` the whole population, and `n_h` the number retained from that
group. Sum each weight times that question's average attempt grade.

The command reports both the raw subset mean and the weighted population estimate.
It validates the weights against group counts and rejects missing groups/questions.
It never renormalizes away missing evidence. Weighting corrects the allocation;
it does not prove the selected questions are representative of an unseen model.

## 8. What a score difference means

If the full score is 0.70 and the pruned estimate is 0.75, the signed difference
is **+5 percentage points**. The absolute error is 5 points. It is not a 5%
relative improvement: relative change would be 5/70, about 7.14%.

Positive error means the subset overestimates that recorded full score. Negative
error means it underestimates it. Zero error on one run is useful evidence,
but is not proof of future reliability. The paired question MAE separately asks
whether grades changed on the overlapping questions, which can happen when
generation or judging is nondeterministic.

Saved reports round scores to four decimal places. The loader checks individual
subsets against exact review calculations, then checks aggregate report rounding
at the framework's subset/category/metric boundaries. Output comparison scores
keep full review precision. This avoids rejecting valid reports for double rounding.

## 9. A high estimate is not automatically GO

Suppose there are four questions. We observe two passes and leave two unseen.
The subset estimate is 100%, but the full population might contain two passes
and two failures: only 50% overall.

For `n` observed questions out of `N`, let their question means sum to `S`:

```text
lowest possible completion = S / N
highest possible completion = (S + N - n) / N
```

Every unseen question may have any mean between 0 and 1. These are deterministic
completion bounds, not a 95% confidence interval. They require no claim that a
deterministic hash selector is a random sample. They deliberately trade decisiveness
for fewer assumptions. Their width is `1 - n/N`, so heavy pruning can be inconclusive.

At threshold 60%, bounds [50%,100%] straddle the requirement. We return
**inconclusive**, even if the point estimate says GO. If the entire bound is at
least the threshold, return GO; if the entire bound is below it, return NO GO.
Equality qualifies. With no supplied threshold, the command does not invent one.

The subset decision never borrows the full run's unselected grades. We compare
its conclusion to the recorded full decision afterward. If overlapping grades
changed between fresh runs, the bounds describe possible completions of the
pruned run, not the exact full run's different recorded grades.

## 10. Why AA-LCR needs an extra warning

AA-LCR uses a model to judge another model's answer. Think of two teachers who
may disagree about the same answer. One stored grade per answer cannot tell us
how often the judge changes its mind. That uncertainty is **unmeasured**, not zero.

A census eliminates uncertainty from unobserved questions in this fixed pool.
It does not eliminate judge error, generation variation, future-task changes or
customer-workload mismatch. The output therefore keeps `decision_certified=false`.
GO is conditional evidence about this recorded setup, not a production guarantee.

## 11. Why model ordering needs its own checks

A shortlist can become misleading even if score errors are modest. Imagine two
models score 66% and 64%; a subset that estimates 63% and 65% reverses their order.
The command reports whether pairwise ordering is preserved, with ties distinct
from strict wins. It needs at least two matching models per benchmark/subset.

Before ranking, it verifies that the full runs share the complete input pool and
the generation/judge/scoring protocol. A benchmark name alone does not establish
comparability. Model-specific selections may still differ; the resulting ordering
is descriptive and does not replace independent pair-holdout transfer experiments.

## 12. Reproduce the measured result

In an activated Python 3.12 environment in the EvalScope fork:

```powershell
python -m pip install -e .
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/comparison-smoke
python -m evalscope_ext.tools.compare_runs --full outputs/comparison-smoke/full --pruned outputs/comparison-smoke/pruned --threshold 0.8
```

The smoke uses a local OpenAI-compatible answer/judge fixture and tiny synthetic
documents. It makes no paid model calls. Expected evidence: **12 full questions,
3 pruned questions, both scores 1.0, zero-point difference, bounds [0.25,1.0],
full GO and pruned inconclusive**. The fixture's 75% sample reduction is an
integration demonstration; it is not a certified production saving.

For real endpoint commands, use the fork's `COMPARE_RUNS.md` and real question
data/test cases. The task brief's conceptual `--output` becomes `--work-dir` in
this pinned CLI. `--no-timestamp` makes the documented output roots exact;
otherwise pass the actual timestamp directory. Pruning arguments are nested by
benchmark under `extra_params`. Do not reuse tiny fixture data as a real benchmark.

## 13. Interview answers to practise

**What did you build?** A saved-run comparison module that validates Native
evaluation evidence, compares full accuracy to a weighted subset estimate, and
reports conditional threshold and ranking evidence with explicit limits.

**Why not just subtract two report scores?** That can compare different exams,
count repetitions as coverage, accept partial grades, or compare a raw subset
mean to a population target. I reconcile reports with reviews and configurations.

**Why use a full run at ratio 1.0?** It is a census of the identical frozen
reference population, with matching input and selection provenance. A default
upstream dataset might contain different questions or document ordering.

**Why no bootstrap or 95% interval?** This CLI uses deterministic completion
bounds instead of assuming a probability design or independent stochastic labels.
Statistical design intervals and transfer studies remain separate evidence.

**Can matching scores prove compression works?** No. They establish retrospective
fidelity for the observed setup. A new model, judge, source or workload can behave
differently. The defended operating point still retains the full reference pools.

**Why are failed grades rejected?** A judge transport failure means no reliable
grade was obtained. Calling it zero or dropping it and renormalizing changes the
estimand and can bias the decision.

**What did review catch?** Missing cross-model comparability checks, omitted hidden
coding tests in input identity, original AA-LCR repeat-count semantics, and Native
multi-level rounding. Each was repaired and covered through the public CLI.

**What would you do next?** Agree real customer thresholds before evaluation,
test independent held-out model pairs, collect repeated generations and judge
verdicts, measure actual tokens/time/cost, then select the smallest budget that
passes those preregistered gates. Do not advertise a saving before that evidence.

Practise a short answer first: “The small test has to preserve the decision,
not merely look close on one score. I check the exam, the weighting and the
uncertainty before showing a conclusion.” Then expand using the worked examples.
