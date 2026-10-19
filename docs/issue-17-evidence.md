# Issue #17: Part A operating-point evidence

Implements [#17](https://github.com/sdv1708/ai-model-quality-challenge/issues/17)
on `feature/issue-17-operating-points`, based on freshly pulled main
`92a25332c6aa74540b2931bde5922f5e1b6c34fd` (includes merged issue #16 / PR #39).
The linked chat **Implement issue #16** was read before interpreting prior work.

## Policy and interpretation

The twelve gates are declared by `FidelityPolicy` before this ticket's new runs.
They are retrospective illustrative requirements, because earlier study results
were already known. No customer tolerance, independent preregistration, fresh
model validation or production certification is claimed. Illustrative thresholds
are explicitly supplied: coding 0.70 and AA-LCR 0.60.

Both benchmarks retain their complete recorded references: **315/315 coding and
100/100 AA-LCR**. No smaller tested candidate meets every requirement. This is
the smallest passing **tested** size, not a mathematical proof against untested
ratios. Default retained fractions are 0.1, 0.2, 0.3, 0.5 and 1.0; seeds are 0–19.

Every held-out model, independently excluded pair and supplied model/threshold
fold gates separately. Worst-fold metrics prevent pooled means hiding weak folds.
Reference-assisted three-model ordering and Jaccard overlap are diagnostic only.
All summary rows, including comparison baselines, remain available; baselines
are never eligible for selection. Census strategy-name ties are bookkeeping.

At half retention, coding difficulty has 1.83 pp worst-fold MAE, but the hardest
pair agrees only 60% of the time and is never interval-decisive. AA-LCR historical
selection has 2.90 pp pooled MAE but 3.16 pp worst-fold MAE, below-policy ranking
and no decisive pair intervals. The [full guide](../task2/ISSUE_17_GUIDE.md)
explains these curves, weighting, leakage prevention, uncertainty and limitations.

## Reproduction

From `task2/`, with Python 3.12:

```powershell
uv sync --locked
uv run part-a-operating-points --data-root ../Evals --output-dir output/operating-points --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/operating-points/live_code_bench_v5
uv run python tools/audit_aa_lcr.py --data-root ../Evals --reports output/operating-points/aa_lcr
uv run python tools/audit_operating_points.py --reports output/operating-points
uv run pytest --basetemp output/pytest-issue-17-final
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The equivalent module command is `python -m benchmark_reference.operating_cli`.
Installation with `uv sync --locked` and the actual installed entry point's
`--help` were verified. No inference or judging calls are made.

Each benchmark has 1,500 score runs and 1,500 pair runs: five methods × five
ratios × twenty seeds × three model/model-pair folds. Total: **6,000 replay
evaluations**, reusing 1,245 existing Part A grades. These are not independent
new model or judge evaluations.

The new root outputs are `operating_points.json`, `curves.csv`, and `manifest.json`.
The nested studies preserve all nineteen existing report files. The root manifest
hashes every nested report, both child manifests, both root data reports and all
package Python sources. Implementation hashes normalize line endings to LF;
report hashes use exact bytes. Both analyses validate before publication, but
individual atomic replacements are not a multi-file transaction.

Compact curves, selected points and the original root manifest are retained in
`docs/data/task2-operating-*`. The selected-point extract records its source
report hash; regenerate large traces locally.

## Acceptance mapping

| Requirement                 | Evidence                                                                                                                   |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Consistent declared metrics | One `FidelityPolicy` and `compare_operating_points` for both benchmarks; twelve explicit gates                             |
| Held-out versus in-sample   | Excluded-model score folds, independently excluded pair folds, diagnostic-only reference-assisted rankings                 |
| Honest uncertainty          | Width, coverage, decisiveness, false decisions and seed dispersion reported; explicit judge/three-model/search limitations |
| Justified retained sizes    | Every size retains all failed-gate names; full-reference fallback when all compressed candidates fail                      |
| Explain and defend          | Complete #14–#17 guide, worked arithmetic, real curves, interview exercises and links from the prior learning walkthrough  |

## Validation record

The user confirmed the public analysis/selection function and end-to-end CLI as
test boundaries. Red-to-green cycles covered the initial decision API, both-data
CLI, mismatched pair truth and attempted promotion of a comparison baseline.
Additional synthetic regressions cover a smaller passing exploratory point,
incomplete pair evidence, no supported point and failure before replacing prior
reports. Tests use known artificial grades, not shipped data as expected truth.

Final suite, independent-audit and reproduction results are recorded after review
in [the review record](issue-17-review.md).
