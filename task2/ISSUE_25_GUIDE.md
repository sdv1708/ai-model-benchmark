# Issue #25: explain, operate and defend Handout B

## 1. Start with a school-test story

Imagine you are choosing a robot to help with homework. You have a book of 100
questions. Giving the robot every question is slow, so you try making a shorter
test. A good short test must still help you make the same choice about the robot.
It is not enough for its percentage to look nice.

Our project does that job for two abilities: writing code and answering questions
using long documents. A **benchmark** is the question book. A **pruner** chooses
which questions to keep before asking a model to answer them. **EvalScope** is the
evaluation framework that loads questions, calls models, grades answers and saves
results. A **comparison command** checks the saved full and selected runs.

Handout B is the instruction card for the people using this work. The editable
[half-page handout](HANDOUT_B.md) and [PDF](../output/pdf/handout-b.pdf) say what
the team can do, what to run, what the output means and what to tell a customer.
They do not make the reader learn the selection mathematics first.

## 2. What issue #25 changes

This issue adds communication and operating instructions, not a new pruner or a
new experiment. The native implementation remains in the separate private
[EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning).
Issues #19/#20 supplied the pruners; #21 supplied saved-run comparison; #22/#23
supplied the multimodal proposal and offline prototype. #24 supplied technical
Handout A. #25 translates that work for its users.

| Reader | Practical question Handout B answers |
| --- | --- |
| Developer | Which implementation and command do I use? |
| Test engineer | Which runs are comparable, and what does inconclusive mean? |
| Sales engineer / deployment lead | Can I explain a result against an agreed requirement? |
| Product / customer team | What can we promise, and what still needs validation? |

Handout A explains selection, weighting, validation gates and assumptions.
Handout B starts with the customer conversation, then gives an executable practice
path, interpretation and a next-quarter image-workflow implication. Its different
purpose is why it is more than an abridged Handout A.

## 3. The result you must say honestly

The [selected operating points](../docs/data/task2-operating-selected.json) retain:

| Reference pool | Keep | Remove | Defended sample-count saving |
| --- | --- | --- | --- |
| LiveCodeBench coding | 315 / 315 | 0 | 0% |
| AA-LCR long-context | 100 / 100 | 0 | 0% |

Earlier experiments tried 10%, 20%, 30%, 50% and 100% retention. Every required
score, model-ordering and threshold gate had to pass. None of the smaller tested
candidates passed all gates. Therefore full retention is the defended fallback.
This is a conclusion about this tested grid and retrospective policy; it does
not prove that every possible smaller selection must fail.

Think of trying several shorter school tests: if some change which robot you
would choose, do not promise the short test is ready. Keeping the full test is an
honest engineering result. It does leave the original compression ambition
unmet at a smaller defended size. The framework and experiments still make the
next validation repeatable, but they do not establish evaluation savings.

Do not claim a shorter test saves the same fraction of money or time. Coding
questions have different generation/grading costs; long-document questions have
different token lengths and judging costs. No live cost study was run here.

## 4. Install the exact implementation

Use Git, Python 3.12 and uv; private repository access and internet are needed
for installation. From a parent folder where the new clone does not exist:

```powershell
git clone https://github.com/sdv1708/evalscope-pruning.git
cd evalscope-pruning
git checkout 5fd26289972f6d01b13ea95bb30481ebd103fa2d
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements/pruning-baseline.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
. ./.venv/Scripts/Activate.ps1
python -m evalscope.cli.cli benchmark-info aa_lcr_pruned
```

The dependency snapshot was verified on Windows/Python 3.12. On another platform
follow the fork's `PRUNING_BASELINE.md` and revalidate. If PowerShell disallows
activation, use `./.venv/Scripts/python.exe` instead of `python` below; no machine
policy change is necessary. After activation, confirm `python` uses that environment.
These instructions assume PowerShell 7 for native JSON argument passing.

