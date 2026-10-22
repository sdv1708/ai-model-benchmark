# Issue #18: pinned EvalScope extension baseline

Issue: [Establish the pinned evalscope extension baseline](https://github.com/sdv1708/ai-model-benchmark/issues/18).

Updated challenge `main` to `8f90439` before creating
`feature/issue-18-evalscope-baseline`. The separate private development repository
is [sdv1708/evalscope-pruning](https://github.com/sdv1708/evalscope-pruning), with
the same feature branch. Its upstream is
[modelscope/evalscope](https://github.com/modelscope/evalscope), based exactly on
`66f0945d145ce6c30de40253cd78144003c6f1fe` with original history and Apache-2.0
license preserved. It is a private derived repository, outside the public GitHub
fork network. GitHub's API reports `isPrivate: true`.

The [machine-readable lock](../task2/evalscope-baseline.json) pins the implementation
commit. [The learner guide](../task2/ISSUE_18_GUIDE.md) explains the issue, a worked
example, the chosen seam, alternatives, operation order and remaining scope.

| Acceptance criterion | Evidence |
| --- | --- |
| Upstream and exact base documented | Private README introduction, `PRUNING_BASELINE.md`, and the lock file |
| Relevant upstream baseline tests pass | 50 tests passed before introducing the adapter |
| Minimal pruned dataset discoverable through conventions | `@register_benchmark`, native adapter location, generated lazy index; fresh-process CLI test |
| Integration is inside EvalScope | Adapter, toy data and tests are in the actual private `evalscope` package; standard inference, scoring and reports run |
| Selected seam and alternatives can be explained | Guide and private baseline document compare `load_subset`, conversion/filter hooks, limits, whole-loader overrides and core-wide changes |

The `pruning_smoke` adapter extends `DefaultDataAdapter`, loads the complete
eligible population through the standard loader, and selects deterministic
metadata groups before limits and repeated attempts. Six synthetic questions
become three: one easy, one medium and one hard. Question IDs are preserved in
metadata; framework execution IDs are reindexed. Configuration and malformed
or duplicate identities fail explicitly. No challenge data is copied into the
framework repository.

## Verification

| Check | Result |
| --- | --- |
| Upstream adapter / dataset-limit / registry baseline | 50 passed |
| Final adapter / dataset-limit / registry / metadata / integration suite | 81 passed, including all 16 new smoke tests |
| Upstream required CI-lite smoke | 1 passed with mock model; downloaded public IQuiz data |
| New code Ruff and Mypy | Passed |
| Upstream import architecture | 5 contracts kept, 0 broken |
| Feature-file upstream pre-commit checks | Passed |
| CLI and JSON `run_task` smoke examples | Standard predictions, reviews, JSON report and HTML report generated; 3 samples |
| Package verification | Wheel built and installed into a temporary target; imported installed package and loaded its bundled fixture |
| Complete challenge Task 2 suite | 129 passed; Ruff check, format check and strict Mypy passed |

The test paths and reproduction commands are in the private repository's
`VALIDATION_ISSUE_18.md` and `PRUNING_BASELINE.md`. Type checks cover the new
module/test with upstream imports followed silently; no repository-wide upstream
Mypy pass is claimed. The full upstream suite includes live services and optional
backends and was not run wholesale. Its relevant baseline and standard CI smoke
were run.

Full upstream pre-commit was attempted. Initial CRLF checkout and an existing
Windows symlink placeholder's missing newline prevented a clean global pass.
The feature files pass all applicable pinned hooks. No unrelated upstream
auto-fixes are included. Generated benchmark docs use the supported English
fallback for Chinese because translation requires an LLM credential.

## Scope and interpretation

This is the ticket's minimal integration foundation. Its synthetic allocation
is not a production pruning strategy and its subset mean is not advertised as
a full-benchmark estimate. The mock model's observed 0.0 score is expected and
only proves the real grading/report path ran.

Issues #19–#21 add the required `live_code_bench_pruned` interface, AA-LCR
integration and comparison command. Issue #17's full-reference fallback remains
unchanged: no smaller tested candidate passed all illustrative decision gates.
No production compression or new model-quality claim follows from this smoke.
