# Issue #26: final documentation and written walkthrough

Authoritative issue: [#26](https://github.com/sdv1708/ai-model-benchmark/issues/26).
Read its body, empty comment thread, parent #1 and closed prerequisites #24/#25.
The explicit user implementation request overrides learner-labelled ownership;
the user subsequently clarified that recording should be split into a separate
ticket and deferred, rather than cancelled.

## Provenance and scope

Initial working trees were clean. Challenge main was pulled to
`7882d1623136727b28799b1405337456cd836650` and native EvalScope main to
`800119ff6870ca958f5d8459970f5fe75bfac305`, before creating
`feature/issue-26-task2-documentation` in each repository. Upstream base remains
`66f0945d145ce6c30de40253cd78144003c6f1fe`. Native main's runtime tree is identical
to the previous #21 implementation pin `5fd26289972f6d01b13ea95bb30481ebd103fa2d`.
This documentation issue introduces no runtime or selection-policy changes.
Optional TDD does not apply to editorial edits; existing public tests are reused.
Verified native documentation revision:
`1f7396ea0eb33f55162f48596dcb1dc8991965f4`. Subsequent publication-status edits
do not change the validated runtime. Native publication is tracked in
[companion PR #4](https://github.com/sdv1708/evalscope-pruning/pull/4).

## Acceptance mapping

| Issue requirement | Evidence / status |
| --- | --- |
| Pinned upstream SHA and required commands prominent | Both root READMEs; fork `TASK2_README.md`; challenge [final guide](../task2/ISSUE_26_GUIDE.md) |
| Clean clone can run relevant tests and reproduce analysis/comparison | Exact Python/dependency/runtime pins, native isolated-clone verification and challenge historical commands; results below |
| Walkthrough demonstrates integration and explains evidence | Seven-step written demonstration in both guides; native synthetic CLI demonstration; no recorded walkthrough |
| Trade-offs and limitations stated directly | Full-retention result, no live savings, retrospective-policy reuse, unknown judge variance, conditional GO, synthetic-only image harness and API causality limit |
| Accessible video link in checklist | Recording/publication/access criteria moved to open, deferred [#49](https://github.com/sdv1708/ai-model-benchmark/issues/49); [checklist](../SUBMISSION_CHECKLIST.md) tracks the still-required video |

Issue #26 now owns written documentation and the written walkthrough; its original
video criteria were moved to #49 at the user's request. The final submission audit
(#27) explicitly depends on #49, preserving the recording requirement. Issue
closure is reserved for the submission PR's merge. No reviewer invitation,
deployment or submission-form action is performed. The native README is edited
in the actual EvalScope-derived repository, not only described in this submission.

## Research

- Actual source at native runtime pin: both pruned adapters, shared pruning
  helpers, smoke script, comparator, CLI and previous validation. Confirmed
  `--work-dir`, `--no-timestamp`, nested dataset arguments, retained-ratio meaning,
  frozen source population, weights, output identity checks and threshold semantics.
- Recorded [full scores](data/task2-full-scores.json),
  [selected operating points](data/task2-operating-selected.json) and
  [manifest](data/task2-operating-manifest.json): default grid, twenty seeds,
  illustrative thresholds 0.7 coding / 0.6 AA-LCR, defended 315/315 and 100/100.
- [Official EvalScope quick start](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html):
  evaluation and saved-output workflow. Pinned source controls exact commands.
- [Official MMMU README at the researched pin](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md):
  150 development + 900 validation + 10,500 test = 11,550; 30 subjects.
- [MMStar paper](https://arxiv.org/abs/2403.20330v2): motivates visual-dependence
  controls, not validation of this proposal's budgets or transformations.

## Fresh verification

The native runtime was cloned from the local committed Git repository using
`git clone --no-local --no-hardlinks` into a new sibling `issue-26-native-clean`.
Its HEAD is exactly `800119ff6870ca958f5d8459970f5fe75bfac305`; it has a separate
Python 3.12.8 environment, no shared site-packages and a clean tracked tree.
Dependencies were installed from `requirements/pruning-baseline.txt` (143 pinned
packages), followed by editable installation with `--no-deps`. The package imports
from this new clone. Package cache reuse is not a reused virtual environment.
This verifies an isolated local clone; a new remote clone/reviewer account's
private access was not tested.

Fresh registration succeeded for both native datasets. The documented synthetic
AA-LCR full/pruned CLI workflow succeeded with ordinary local socket/process
access, as did a separate saved-run comparison. Its
[saved JSON](data/task2-issue26-native-smoke.json) records **12/3 unique questions**,
scores **1.0/1.0**, difference **0 pp**, completion bounds **[0.25, 1.0]**, full
**GO**, subset **inconclusive**, no model ordering and `decision_certified=false`.
No paid provider or real-model-quality result is claimed.

The first isolated native test attempt exposed two missing setup instructions:
108 setup errors came from pytest's missing `.pytest-tmp` parent; three inherited
ArenaHard judge tests failed because the baseline snapshot lacks scikit-learn.
The old native environment had that optional dependency. Both guides now create
the temporary parent where needed, and the native full-suite recipe explicitly
installs `scikit-learn==1.9.1` and `threadpoolctl==3.7.0`. The suite also guards
against a local `.env` file:
CI-lite reads its key using `dotenv_values('.env')`, so clearing a process
environment variable would not force mock mode. The isolated clone has no `.env`;
its CI-lite run uses the mock model. These are documentation fixes, not changes
to runtime code or test logic.

Windows' default CRLF checkout also failed native Ruff's LF formatting check on
four unchanged extension files. The clone recipe now persists
`core.autocrlf=false` in the new repository only. Re-checkout with LF endings in
the isolated clone made `ruff format --check evalscope_ext` pass. No global Git
settings or upstream formatting exemptions changed.

| Check | Fresh result |
| --- | --- |
| Complete challenge Task 2 suite | **152 passed**, 85.68 seconds |
| Challenge Mypy | **40 files**, passed |
| Challenge Ruff lint / formatting | Passed; **60 files** formatted correctly |
| Native Mypy | **6 files**, passed in the isolated environment |
| Native comparator Ruff lint / formatting | Passed; **4 extension files** formatted correctly after LF checkout |
| Native import contracts | **5 kept, 0 broken** |
| Native full-suite final rerun | **242 passed**, 189 upstream warnings, 128.15 seconds after the documented prerequisite repairs |

The historical reference command validated **28 prediction/review pairs, 56 files,
1,905 samples** and regenerated all six Part A scores. Its entire score JSON
equals [the recorded score JSON](data/task2-full-scores.json). The default
operating-point replay with coding 0.7 / AA-LCR 0.6 reproduces every selected
benchmark field, limitation and plan field in the saved selected extract. The
fresh complete report additionally contains the full grid diagnostics; it is not
byte-identical to the smaller checked-in extract. Both selected counts remain
315/315 and 100/100 with `full_reference_fallback` and no certification.

The isolated native smoke logs, tests and generated artifacts remain beneath its
ignored `outputs/`. Challenge replay files remain in ignored `task2/output/`.
No new paid inference, live MMMU experiment or Task 1 change was performed.

## Documentation checks and review

All **129 local Markdown links**, including **7 linked headings**, resolve.
All **23 PowerShell blocks** parse successfully. Provisional verification
placeholders are absent. Applicable native
pre-commit hooks passed on changed files. Repository-wide `make lint` encountered
the known Windows `.github/copilot-instructions.md` symlink-placeholder EOF
failure; its hook-generated change was restored. No unrelated edits remain.
The entire upstream test suite was not rerun or claimed to pass.

Independent reviewers found **0 Standards findings** and **two Spec findings**,
both repaired and independently verified: walkthroughs must point to the
production `_reference_pruning` helper, and CI-lite's mock prerequisite must match
its actual `.env` key source. See [the review record](issue-26-review.md).
The video is explicitly deferred in #49 and remains required for the overall
submission, rather than being cancelled or silently treated as complete.

## Deferred recording ticket split

Created [#49](https://github.com/sdv1708/ai-model-benchmark/issues/49) and verified
that it is **OPEN**, explicitly deferred, with recording, publication, reviewer
access and checklist/form URL acceptance criteria preserved. Issue #26 was renamed
to documentation and written walkthrough, with those video criteria transferred.
Issue #27's blockers now include #49. The existing Task 1 video remains in #13.
No recording deadline was invented and no video requirement was cancelled.
README entrypoints, both native guides and the checklist reflect this split.
