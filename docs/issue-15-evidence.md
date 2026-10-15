# Issue #15 acceptance evidence

Verified October 15, 2026, on `feature/issue-15-lcb-pruning`, created after
fast-forwarding local `main` to `fb6671daa9274c1b65be58cd39c18a923797dc35`.
The issue #14 prerequisite is merged and closed. The user's explicit request in
this session authorizes assistant implementation of this learner-labelled ticket.

## Acceptance mapping

| Requirement | Evidence |
| --- | --- |
| Uniform random, easiest-only, hardest-only are comparisons only | Separate candidate/baseline APIs, explicit report roles, tests rejecting all three through the candidate API |
| Evaluate candidates at several ratios | Two candidates x five retained fractions x twenty seeds x three held-out models; three baselines use the same protocol |
| Unique, reproducible, auditable samples | No-replacement hash priorities; selected ID/group/count/weight records; six input hashes and eight implementation hashes; byte-identical reruns |
| Score and ordering fidelity against full benchmark | Weighted estimates and raw means, held-out MAE/RMSE/bias/max/spread, common-subset pair agreement, tie-aware Kendall tau-b and exact order fraction |
| Features remain defensible for unseen models | Only historical reference pass vectors; held-out model removed before fitting; target-grade perturbation test; no assistant-message features |

## Verification

From `task2/`, with Python 3.12 and the locked environment:

```powershell
uv sync --locked
uv run pytest -q --basetemp=output/pytest-final-reviewed
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning-repeat
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/lcb-pruning
```

Observed:

- **91 tests passed**, including existing reference tests; no skips or expected failures.
- Ruff lint and formatting passed; strict mypy passed for **15** source/test/tool files.
- **1,500** runs from **945** recorded coding grades, validating the six coding inputs.
- All five corresponding report files are byte-identical across the two real runs.
- Independent stdlib replay imports none of `benchmark_reference`; checks source,
  implementation and output hashes, normalized grades, unique selected IDs, weight
  totals, every estimated score, and held-out summary MAE/maxima.
- Full-budget selections recover all full scores and orderings, including explicit
  undefined tau-b for an all-tied synthetic model panel.
- Literal 8-task test demonstrates weighted 75% versus raw subset 50% under rare
  group oversampling; reversal/tie fixtures verify ordering math.
- Corrupt coding input, invalid ratio, repeated seeds, uncovered strata, and output
  paths inside source data exit 2 without replacing prior reports.

The initial isolated test encountered restricted Windows temporary-directory access;
the documented workspace-local `--basetemp` resolved it. Dependency synchronization
used normal host cache access. This is verification on the existing Windows checkout,
not a claim of a fresh-machine installation. No inference, regrading, or input edits
were performed.

The standards review identified source line-ending sensitivity and duplicated
report-I/O safeguards. Source hashes now normalize CRLF to LF (raw data/report
hashes remain exact), with a regression assertion. Both pipelines share the same
destination validation and atomic replacement helpers. The complete 91-test suite
passed again after these review changes, and the final reports were regenerated,
independently audited, and compared byte-for-byte a second time.

## Measured comparison

Errors below are **percentage points**, pooled over 60 runs per row. Ranking uses
one common subset in each fold and includes two in-sample historical reference models.

| Candidate | Retained | Tasks | Held-out MAE | Worst absolute error | Exact ordering |
| --- | --- | ---: | ---: | ---: | ---: |
| Difficulty strata | 10% | 32 | 4.94 | 15.50 | 35.0% |
| Difficulty strata | 20% | 63 | 3.38 | 9.61 | 46.7% |
| Difficulty strata | 30% | 95 | 2.50 | 6.24 | 38.3% |
| Difficulty strata | 50% | 158 | 1.53 | 3.73 | 43.3% |
| Response-pattern strata | 10% | 32 | 5.38 | 15.14 | 66.7% |
| Response-pattern strata | 20% | 63 | 3.41 | 9.70 | 61.7% |
| Response-pattern strata | 30% | 95 | 2.64 | 7.29 | 63.3% |
| Response-pattern strata | 50% | 158 | 1.61 | 3.38 | 63.3% |
| Both candidates | 100% | 315 | 0.00 | 0.00 | 100.0% |

Uniform comparison MAE at half retention is 1.78 pp; easiest-only/hardest-only
have 23.48/23.38 pp MAE. All per-fold results and comparisons are in the checked-in
[summary CSV](data/task2-lcb-pruning-summary.csv). The
[manifest](data/task2-lcb-pruning-manifest.json) fingerprints inputs, implementation,
and generated artifacts. Full per-run reports are generated under ignored output
directories rather than duplicating 25 MB of selected-sample records in Git.

## Interpretation and remaining project scope

These candidates are implemented and evaluated; no compression ratio is certified
for production. Kimi and Minimax differ by only 3/315 = 0.952 pp in the recorded full
benchmark, below typical half-budget error. Three folds trained on two models each
are limited evidence for a fourth model. Strata encode historical behavior, not
semantic topic coverage. The whole-tree inventory is checked, but this command
parses/hashes only coding files. AA-LCR/MMMU grades are not analyzed here.

Neither seed spread nor Jaccard overlap is a confidence guarantee. Customer decision
tolerances, uncertainty-aware operating-point choice, and the required pinned
evalscope extension remain later project work. Weighted candidate results require
weight-aware aggregation in that extension; a plain unweighted subset mean is a
different estimator. See [the complete interview guide](../task2/ISSUE_15_GUIDE.md).
