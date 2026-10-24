# Issue #26: final Task 2 handoff and interview guide

## Start with a school-test story

You have several robots and want one that can write code and read long books.
Testing every question costs time. You try a shorter exam, but the shorter exam
must help you choose the same robot for the same reason. A short exam that changes
your choice is not ready, even if its score looks close.

That is this project. A **benchmark** is an exam. A **pruner** chooses questions
before the candidate answers. **EvalScope** runs the exam, grades answers and saves
evidence. The **comparator** checks whether a shorter run supports the same conclusion.

The honest result is **315/315 coding questions and 100/100 long-context questions
retained: 0% defended pruning**. Smaller tested candidates did not pass every gate.
We built and tested the selection/integration machinery, but we have not delivered
a smaller validated exam. Do not turn that distinction into a savings claim.

Issue #26 finishes the reviewer entrypoints and this written demonstration.
The video is skipped at your direction; no video was recorded or uploaded.
The [submission checklist](../SUBMISSION_CHECKLIST.md) records that unmet criterion.

## Two repositories, two jobs

| Repository | What it owns | What it does not establish |
| --- | --- | --- |
| This [challenge repository](https://github.com/sdv1708/ai-model-benchmark) | Saved-data analysis, exported reference panels, operating-point evidence, handouts, image proposal/prototype | Installing `task2` does not install the native EvalScope pruners |
| Private [EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning) | Registered native adapters, original framework inference/grading/reporting, saved-run comparator | A successful synthetic run is not real-model quality evidence |

**Exact upstream base: `66f0945d145ce6c30de40253cd78144003c6f1fe`.**
**Tested native runtime: `800119ff6870ca958f5d8459970f5fe75bfac305`.**
Historical analysis code/data used by this documentation already exist at challenge
main `7882d16` (full provenance in [acceptance evidence](../docs/issue-26-evidence.md)).
This issue changes documentation, not runtime behavior. The native documentation
branch is `feature/issue-26-task2-documentation`; publication status is in the checklist.

A pin is the exact edition of a book. Using a different framework edition may
change flags, questions, prompts or grades. The old remote name
`ai-model-quality-challenge` redirects to canonical `ai-model-benchmark`.

## Path A: install and demonstrate the native integration

Use Git, Python 3.12, uv and PowerShell 7, with private repository access and internet
for installation. From a parent directory where the destination does not exist:

```powershell
git clone https://github.com/sdv1708/evalscope-pruning.git
cd evalscope-pruning
git checkout 800119ff6870ca958f5d8459970f5fe75bfac305
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements/pruning-baseline.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info live_code_bench_pruned
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info aa_lcr_pruned
```

Stop at any installation error. Direct interpreter paths avoid activation and
PowerShell execution-policy changes. The snapshot is Windows/Python 3.12 tested;
POSIX uses `.venv/bin/python` and needs dependency revalidation per the fork's
`PRUNING_BASELINE.md`. The runtime checkout predates issue #26's new native
`TASK2_README.md`; keep this guide open for the following steps.

From the installed fork root, choose a fresh output directory:

```powershell
.venv/Scripts/python.exe examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/task2-demo
if ($LASTEXITCODE -ne 0) { throw 'Synthetic evaluation failed' }
.venv/Scripts/python.exe -m evalscope_ext.tools.compare_runs --full outputs/task2-demo/full --pruned outputs/task2-demo/pruned --threshold 0.8
if ($LASTEXITCODE -ne 0) { throw 'Comparison failed' }
```

This starts a local scripted model/judge and runs the real evaluator twice.
It needs local socket/process permissions but makes no paid provider calls.

| Result | Expected value | What to explain |
| --- | --- | --- |
| Full / pruned questions | 12 / 3 | Unique questions, not repeated attempts |
| Full / weighted pruned accuracy | 100% / 100% | Both observed averages are perfect in this fixture |
| Signed difference | 0 percentage points | Matching observed scores do not imply a safe decision |
| Completion bounds | 25% to 100% | Nine grades are unknown to the subset |
| At illustrative 80% requirement | Full GO; subset inconclusive | A valid tool run can return insufficient evidence |
| `decision_certified` | false | This is not production approval |

The output has no model ordering with just one model. Exit 0 means the comparison
completed; read `decision.pruned`, bounds and warnings for the conclusion.
Exit 2 means invalid/incompatible evidence. Without `--threshold` there is no
threshold decision. Fixture question savings are not production savings.

The full relevant native suite and type/lint commands are in the fork's
`TASK2_README.md` and `VALIDATION_ISSUE_21.md`. A fast public-boundary check is:

```powershell
.venv/Scripts/python.exe -m pytest tests/tools/test_compare_runs.py tests/api/test_live_code_bench_pruned.py tests/api/test_aa_lcr_pruned.py -q
.venv/Scripts/python.exe -m mypy --follow-imports=silent --ignore-missing-imports evalscope_ext tests/tools/test_compare_runs.py examples/aa_lcr_pruned/smoke.py
```

For real endpoints, use the complete paired coding and AA-LCR templates in
[the operational runbook](ISSUE_25_GUIDE.md#7-real-endpoint-runbook), plus the
fork's `COMPARE_RUNS.md`, `LIVE_CODE_BENCH_PRUNED.md` and `AA_LCR_PRUNED.md`.
Real inference needs provider credentials, context capacity, original benchmark
data, coding sandbox setup and a fixed AA-LCR judge; no such inference was run here.
Use `--work-dir`, nested `dataset_args.<dataset>.extra_params`, `--no-timestamp`
and `prune_ratio` as a fraction **retained**. Use the reference adapter at 1.0
for the matching full population; smaller ratios are explicitly experimental.
`--limit` is rejected because it would invalidate coverage and weights.

## Path B: reproduce the historical evidence

This path uses the supplied saved outputs, not a model endpoint. Use Git LFS;
the complete inventory includes image-heavy MMMU references even for the initial
validation command. A pointer file is not usable evaluation data.
From a parent directory where the destination does not exist:

```powershell
git lfs install
git clone https://github.com/sdv1708/ai-model-benchmark.git
cd ai-model-benchmark
git checkout 7882d16
git lfs pull
cd task2
uv sync --locked
uv run benchmark-reference --data-root ../Evals --output-dir output/issue26-reference
if ($LASTEXITCODE -ne 0) { throw 'Reference validation failed' }
uv run part-a-operating-points --data-root ../Evals --output-dir output/issue26-operating --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
if ($LASTEXITCODE -ne 0) { throw 'Operating-point analysis failed' }
uv run pytest --basetemp=.pytest-tmp/issue26 -q
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

The thresholds reproduce the recorded illustrative policy. They are not customer
requirements. The default ratios are 0.1, 0.2, 0.3, 0.5, 1.0 with twenty seeds.
This is retrospective analysis: policy choice reused observed evidence, and the
intervals are not simultaneous guarantees after method/ratio search.
Do not replace the thresholds and claim exact reproduction of the old policy.

Expected files: `output/issue26-reference/full_scores.json`,
`output/issue26-operating/operating_points.json`, `curves.csv`, `manifest.json`,
and benchmark-specific diagnostics. Compare full scores with the
[recorded JSON](../docs/data/task2-full-scores.json) and selected fields with
[the operating record](../docs/data/task2-operating-selected.json).
Manifests identify source/implementation/output bytes; a later code edition can
change implementation hashes even if selected results remain identical.

| Model | Coding: successful / 315 | AA-LCR: successful / 100 |
| --- | --- | --- |
| gpt-oss-120b | 241 (76.5079%) | 48 (48%) |
| kimi-k2.5 | 198 (62.8571%) | 66 (66%) |
| minimax-m2.5 | 195 (61.9048%) | 64 (64%) |

These are stored-artifact results. They do not describe the latest endpoints or
an independently held-out fourth model. Missing/invalid grades fail validation;
they are not silently omitted or converted to zero.

## Written walkthrough and demonstration

Use these seven beats for a live explanation, or read them as a walkthrough.
No recording is needed to learn or reproduce the work.

1. **State the decision.** "I want fewer evaluation questions without changing
   the customer's decision about coding and long-document quality." Show the
   [Task 2 brief](../Task2_Model_Quality.md), then state 0% defended pruning up front.
2. **Show the historical evidence.** Run Path B; open `full_scores.json` and
   `operating_points.json`. Explain that score closeness, ordering, requirement
   decisions, uncertainty and seed sensitivity are different checks. No smaller
   tested candidate passed all required checks. Do not claim global optimality.
3. **Explain selection.** Coding uses historical difficulty groups. AA-LCR also
   uses token-length thirds. Keep coverage, allocate remaining slots and use
   deterministic seeded hashes within groups. Exclude the evaluated model's
   historical grades; pair holdouts stress transfer. Three models are still weak
   evidence for a new family. Uniform random, easiest-only and hardest-only appear
   only as comparison baselines, never the defended configured strategy.
4. **Show the native seam.** In the EvalScope fork open the two `*_pruned` adapter
   folders and shared code under `evalscope/benchmarks/pruning_smoke/`. Selection
   happens at `DefaultDataAdapter.load_subset`, before inference and repeats.
   Registration, source loading, prompts, sandbox/judge and reporting remain native.
   Fingerprints bind selected historical IDs to the actual question text/source.
5. **Run the demonstration.** Execute Path A and inspect saved `configs/`,
   `reviews/`, `reports/`, then the comparator JSON. Show 12/3, 100%/100%, 0 pp,
   [25%,100%] and inconclusive together. The comparator validates identity,
   settings, counts and weights before interpretation. Zero score error alone
   does not certify a shortcut.
6. **Show both handouts.** [Handout A](../output/pdf/handout-a.pdf) is a one-page
   technical defense. [Handout B](../output/pdf/handout-b.pdf) is a half-page
   operating/customer guide. Explain the same finding differently for an engineer
   and a deployment lead, including what remains uncertain.
7. **Explain the roadmap and limits.** Open [the full-MMMU design](MMMU_PROBE_DESIGN.md)
   and [synthetic harness](MMMU_HARNESS.md). Distinguish proposed real studies from
   tested offline mechanics. End by proposing fresh-model validation, repeated
   judging/generation and measured costs; do not present a production GO guarantee.

## Build the ideas from small numbers

**Strata are question baskets.** Suppose there are two diagram questions and six
text questions. Keeping one from each basket ensures coverage. If the diagram
answer fails and text answer passes, the plain selected average is 50%. The
population-weighted estimate is `0*(2/8) + 1*(6/8) = 75%`. Each basket gets its
original share. In general, each selected item in basket h gets `N_h/(N*n_h)`.
Weights correct representation; they do not prove that future robots behave like
the robots used to define the baskets.

**A percentage point is a subtraction.** Going from 70% to 75% is +5 percentage
points, not +5% relative. `difference_pp` reports the signed pruned-minus-full
difference on that scale. Check absolute error and decision fidelity too.

**Unknown answers are still unknown.** With three passes among twelve questions,
the lowest complete score is 3/12=25%, highest 12/12=100%. The comparator does
not borrow unselected full-run answers to make the short run certain.
These deterministic completion bounds differ from the offline experiments'
nominal 95% finite-pool statistical intervals.

**GO is conditional.** A bound wholly at or above the agreed threshold supports
benchmark GO; wholly below supports NO GO; straddling it is inconclusive.
If required coding or document evidence is inconclusive, gather more evidence.
Even both benchmark GOs need customer-workload and production-performance validation.

**The judge is another robot.** Coding uses executable tests. AA-LCR uses an LLM
judge. That judge may vary on the same answer. One verdict cannot reveal its
variance. Repeating candidate generation and rejudging a fixed answer measure
different things. Human review can help discover systematic judge bias.
Full retention removes unobserved questions from the fixed recorded pool; it
does not remove judge mistakes, generation variability or distribution shift.

## Multimodal roadmap in plain language

Now the robot must read pictures. Some questions need tiny labels, thin chart
lines, dense tables or spatial relationships. Randomly choosing questions can
miss these rare weaknesses. Deliberately cover stress types and compare the same
question with original versus mildly changed images, keeping the correct answer
unchanged and human-checked. Destructive changes are controls, not robustness proof.

The [official pinned MMMU inventory](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md)
has 150 development + 900 validation + 10,500 test = **11,550 questions** across
30 subjects. The 660 supplied rows cover only 22 subjects. The design inventories
all splits, uses development/validation for calibration, and proposes a frozen
confirmatory test panel targeting the 10,500-question test population.
It separates weighted population estimation from deliberate diagnostic coverage.

No-image controls ask if the picture was needed. Equivalent-factual-text controls
ask whether the robot can reason when visual facts are already supplied.
Visual-fact extraction checks what it perceived. The
[MMStar paper](https://arxiv.org/abs/2403.20330v2) supports using visual-dependence
controls; it does not validate our chosen future budgets or transformations.
Through an API, failure can implicate the visual path, including preprocessing,
fusion and reasoning. Claiming the encoder alone caused it needs an intervention
that changes only the encoder. The full probe remains unrun; the existing harness
only tests synthetic transformations, request plans and saved-response analysis.

## Interview rehearsal

Start with this answer in your own words:

"I built native EvalScope pruners and a comparison workflow to test whether we
could shorten coding and long-context evaluations without changing decisions.
I used structured selection and weights, tested multiple retained sizes and
holdouts, and found that only full retention passed the retrospective policy.
I therefore claim reproducible infrastructure and a conservative fallback, not
validated savings. I documented the evidence and limitations for engineering
and customer audiences, plus a controlled multimodal study proposal."

| Interviewer asks | What your answer must contain |
| --- | --- |
| Why did you fail to prune? | Smaller tested candidates failed one or more required gates; 0% is an honest fallback and the compression ambition remains open. |
| Why not random or hardest-only? | Random is a baseline; extremes distort coverage. Structured groups preserve coverage and enable weights, but still need validation. |
| How do you avoid leakage? | Select using other historical models before target inference, exclude target aliases explicitly, use holdouts; acknowledge policy-selection reuse. |
| Why this framework seam? | Whole-pool selection needs a population view; `load_subset` preserves downstream native behavior. Per-row conversion alone is too narrow. |
| How do you prove it lives inside EvalScope? | Show registry names, adapter source, CLI invocation and native saved artifacts, not just the analysis script. |
| Why fingerprints? | Numeric indices can refer to different source rows after reorder/version changes; bind identity to question content and pinned metadata. |
| Why weights? | Unequal sampling changes group proportions; show the 75% versus 50% example. |
| Why can perfect observed accuracy be inconclusive? | Show three known passes plus nine unknown answers and the 25%-100% range. |
| Does a successful exit mean GO? | No; it means valid processing. Read the decision, bounds and warnings. |
| Does full retention solve uncertainty? | Only missing-question uncertainty within recorded grades, not generation, judge or future-distribution uncertainty. |
| What proves transfer to a fourth model? | Nothing yet; holdouts are stress tests. Freeze the policy and evaluate an untouched model. |
| What did the demo prove? | Native transport, selection, judging, serialization, validation and comparison on scripted synthetic data. |
| How much money did it save? | No validated live saving. At the defended setting sample saving is 0%; measure tokens, judging, runtime and cost separately. |
| Is the image encoder broken? | API evidence can diagnose visual-path sensitivity; encoder-only causality requires a controlled component change. |
| What would you do next? | Agree customer thresholds, use a new model, repeat generation and fixed-answer judging, audit failures, measure costs and validate customer tasks. |

Practise without reading: draw the two repositories, the native flow and the two
small arithmetic examples. Then run the demo and explain every displayed number.
Avoid memorizing a claim stronger than the evidence. Recording a video is optional
for your learning but still required by the original submission.

## Evidence and further reading

Fresh verification, research, exact commits and limitations are in
[issue #26 evidence](../docs/issue-26-evidence.md); independent Standards and Spec
review is in [the review record](../docs/issue-26-review.md).
For deeper method details use [the #17 guide](ISSUE_17_GUIDE.md),
[native comparison guide](ISSUE_21_GUIDE.md) and [technical handout guide](ISSUE_24_GUIDE.md).
[Official EvalScope usage](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html)
corroborates the workflow; pinned code defines this implementation's exact flags.
