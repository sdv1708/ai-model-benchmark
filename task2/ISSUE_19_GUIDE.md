# Issue #19: run the coding selector inside EvalScope

## What this ticket is for

Earlier tickets asked whether a shorter coding exam could represent the complete
recorded exam. They implemented experiments over answers that already existed.
Issue #19 puts that selection method into the system that can actually ask a new
model the selected questions and grade its generated programs.

Without this integration, the analysis can say which questions it would retain,
but a deployment engineer still has to manually connect selection, inference,
grading and reports. Now the engineer selects `live_code_bench_pruned` through
EvalScope's normal CLI. The standard framework does the rest.

The implementation lives in the private
[sdv1708/evalscope-pruning](https://github.com/sdv1708/evalscope-pruning) repository.
This challenge repository contains the historical panel, reproducible export/audit
tools, acceptance evidence and this explanation. Both use branch
`feature/issue-19-livecodebench-pruner`. The machine-readable integration lock
records the native implementation version. Upstream remains pinned to
`66f0945d145ce6c30de40253cd78144003c6f1fe`.

## The important limitation: no validated savings yet

Issue #17's conservative policy found no smaller tested coding subset that passed
every score, ranking and customer-decision gate. Its selected strategy is
`difficulty_stratified` with a **1.0 retained fraction: all 315 recorded tasks**.
That is the native adapter's default. This ticket does not change the statistical
result by making an experiment runnable.

Smaller ratios are configurable for research. At 0.5, `ceil(315 * 0.5) = 158`
questions are retained, about half as many generation requests at repeats=1.
That is a count reduction, not validated customer-decision fidelity or measured
latency/billing savings. Near-tied models can change order even when approximate
scores look close. Use the earlier uncertainty analysis and fresh validation
before treating an experimental score as a customer GO/NO GO decision.

## How the pipeline works

```text
TaskConfig / evalscope eval
  -> native registry resolves live_code_bench_pruned
  -> validate strategy, retained ratio and integer seed
  -> read frozen historical reference panel
  -> exclude the evaluated model before creating historical strata
  -> standard loader reads and date-filters original coding records
  -> match the complete 315-question population by question fingerprint
  -> allocate the retained budget and select stable original indices
  -> attach strata, weights and provenance; shuffle and repeat if requested
  -> inherited LiveCodeBench prompts and ordinary model transport
  -> inherited code extraction and original test-case grading
  -> standard predictions/reviews plus raw subset and weighted population metrics
```

The adapter overrides the established `load_subset` seam rather than the evaluator
or model client. It inherits LiveCodeBench's prompt and grading implementation.
Fresh grading therefore still needs original test cases; reading old binary grades
does not substitute for running a new model's generated programs.

## Why fingerprints were necessary

The supplied coding artifacts use indices 0–314 but omit original problem IDs and
question text. Their line order is shuffled, and modern source datasets may have
different ordering or more questions. Treating source row 27 as historical index
27 would attach historical grades to an arbitrary question.

The GPT-OSS prediction records preserve the original input token IDs. Decoding
them with `tiktoken 0.14.0 / o200k_harmony` recovers the question text. This is
deterministic text decoding; it does not ask a model to reconstruct a question.
Normalize line endings and outer whitespace, then hash the UTF-8 question with
SHA-256. The panel binds that fingerprint to its original analysis index and
three recorded grades. Six source-file hashes record provenance.

All 315 fingerprints were independently matched uniquely to real questions in
the pinned public Hugging Face `release_v5` dataset, revision
`e70df9620dd54c12afac5e2881355de6f9ece2e9`. That source has **880** questions;
the adapter evaluates only the frozen 315. Matching uses question content, not
current row positions. The shared historical index across models remains an
assumption of the supplied data, since their original IDs were not provided.

Every panel question must appear exactly once after source/date eligibility.
Missing questions, duplicate matches and malformed panels fail before inference.
This prevents a source update or date filter from silently changing the exam.

## Selection, worked through

`difficulty_stratified` groups questions by how many reference models passed.
With two historical references, groups are `passes:0/2`, `passes:1/2` and
`passes:2/2`. `response_stratified` instead keeps the whole pattern: `[0, 1]`
and `[1, 0]` are separate groups. These are the two previously evaluated methods;
uniform random, easiest-only and hardest-only cannot be configured as production
strategies.

1. Compute `budget = ceil(population_size * prune_ratio)`. The argument is the
   fraction retained, despite the name `prune_ratio`.
2. Give each occupied group one slot. Fail if the budget cannot cover all groups.
3. Allocate each remaining slot to the largest deficit from proportional coverage.
4. Within a group, select the lowest SHA-256 priorities of
   `lcb-pruning-v1:{seed}:{original_index}`.
5. Return selected questions sorted by original analysis index before optional
   execution shuffling.

This exactly preserves the analysis hash domain, lexical ties, rounding and
allocation. Reordering source rows or panel rows cannot change the selected IDs.
Changing a held-out model's grades cannot change its selection, because those
grades are excluded first. Canonical model names are automatically excluded;
endpoint aliases should explicitly exclude the historical canonical name too.

## Why the score needs weights

Integer allocation can make the selected exam's proportions differ from the
original. Suppose a population has 20 questions of one type and 80 of another,
but a subset retains five of each. Equal averaging incorrectly treats the types
as equally common. If their accuracies are 80% and 40%, the raw mean is 60%,
while the population-weighted estimate is `0.2 * 80% + 0.8 * 40% = 48%`.

For group `h`, each retained question gets weight `N_h / (N * n_h)`. Its
contribution is that weight times its binary grade. With repeated attempts, average
the grades for each original question first, then apply its weight once.

The primary native report identity is:

```text
accuracy / weighted_mean / {scope: population}
```

Ordinary unweighted subset mean and pass@k remain separate metrics. The weighted
estimate represents average-attempt accuracy, not population pass@k for k > 1.
Missing grades/questions/repeat positions cannot silently receive renormalized
weights. `--limit` is rejected for this adapter because truncating a selected
sample would invalidate its design. Reports retain the panel hash, original
indices, strata, weights, seed, strategy and reference-model identities.

## Run it offline

Install the private native checkout using its `PRUNING_BASELINE.md`, then from that
repository root:

```powershell
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info live_code_bench_pruned
.venv/Scripts/python.exe -c "from evalscope import run_task; run_task('examples/live_code_bench_pruned/task.json')"
.venv/Scripts/python.exe -m pytest tests/api/test_live_code_bench_pruned.py --basetemp=.pytest-tmp/coding
```

The bundled example has six synthetic questions and selects three. The mock model
does not solve them, so its zero score is expected. Correct/wrong fixed-program
tests separately check real grading. A loopback OpenAI-compatible endpoint test
exercises HTTP generation and grading without any external API key. Allow local
Python multiprocessing workers when running grading tests on Windows.

## Reproduce the panel and 1,200-case parity audit

From this challenge repository's `task2/`, the panel export alone can run with:

```powershell
uv sync --locked --extra integration
uv run --extra integration python tools/export_lcb_panel.py --data-root ../Evals --output output/issue19/lcb-reference-panel.json
```

The optional pinned tokenizer dependency is not needed for ordinary offline
analysis. Its first vocabulary fetch requires internet; later cached decoding is
offline. The checked-in `data/lcb-reference-panel.json` avoids that setup for
native evaluation. Exported panel JSON uses stable sorted keys and LF endings.

The native parity and optional public-source checks need the installed private
EvalScope environment. With sibling checkout locations, from `task2/`:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$nativePython = '../../evalscope-issue-18/.venv/Scripts/python.exe'
& $nativePython tools/audit_evalscope_lcb.py --data-root ../Evals --panel data/lcb-reference-panel.json --output output/issue19/native-audit.json
& $nativePython tools/verify_lcb_source.py --panel data/lcb-reference-panel.json --output output/issue19/source-verification.json
```

Adjust the native checkout path on another machine. The audit covers two
strategies × five ratios × twenty seeds × six exclusion folds = **1,200** native
registry/loader selections. It compares exact IDs, strata, allocation counts,
weights and replayed population estimates against independent analysis. Its
reconstructed questions have empty test cases solely to exercise the loader;
they are never graded and must not be used for fresh evaluation. Source
verification projects question/identity parquet columns over HTTP byte ranges,
excluding large hidden-test columns. It makes no model call.

## Run a fresh model

The native [LIVE_CODE_BENCH_PRUNED.md](https://github.com/sdv1708/evalscope-pruning/blob/feature/issue-19-livecodebench-pruner/LIVE_CODE_BENCH_PRUNED.md)
contains the full PowerShell command. Provide a model ID, OpenAI-compatible API
URL/key, the local reference panel and a functioning upstream Docker sandbox.
Use `eval_type=openai_api`; model transport is the existing EvalScope transport.
Start with the defended 1.0 ratio or explicitly mark a smaller run experimental.
Keys belong in environment variables and are not checked in.

The recorded full scores reproduced by historical replay remain:

| Model | Successes | Full mean |
| --- | ---: | ---: |
| GPT-OSS-120B | 241 / 315 | 76.51% |
| Kimi-K2.5 | 198 / 315 | 62.86% |
| MiniMax-M2.5 | 195 / 315 | 61.90% |

A new endpoint can produce different answers. No paid benchmark inference,
fresh-model quality claim or new compression certification is included here.
Live provider behavior, Docker integration and actual latency/billing still need
a real run. Issue #20 adds AA-LCR integration; issue #21 adds saved-run comparison.

The only paid calls in this ticket translated the generated benchmark documentation
into Chinese with the user-authorized OpenAI key. They did not evaluate a model's
coding capability. The final native suite has 123 passing tests, including a
regression for model objects whose underlying name differs from their display ID.

## Practice explaining the work

- Why can a runnable 50% ratio still be unsuitable for customer decisions?
- Why is a source row number an unsafe substitute for the recorded index?
- What does automatic reference exclusion prevent, and what changes for aliases?
- Why do per-question weights sum to one, even with repeated attempts?
- Which benchmark behavior is inherited, and which loading behavior is new?
- What do the 1,200 offline checks establish, and what requires a fresh endpoint?
