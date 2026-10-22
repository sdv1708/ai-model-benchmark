# Issue #19 acceptance evidence

Issue: [Integrate the selected LiveCodeBench pruner into EvalScope](https://github.com/sdv1708/ai-model-benchmark/issues/19).
The user's explicit implementation request authorizes assistant implementation of
this learner-labelled ticket. The detailed explanation is in
[ISSUE_19_GUIDE.md](../task2/ISSUE_19_GUIDE.md).

## Provenance and placement

Both private repositories were updated from main before creating
`feature/issue-19-livecodebench-pruner`. Challenge main was
`5a73f6bac224d7f5743b77f3b38f61060a7c66c7`. Native private main was still the
upstream pin; its issue #18 baseline commit was fast-forwarded into the new
branch before implementation. No history was rewritten.

The actual pruner lives inside private `sdv1708/evalscope-pruning`, not in a
standalone challenge script. [evalscope-lcb.json](../task2/evalscope-lcb.json)
records the exact implementation and source pins plus reference-panel hash.

## Acceptance mapping

| Requirement | Evidence |
| --- | --- |
| `live_code_bench_pruned` available through CLI | Generated lazy registry index; `benchmark-info`; real CLI evaluation writes native predictions/reviews/JSON/HTML |
| Documented strategy and ratio arguments | Native `extra_params` contract, strict typed validation, two historical candidates, ratio `(0,1]` |
| Selected IDs match validated analysis | 1,200 independent native registry/loader parity cases; exact IDs/strata/allocations/weights and historical weighted estimates match |
| Framework tests for valid and invalid configuration | 31 feature tests, including eight invalid ratios, forbidden baselines, malformed panels, incomplete populations, exclusion, repeats and genuine CLI/HTTP paths |
| Upstream conventions | LiveCodeBench inheritance, Pydantic contracts, `load_subset` seam, generated index/docs, Ruff/Mypy/import contracts and feature hooks |

## Measured checks

| Check | Result |
| --- | --- |
| Offline baseline before implementation | Challenge: **129 passed**; native relevant baseline: **75 passed** |
| Final complete Task 2 suite | **129 passed**, plus Ruff check/format and strict Mypy |
| Final relevant native suite plus required upstream CI-lite | **122 passed**, including all 31 feature tests |
| Native type check and Ruff | Passed |
| Architecture import contracts | **5 kept, 0 broken** |
| Upstream hooks on feature files | Passed; nonapplicable YAML/requirements hooks skipped |
| Repository-wide upstream hooks | All pass except the existing Windows symlink-placeholder EOF issue recorded in #18 |
| Independent native-loader parity | **1,200 cases passed**: 600 model holdouts + 600 pair holdouts |
| Public-source identity research | **315/315 unique matches** inside the pinned 880-question source |
| Actual OpenAI-compatible loopback transport and local grading | Three fixed correct programs; weighted population accuracy **1.0**, count **3** |

The initial registry and weighted-estimate tests failed before their implementation
slices. Tests use public configuration/loading/scoring/CLI seams. The ordinary mock
CLI example gives zero accuracy as expected; separate correct/wrong fixed-program
tests and a scripted local HTTP endpoint verify actual extraction and grading.
Windows requires workspace pytest temp folders and normal local worker creation.
The full relevant native command is saved in its `VALIDATION_ISSUE_19.md`.

The repository-wide EOF hook attempts to add a newline to an upstream symlink
placeholder, `.github/copilot-instructions.md`. That isolated incidental change
was inspected and removed. No unrelated upstream fix is included.

## Identity and replay evidence

[Source verification](data/task2-lcb-source-verification.json) records the public
dataset revision and matched population. Question text was recovered from saved
GPT-OSS Harmony input tokens, not guessed from answers. Cross-model identity still
uses the supplied shared index. Source verification reads projected question and
identity columns over HTTP ranges, excluding large hidden-test columns.

[Native parity audit](data/task2-lcb-native-audit.json) records exact agreement and
the full-retention replay scores: 241/315, 198/315, 195/315. Two strategies × five
ratios × twenty seeds × six exclusions = 1,200 cases. Replay loader fixtures have
empty test cases and are never graded. They cannot replace original benchmark
records for fresh-model evaluation.

## Limits and live readiness

The default remains `difficulty_stratified`, ratio **1.0**, selected by issue #17
as the conservative full-reference fallback. Smaller ratios are configurable
research settings, not new GO/NO GO or savings certification. We retain original
LiveCodeBench grading and report ordinary subset metrics separately from the
population-weighted average-attempt estimate.

No model key or paid inference was used. The actual OpenAI-compatible transport
was tested on loopback; external provider behavior and Docker sandbox execution
remain unmeasured here. The native guide includes a credential-free checked-in
configuration and the environment-variable-based live command. AA-LCR and saved-run
comparison remain issues #20 and #21.

## Primary research sources

The pinned source is authoritative for framework behavior. Research checked the
official [benchmark contribution guide](https://evalscope.readthedocs.io/en/latest/advanced_guides/add_benchmark.html),
[LiveCodeBench guide](https://evalscope.readthedocs.io/en/latest/benchmarks/live_code_bench.html),
and [sandbox guide](https://evalscope.readthedocs.io/en/latest/user_guides/sandbox.html),
then read the checked-out adapter, loader, configuration merge, repeat/indexing,
cache and report contracts. The public fingerprint check independently establishes
that recovered questions exist in the exact pinned benchmark source.
