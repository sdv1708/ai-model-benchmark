# Issue #20 acceptance evidence

Issue: [Integrate the selected AA-LCR pruner into EvalScope](https://github.com/sdv1708/ai-model-benchmark/issues/20).
The user's explicit implementation request authorizes assistant implementation of
this learner-labelled ticket. The [learning guide](../task2/ISSUE_20_GUIDE.md)
explains the concepts, implementation, evidence and interview questions.

## Placement and provenance

Fetched both repositories, fast-forwarded each main, and created
`feature/issue-20-aalcr-pruner` in both clean checkouts. Challenge base is
`c0851e5`; private EvalScope base is `3e850321`. The preserved upstream framework
pin remains `66f0945d145ce6c30de40253cd78144003c6f1fe`.

The real adapter lives in private `sdv1708/evalscope-pruning`, not a challenge
side script. [The lock](../task2/evalscope-aa-lcr.json) records its implementation
commit, source revision and panel hash. Both feature branches are local.

## Acceptance mapping

| Requirement | Evidence |
| --- | --- |
| Dataset available through the documented framework path | Native `aa_lcr_pruned` registry/index, generated metadata/docs, CLI/OpenAI-compatible loopback smoke with a separate judge |
| Defended configuration deterministic | `length_difficulty_stratified`, retained fraction 1.0; exact parity across 1,200 cases, including experimental ratios |
| Judge-noise assumptions near user behavior | Adapter description, runtime weighted-metric metadata, native usage guide and learner guide |
| Framework-level valid/invalid configuration tests | Registry/loader/scoring/CLI tests cover ratios, strategies, budgets, source drift, identities, repeats, target exclusion and judge failures |
| Upstream conventions | Inherits AA-LCR, native loader seam, Pydantic contracts, shared allocation/weighting, lazy index, generated docs, feature Ruff/Mypy/hooks and architecture checks |

## Research before implementation

Read the official [AA-LCR release](https://artificialanalysis.ai/articles/announcing-aa-lcr),
[dataset card](https://huggingface.co/datasets/ArtificialAnalysis/AA-LCR),
[EvalScope AA-LCR documentation](https://evalscope.readthedocs.io/en/latest/benchmarks/aa_lcr.html),
[benchmark contribution guide](https://evalscope.readthedocs.io/en/latest/advanced_guides/add_benchmark.html),
and pinned local loader/adapter/judge/metric contracts. Read prerequisite issues
#1, #17 and #18, earlier analysis and issue #19 implementation.

Research identified AA-LCR v1.1 answer/judge changes. Historical evidence uses
the pinned v1.0 source `bdae010bbce259820c0e34c1d7cce210d966fb75`; cross-version
leaderboard comparison is invalid. Remote runs require the pinned Hugging Face
source; local mirrors are still fingerprint/metadata validated.

The 145,272-byte public metadata CSV matches all 100 questions: 95 exact strings,
five through the exact reversible UTF-8-decoded-as-Mac-Roman transformation.
Indices 4, 20, 61, 64 and 80 and source/input hashes are recorded in the frozen
panel's provenance. Token counts and URL sets match all 100. Runtime uses official
question hashes without fuzzy repair. Context follows declared filename order and
fails on missing/empty files. These prompt corrections mean fresh scores must
not be called exact historical prompt replay.

## Selection and scoring evidence

[Native audit](data/task2-aa-lcr-native-audit.json): **1,200 cases passed**.
Two strategies x five ratios x twenty seeds x six exclusions. IDs, strata,
population/retained counts, weights, excluded-reference effects and replay scores
match the independent analysis implementation. Full retention reproduces
**48/100, 66/100, 64/100**. The fixtures contain tiny synthetic contexts and are
never inferred or judged.

The genuine CLI smoke uses loopback OpenAI-compatible model and judge endpoints,
checks native predictions/reviews/JSON/HTML and returns weighted accuracy 1.0 on
three synthetic selected questions. It is integration evidence, not model quality.
No paid model/judge calls were made.

The user agreed to registry/configuration-loader and scoring/CLI test seams.
The initial registry test failed because the new benchmark was absent. Tests
exercise the public framework interfaces rather than selector internals. A separate
known-answer weighted example distinguishes subset accuracy 1/3 from population
estimate 2/3. Missing/nonbinary/excluded grades fail the weighted estimate closed.

The [real-source load check](data/task2-aa-lcr-source-loading.json) also loaded
all 100 original questions and document contexts through the native CSV-mirror
path, without inference. It verifies the pinned archive and CSV hashes.
Review found CSV token fields needed strict decimal conversion, and the archive
omits UTF-8 flags for four filenames, one additionally decomposed. Exact encoding
resolution and the CSV loader have a red-green public regression. Unknown or
ambiguous files still fail; no fuzzy identity/content matching is used.

## Validation and limits

Complete challenge Task 2 suite: **129 passed**, Ruff check/format passed,
strict Mypy passed for **34 files**. The native final suite passed **208 tests**, including **33 AA-LCR feature cases**.
The framework reproduction command
are recorded in the private repository's `VALIDATION_ISSUE_20.md`.

The first expanded framework run passed 204 tests and found three unrelated
ArenaHard tests missing optional `scikit-learn`. Installed the declared optional
dependency before rerunning. The full upstream repository also contains paid/live
services and optional backends; no all-upstream-tests claim is made.

Generated discovery and docs use upstream commands. The statistics pass was
attempted but requires a configured reference panel and corpus; its misleading
zero-row result was discarded and metadata regenerated without statistics.
Translation was attempted but no `DASHSCOPE_API_KEY` is configured; the Chinese
page uses the upstream English fallback. No credential was requested or used.
Repository-wide pre-commit has the previously documented Windows symlink-placeholder
EOF failure at `.github/copilot-instructions.md`; its incidental edit was removed.

No smaller operating point is certified. One historical judge grade per answer
cannot estimate judge variance. Full retention removes sampling error, not judge
error, and a two-point historical model gap remains judge-sensitive. Provider
behavior, paid fresh-model runs, actual billing/latency savings and repeat-judge
variance are unmeasured. Saved-run comparison belongs to issue #21.

The [two-axis review](issue-20-review.md) has no unresolved actionable findings.
Its documented test-placement finding was resolved by moving judge verdict cases
to the required upstream migrated-adapter module; the CSV finding was fixed and
regression-tested. The benchmark-specific evidence audit scripts remain separate.
