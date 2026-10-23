# Issue #21 acceptance evidence

The user explicitly requested implementation of this learner-labelled ticket,
latest main, a new branch, research, accurate results and an interview-ready
explanation. Challenge main was pulled to `12070a1`; native fork main was pulled
to `9698587429f23a28daed3f341ca8b97aa5b1d28b`. Both checkouts use
`feature/issue-21-compare-runs`. The initial trees were clean.

Implementation lives inside private `sdv1708/evalscope-pruning`, preserving the
upstream integration requirement. The submission records the exact native commit
and inherited upstream pin in [evalscope-compare-runs.json](../task2/evalscope-compare-runs.json).
The [learning guide](../task2/ISSUE_21_GUIDE.md) covers architecture, worked examples,
invariants, limitations and interview answers. The user's confirmed public test
boundary is the subprocess module command and its saved-run input/output behavior.

| Acceptance criterion | Evidence |
| --- | --- |
| Documented module accepts full/pruned result directories | `python -m evalscope_ext.tools.compare_runs --full ... --pruned ...`; one or more exact Native roots per side |
| Counts, difference, ordering/decision evidence, warnings | Unique questions and attempts, raw and weighted means, signed/absolute percentage-point differences, paired question MAE, multi-model pair order, optional conservative threshold decisions |
| Invalid/incompatible inputs fail actionably | Exit 2, stderr diagnostic, no partial JSON; matching settings, input/grading identities, complete populations/attempts, native schema and valid design weights required |
| Representative tests | **34 public CLI tests passed**; complete relevant native suite **242 passed** |
| Complete required run contract | Fork `COMPARE_RUNS.md` includes installation, full/pruned real coding CLI commands and comparison, plus a credential-free Native AA-LCR workflow |

## Measured integration

The real Native evaluator used a loopback OpenAI-compatible answer/judge fixture
and tiny synthetic documents. It wrote complete configs, reports and reviews,
then the comparison command consumed those files. The final reviewed module was
rerun against those saved Native results.

[Saved comparison output](data/task2-run-comparison-smoke.json):

- Full: **12 unique questions**, 12 attempts, score **1.0**.
- Pruned: **3 unique questions**, 3 attempts, weighted score **1.0**.
- Signed and absolute error: **0 percentage points**; paired question MAE: **0**.
- Pruned completion bounds: **[0.25,1.0]**.
- At illustrative threshold **0.8**: full recorded GO, subset **inconclusive**.
- Warnings preserve unmeasured AA-LCR judge noise, retrospective scope and absent
  single-model ordering; `decision_certified=false`.

This demonstrates transport, serialization, validation and comparison, not model
quality. The fixture's 75% reduction is not certified production compression.
The defended historical defaults still retain 315 coding / 100 AA-LCR questions.
No paid model or judge inference was performed for issue #21.

## Verification and review

| Check | Result |
| --- | --- |
| Final complete relevant native regression suite + upstream CI-lite | **242 passed**, 189 existing upstream warnings |
| Comparison CLI tests within that suite | **34 passed** |
| Complete submission Task 2 suite | **129 passed** |
| Native feature Mypy | Passed, 6 source/test/example files |
| Submission Mypy | Passed, 34 source/test/tool files |
| Native feature / submission Ruff and formatting | Passed |
| Native import contracts | **5 kept, 0 broken** |
| Native pre-commit on changed files | Passed |
| Wheel package and execution outside source checkout | Passed; [module/source-byte audit](data/task2-run-comparison-package.json) |

The initial CLI test failed because the module did not exist. Independent parallel
Standards and Spec reviewers then checked the implementation. Four compatibility
gaps were repaired: cross-model comparability, hidden coding test identity,
original AA-LCR repeat-count semantics, and multi-level report rounding. The
spec reviewer independently passed seven repair regressions and confirmed zero
unresolved actionable findings. Standards found zero hard violations and one
optional typed-provenance maintenance suggestion. See the
[two-axis review](issue-21-review.md).

The relevant native suite command and environment details are recorded in the
fork's `VALIDATION_ISSUE_21.md`. In this repository, the existing Task 2 virtual
environment ran `python -m pytest`, `python -m ruff check .`,
`python -m ruff format --check .` and `python -m mypy`. Direct environment Python
avoided a sandbox-specific uv interpreter-cache permission failure.

## Reproduction and limits

From an activated Python 3.12 environment in the EvalScope fork:

```powershell
python -m pip install -e .
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/comparison-smoke
python -m evalscope_ext.tools.compare_runs --full outputs/comparison-smoke/full --pruned outputs/comparison-smoke/pruned --threshold 0.8
```

The pinned CLI uses `--work-dir`, rather than the task brief's conceptual
`--output`. `--no-timestamp` ensures exact run roots. Dataset arguments are
nested by benchmark, with pruning under `extra_params`; the fork's guide contains
the full real coding command sequence and AA-LCR judge setup references.

The entire upstream suite was also attempted. It stopped during collection with
**27 errors and 12 skipped** because optional `anthropic`, `emoji`, `flask`,
`langdetect`, `torch` and `uvicorn` packages are unavailable. It is not claimed to
pass wholesale. Repository-wide `make lint` encountered the existing Windows
symlink-placeholder EOF issue in `.github/copilot-instructions.md`; the unrelated
hook modification was removed, and all applicable feature hooks passed.

Completion bounds assume only unknown grades in [0,1] for the fixed input pool;
they are not probabilistic confidence intervals. Different recorded grades across
fresh runs can reflect generation/judge variation. The command reports that
disagreement and never estimates judge variance from one verdict per answer.
Historical `Evals/` files are not relabelled as fresh Native results. No new-model
transfer guarantee, live-cost saving, upstream merge, deployment or production
compression certification is asserted.
