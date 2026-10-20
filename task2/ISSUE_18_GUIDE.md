# Issue #18: putting the pruning work inside EvalScope

## What problem does this issue solve?

Imagine an exam with 315 coding questions. Running every question on every new
AI model costs time and money. Earlier issues studied whether a smaller exam
could still support the same customer decision. That research is useful, but
an engineer needs to run it through the actual evaluation system.

EvalScope is that system. It loads questions, formats model requests, calls a
model, grades answers, and writes results. Issue #18 establishes a maintained,
reproducible place inside EvalScope for the later pruning implementations.

Think of earlier analysis as designing an exam on paper. This issue connects a
small practice exam to the school's real exam administration system. It proves
the connection works; it does not establish that the practice exam measures a
real student's ability accurately.

## What was created?

- A private development repository, [sdv1708/evalscope-pruning](https://github.com/sdv1708/evalscope-pruning),
  derived from [modelscope/evalscope](https://github.com/modelscope/evalscope).
- An exact upstream base: `66f0945d145ce6c30de40253cd78144003c6f1fe`.
  Git history, the Apache-2.0 license, and original source attribution are retained.
- A feature branch named `feature/issue-18-evalscope-baseline` in both repositories.
- A registered synthetic `pruning_smoke` benchmark in EvalScope's own package.
- Tests through the registry, dataset loader, and real CLI, with local toy data
  and EvalScope's mock model instead of a paid endpoint.

The machine-readable [baseline lock](evalscope-baseline.json) records the exact
private implementation commit. The implementation lives in that repository;
this challenge repository holds the research, learning guide, and evidence.

## The important terms

| Term | Meaning here |
| --- | --- |
| Benchmark | An exam for an AI model: questions plus a grading procedure. |
| Dataset | The actual collection of questions. |
| Pruning | Selecting fewer questions from a larger collection. |
| Adapter | Code that teaches EvalScope how a particular benchmark fits its standard pipeline. |
| Registry | EvalScope's directory of available benchmarks, addressed by names such as `pruning_smoke`. |
| Extension seam | A supported place to change one part of the pipeline while reusing the surrounding framework. |
| Commit pin | An exact saved source-code version, rather than the changing name `main`. |
| Smoke test | A small test proving the connected system runs end to end. It does not prove statistical fidelity. |
| Stratum | A group of questions sharing a property; the toy example uses easy, medium, and hard. |

## A six-question example

The synthetic dataset has six questions: two easy, two medium, and two hard.
With `keep_per_stratum=1`, the adapter retains one question from each group,
so EvalScope sends three questions to its model backend instead of six.

Within each group, a hash of the seed, group name, and stable question ID
determines which question is retained. A hash is a repeatable way to assign a
priority: the same inputs give the same priority. Rearranging file rows does
not change the chosen IDs. Answers and model scores do not influence selection.

The smoke policy is deliberately small. Its fixed per-group allocation is not
the validated LiveCodeBench or AA-LCR strategy. With uneven groups, the ordinary
mean over selected questions need not estimate the full-population mean. This
benchmark's report is only a synthetic subset score. No customer GO/NO GO result
or production compression ratio is certified by it.

The mock model returns a fixed text response. Getting a low score in this run
is expected: we are testing that requests, grades, and reports travel through
the framework, rather than testing model intelligence.

## Where does the new code connect?

The selected seam is the benchmark adapter's `load_subset(subset, data_loader)`
method. The adapter extends `DefaultDataAdapter`; it does not replace the CLI,
evaluator, model transport, grader, or report generator.

The path is:

```text
evalscope eval / TaskConfig
  -> benchmark registry resolves pruning_smoke
  -> standard local loader reads the complete eligible subset
  -> adapter selects stable IDs, retaining every occupied stratum
  -> optional shuffle and limit
  -> framework repeat helper and reindexing
  -> normal prompt processing, model calls, scoring, and reports
```

Why this order? Suppose six questions become three selected questions and
`repeats=2`. We want two attempts at each selected question: six model requests
in three repeat groups. Selecting after repeats would risk choosing individual
attempts rather than questions. Likewise, a limit of one must truncate the
selected set rather than change the population from which selection is made.
A limit can remove coverage, so it is only useful for debugging this smoke path.

There are two kinds of IDs. `record_id` identifies the original question and
survives selection and row reordering. EvalScope assigns fresh sequential
`sample.id` and `group_id` values for execution and repeated-attempt grouping.
Those execution IDs are not substitutes for original question identity.

## Alternatives considered

| Option | Decision |
| --- | --- |
| A standalone script that writes a smaller file | Insufficient: it would not establish an in-framework integration. |
| EvalScope's `--limit` | Useful for debugging, but a prefix limit does not implement a defended pruning method. |
| `record_to_sample` | Correct place for format conversion and stable metadata; too narrow for selecting from a whole population. |
| `sample_filter` alone | Useful for independent eligibility rules, but does not provide the complete pool needed for allocation. At the pinned revision, loaders also apply limits and repeats before this filter. |
| Override the entire `load` or evaluator | Too broad: would duplicate hub handling or downstream evaluation behavior. |
| A new core-wide pruning API now | Premature for a minimal baseline; benchmark adapter behavior can be tested first without changing all benchmarks. |
| Adapter-level `load_subset` | Selected: population-aware and before inference, while retaining standard loaders and downstream execution. |

Later adapters should inherit benchmark-specific behavior where appropriate:
LiveCodeBench's prompt and sandbox grading, and AA-LCR's judge contract. Those
semantics must not be replaced by the toy exact-match metric used here.

## Try the integration

Use Git, uv, Python 3.12, and GitHub access to the private repository. From a
parent directory where you want the checkout:

```powershell
git clone --branch feature/issue-18-evalscope-baseline https://github.com/sdv1708/evalscope-pruning.git
cd evalscope-pruning
# Read task2/evalscope-baseline.json in the challenge repository first.
# Check out its extension_commit for the exact reviewed implementation.
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e .
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info pruning_smoke
.venv/Scripts/python.exe -m evalscope.cli.cli eval --model pruning-smoke-mock --eval-type mock_llm --datasets pruning_smoke --work-dir outputs/pruning-smoke
```

The CLI defaults and supplied JSON configuration select one question per group,
use the mock
model, and writes ordinary EvalScope result directories beneath
`outputs/pruning-smoke/`. No model API key, GPU, or benchmark download is required
for the smoke run. Initial package installation does require internet access.
To run the editable JSON task configuration through the same framework:

```powershell
.venv/Scripts/python.exe -c "from evalscope import run_task; run_task('examples/pruning_smoke/task.json')"
```

See `PRUNING_BASELINE.md` in the private repository for the full development and
verification instructions, dependency snapshot, and source-level seam pointers.

## What remains for later issues?

Issue #19 adds the required `live_code_bench_pruned` benchmark with the selected
coding strategy and ratio arguments. Issue #20 adds the corresponding AA-LCR
integration and its judge-noise limitations. Issue #21 compares full and pruned
EvalScope output directories. This foundation deliberately leaves those names
and production interfaces to those tickets.

Issue #17 found that no smaller tested candidate satisfied all its illustrative
decision gates: its selected operating points retain all 315 coding and 100
AA-LCR questions. Integrating code into a framework does not change that finding.
Any later claim of useful compression still needs supporting evidence.

## Research sources

The checked-out source at the pinned SHA is the authority when current docs
change. The official [benchmark contribution guide](https://evalscope.readthedocs.io/en/latest/advanced_guides/add_benchmark.html)
explains the adapter pipeline and registration. The upstream
[benchmark discovery source](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/benchmarks/__init__.py)
defines lazy loading and the generated index. The
[default adapter](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/api/benchmark/adapters/default_data_adapter.py)
and [dataset loader](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/api/dataset/loader.py)
establish operation order. The existing
[LiveCodeBench adapter](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/benchmarks/live_code_bench/live_code_bench_adapter.py)
shows the benchmark-specific prompting and grading that the later coding
integration should preserve.