The extension commit above includes both native pruners and comparison. Its
upstream base is `66f0945d145ce6c30de40253cd78144003c6f1fe`, as recorded in
[the comparison lock](evalscope-compare-runs.json). A pin is a precise saved
version, like a book edition: it keeps tomorrow's changed APIs out of this recipe.
This submission repository's `task2` environment is a different package and
does not install the native EvalScope extensions.

## 5. Run the handout's credential-free practice

From the installed EvalScope fork root, with its environment active:

```powershell
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/handout-b
if ($LASTEXITCODE -ne 0) { throw 'Synthetic evaluation failed' }
python -m evalscope_ext.tools.compare_runs `
  --full outputs/handout-b/full --pruned outputs/handout-b/pruned --threshold 0.8
if ($LASTEXITCODE -ne 0) { throw 'Saved-run comparison failed' }
```

Use a fresh output directory; if that name already exists, change it in both
commands. The first command starts a loopback fixture that impersonates a model
and judge, runs the real native evaluator twice, then compares. The second
command shows how to compare those saved runs again without inference.
The fixture needs no provider credential and makes no paid provider calls.

Expected values, also recorded in [the #21 smoke output](../docs/data/task2-run-comparison-smoke.json):

| Output | Value | Meaning |
| --- | --- | --- |
| `full_samples` / `pruned_samples` | 12 / 3 | Unique questions, not attempts |
| `full_score` / `pruned_score` | 1.0 / 1.0 | Both observed scores are 100% |
| `difference_pp` | 0.0 | No observed percentage-point difference |
| `finite_pool_bounds` | [0.25, 1.0] | Possible full-pool completion from subset evidence |
| `decision.full` | GO | Full recorded result meets example 80% threshold |
| `decision.pruned` | inconclusive | Subset cannot establish that result |
| `decision.observed_pruned_point` | GO | Point-only answer; insufficient for the bound decision |
| `decision.decision_certified` | false | No production certification |

The output has an empty `ordering` list because only one candidate model ran.
That is not an error. Two matching models are needed for an ordering comparison.
This synthetic 75% question reduction proves that the plumbing works. It says
nothing about safe compression for a real model or real long documents.

## 6. Why 100% can still mean inconclusive

You checked 3 of 12 answers; all 3 passed. You do not know the other 9.

- Worst case: all 9 fail. The complete score is 3/12 = 25%.
- Best case: all 9 pass. The complete score is 12/12 = 100%.

An 80% requirement sits between 25% and 100%, so the answer is **inconclusive**.
The subset must not borrow the unselected full-run grades to make itself look
certain; that would defeat the purpose of evaluating fewer questions.

For observed question means summing to S, n observed questions and N total:

```text
lower = S / N
upper = (S + N - n) / N
```

These are deterministic **completion bounds**, not 95% confidence intervals.
They describe what unseen answers could do in this fixed pool. Earlier offline
policy experiments used a separate finite-pool statistical interval construction.
Do not mix those two kinds of uncertainty in an interview.

| Bound and required accuracy | Command's conclusion | Operational response |
| --- | --- | --- |
| [82%, 95%], requirement 80% | GO | Consider a customer-workload pilot, with stated limits |
| [50%, 79%], requirement 80% | NO GO | Candidate misses the benchmark requirement; investigate alternatives |
| [75%, 90%], requirement 80% | inconclusive | Collect more evidence; do not convert to a sales yes |
| [80%, 80%], requirement 80% | GO | Equality meets the requirement |

Exit 0 means the comparison ran successfully. Exit 2 means invalid/incompatible
input; inspect stderr and fix the evidence before interpreting any result.
Without `--threshold`, the tool supplies no threshold decision. A point estimate
is useful but does not replace the bound decision. GO remains conditional on the
benchmark, recorded grades and fixed settings. It does not establish production
reliability, safety, latency or customer-distribution coverage.

## 7. Real endpoint runbook

The following are executable command templates for the pinned fork, not records
of real inference performed for #25. Provider access, sufficient context, real
benchmark data, a configured coding sandbox and budget are prerequisites. Replace
provider identifiers and set API keys securely in environment variables. Agree
customer requirements before looking at outputs. Run each benchmark separately;
this CLI takes one threshold for every pair in an invocation.

Set `EVAL_MODEL`, `EVAL_API_URL` (provider base URL ending in `/v1`) and
`EVAL_API_KEY`. Point `LCB_REFERENCE_PANEL` and `AA_LCR_PANEL` at the absolute
paths to this submission's `task2/data/lcb-reference-panel.json` and
`task2/data/aa-lcr-reference-panel.json`. AA-LCR also needs `JUDGE_MODEL`,
`JUDGE_API_URL` and `JUDGE_API_KEY` for a separately specified judge. Keep actual
secret values out of documents and Git. Do not print command/config evidence
containing secrets when sharing the run.

For a model alias matching a historical reference, add its canonical name to
`excluded_reference_models` under `extra_params` on both sides; native automatic
exclusion uses actual/display names and cannot infer arbitrary aliases.

### Coding: full frozen reference and an explicit research subset

Install the fork's sandbox extra and configure the supported Docker sandbox using
its `LIVE_CODE_BENCH_PRUNED.md` and the
[official sandbox guide](https://evalscope.readthedocs.io/en/latest/user_guides/sandbox.html).
Use original questions **with grading test cases** from the pinned source.
Historical `Evals/` outputs and empty-test loader fixtures cannot grade new code.

```powershell
# Full retention is the defended setting. 0.5 is a research comparison only.
# For a defended candidate run, replace the second ratio with 1.0 (no saving).
foreach ($run in @(@{name='full'; ratio=1.0}, @{name='candidate'; ratio=0.5})) {
  $datasetArgs = @{
    live_code_bench_pruned = @{
      subset_list = @('release_v5')
      extra_params = @{
        pruning_strategy = 'difficulty_stratified'
        prune_ratio = $run.ratio
        reference_path = $env:LCB_REFERENCE_PANEL
      }
    }
  } | ConvertTo-Json -Depth 5 -Compress
  python -m evalscope.cli.cli eval `
    --model $env:EVAL_MODEL --eval-type openai_api `
    --api-url $env:EVAL_API_URL --api-key $env:EVAL_API_KEY `
    --datasets live_code_bench_pruned --dataset-hub huggingface `
    --dataset-args $datasetArgs --sandbox '{"enabled":true}' `
    --seed 42 --no-timestamp --work-dir "outputs/hb-lcb-$($run.name)"
  if ($LASTEXITCODE -ne 0) { throw 'Coding evaluation failed' }
}
# 0.7 is illustrative; replace it with the requirement agreed beforehand.
python -m evalscope_ext.tools.compare_runs `
  --full outputs/hb-lcb-full --pruned outputs/hb-lcb-candidate --threshold 0.7
if ($LASTEXITCODE -ne 0) { throw 'Coding comparison failed' }
```

The panel chooses 315 of the pinned release's 880 source questions; those are
different populations. At ratio 0.5, ceil(315 x 0.5) = 158 questions remain.
Using the same reference adapter with ratio 1.0 for the full side preserves
the frozen population and provenance. `prune_ratio` means **fraction retained**.
Do not apply `--limit`; it destroys the selection/weighting contract and is rejected.

### Long-context: same procedure, plus a fixed judge

AA-LCR downloads pinned historical v1.0 question data and document texts. Its
roughly 72k-115k benchmark-token contexts require a suitable model context limit;
those metadata counts are not provider billing counts. Preflight context and
output settings for the candidate and use identical generation settings across
both runs. The pinned adapter follows `data_source_filenames` document order.
Do not substitute v1.1 answers or new judging rules into this comparison.

```powershell
$judge = @{
  strategy = 'llm'
  models = @(@{
    model_id = $env:JUDGE_MODEL
    eval_type = 'openai_api'
    api_url = $env:JUDGE_API_URL
    api_key = $env:JUDGE_API_KEY
  })
} | ConvertTo-Json -Depth 5 -Compress
foreach ($run in @(@{name='full'; ratio=1.0}, @{name='candidate'; ratio=0.5})) {
  $datasetArgs = @{
    aa_lcr_pruned = @{
      extra_params = @{
        reference_path = $env:AA_LCR_PANEL
        pruning_strategy = 'length_difficulty_stratified'
        prune_ratio = $run.ratio
      }
    }
  } | ConvertTo-Json -Depth 5 -Compress
  python -m evalscope.cli.cli eval `
    --model $env:EVAL_MODEL --eval-type openai_api `
    --api-url $env:EVAL_API_URL --api-key $env:EVAL_API_KEY `
    --datasets aa_lcr_pruned --dataset-hub huggingface --judge $judge `
    --dataset-args $datasetArgs --seed 42 --no-timestamp `
    --work-dir "outputs/hb-lcr-$($run.name)"
  if ($LASTEXITCODE -ne 0) { throw 'Long-context evaluation failed' }
}
# 0.6 is illustrative; replace it with the requirement agreed beforehand.
python -m evalscope_ext.tools.compare_runs `
  --full outputs/hb-lcr-full --pruned outputs/hb-lcr-candidate --threshold 0.6
if ($LASTEXITCODE -ne 0) { throw 'Long-context comparison failed' }
```

Use fresh directories for every experiment. `--no-timestamp` makes paths exact;
otherwise point the comparator at the actual timestamp directory. Each native
root needs `configs/task_config.yaml`, `reports/` and complete `reviews/`.
Match model, source, prompt, generation, judge, repetitions and sandbox settings.
Missing grades and mismatched inputs are errors, not zeroes to average away.
The comparison reads saved files and does not make endpoint calls.

Both coding and long-context requirements must be considered for the customer;
there is no automatic cross-benchmark release decision. If either required
capability is inconclusive, the combined quality evidence is insufficient.
A GO on both still needs customer-task and production-performance validation.

## 8. Why the average needs weights

Suppose a question book has 2 small-group and 6 large-group questions. We select
one from each group. The small-group answer fails; the large-group answer passes.
A plain selected average says 1/2 = 50%.

But the groups represent different shares of the original book. The estimate is
0 x (2/8) + 1 x (6/8) = **75%**. Weighting restores population proportions after
unequal allocation. The native comparator reports the weighted estimate and
ordinary subset mean separately, and validates the group counts and provenance.
Correct weights do not establish that an unseen model behaves like past models.

## 9. Why the long-document judge is another uncertainty

Coding uses program tests. AA-LCR asks an LLM judge whether a generated answer
agrees with the reference. Think of a teacher who might grade the same answer
differently on another day. One saved verdict cannot reveal that variation.

Retaining all questions removes uncertainty about unobserved questions in the
recorded pool, but it does not fix judge error or variable generated answers.
Repeating generation asks the candidate to answer again. Repeated judging of a
fixed saved answer is a different experiment. Human review is also needed to
study systematic judge bias. Our evidence has not measured that judge variance.

## 10. What images add next quarter

A random draw may miss the tiny chart labels that matter to a customer's product.
The proposed probe deliberately covers visual challenges and makes matched
comparisons: keep the question fixed, change one visual condition, compare the
answer. A correctly designed random sample is useful for estimating averages;
it does not guarantee coverage of rare visual failure modes or isolate them.

Example: the robot reads a chart correctly at original size but misreads a thin
line after mild blur. Two independent reviewers must confirm the relevant line
is still readable and the correct answer has not changed. If blur removes the
evidence, that is a destructive control, not proof of bad robustness.

Add a no-image control, an equivalent-factual-text control and visual-fact
extraction. These help ask whether the model actually needed the image and
whether failure occurred before or after reasoning over the relevant facts.
The motivation is supported by the [MMStar research paper](https://arxiv.org/abs/2403.20330),
which shows that some benchmark questions can be answered without visual input.
It does not validate our proposed panel sizes or transformation strengths.

The [pinned official MMMU source](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md)
lists 150 development + 900 validation + 10,500 test questions = **11,550** across
30 subjects. The supplied 660 rows are illustrative references, not that full pool.
The [design proposal](MMMU_PROBE_DESIGN.md) targets the full inventory and separates
weighted estimation from deliberate diagnostic coverage. These two panels must
not be pooled as an unweighted population score.

The [existing harness](MMMU_HARNESS.md) makes deterministic image variants,
request plans and saved-response diagnostics. Its demo is synthetic. It does not
call a live model, execute the proposed text controls or establish that an encoder
is good enough. End-to-end API behavior implicates the visual path (including
image preprocessing and downstream reasoning); **encoder causality** needs an
experiment changing only the encoder. Missing responses remain unknown.

No video is needed to use either handout or this guide. Issue #25 is a written
deliverable. Separately, the [overall submission README](../README.md) still
requires walkthrough videos; written materials do not fulfill that requirement.

## 11. An interview answer you can actually defend

"I built an evaluation workflow that tries to reduce questions while preserving
the decisions a customer cares about. The native pruners and comparison live in
a pinned EvalScope-derived repository. My current evidence supports full retention,
so I do not claim compression savings. Handout B turns that into an operating
recipe: agree requirements, run matched evaluations, inspect the weighted score
and completion bounds, and collect more evidence when the result is inconclusive.
For future image workloads, I propose targeted paired stress tests and controls,
while separating synthetic prototype checks from real model-quality evidence."

Practise these follow-up questions out loud:

| Interviewer asks | Answer to build from |
| --- | --- |
| Why is 0% pruning useful? | It prevents an unsupported shortcut; the smaller defended solution remains an open research goal. |
| Why not choose 50% anyway? | Smaller tested candidates failed score, ordering or decision gates; convenience is not validation. |
| Why can 100% observed accuracy be inconclusive? | Three observed passes leave nine unknown grades; show 25-100% completion bounds. |
| Is GO a release approval? | No. It is conditional benchmark evidence; validate customer tasks, judge quality and production needs. |
| What is the difference between accuracy and decision fidelity? | One is a score; the other asks whether changing the test changes the action. |
| What happens if a command exits successfully? | The comparison completed. Read `decision.pruned`, bounds and warnings for its conclusion. |
| Why compare the same adapter at ratio 1.0? | It fixes the original population and preserves selection provenance. |
| Why pin source and implementation? | Different versions can change questions, prompts, grading and flags. |
| What does weighting solve? | Unequal representation of strata; it does not prove model transfer. |
| Why should a PM care? | Acceptance criteria, evidence budgets and rollout promises become explicit and challengeable. |
| What does a random image sample miss? | It may omit rare stress types; targeted paired testing diagnoses specific visual sensitivity. |
| Can you claim the encoder is broken? | Only visual-path sensitivity from these API comparisons; encoder-only causality needs a controlled component change. |
| What would you do with a live endpoint? | Freeze requirements and policy, test an untouched model, repeat generation/judging, audit failures and measure actual costs. |

## 12. What was verified for this issue

The [acceptance evidence](../docs/issue-25-evidence.md) records the exact base,
artifact bounds, command checks, research and full Task 2 regressions. The
[independent review](../docs/issue-25-review.md) reports Standards and Spec
separately. New paid inference is not required for this documentation issue and
was not performed. Real endpoint command templates require provider preflight;
synthetic fixture success cannot validate a real provider's model capabilities.
