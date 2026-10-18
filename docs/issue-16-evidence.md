# Issue #16 acceptance evidence

Implemented on `feature/issue-16-aa-lcr`, branched from fetched `origin/main` at
`39a14597eee63d8e8063f500d7c58be880be1193`. The issue #14 reference pipeline is
already present at this base. The user's explicit implementation request supersedes
the ticket's earlier learner-authorship workflow; the guide explains the implementation.

## Acceptance criteria

| Requirement                                                   | Evidence                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Nontrivial candidates at several pruning ratios               | `metadata_stratified` and `length_difficulty_stratified`; retention 0.1, 0.2, 0.3, 0.5, 1.0; 20 seeds; trivial baselines are comparison-only and rejected by the candidate API.                                                                                                                                                                                          |
| Length and available metadata considered without hand-picking | Shared benchmark token counts, canonical document-URL counts, empirical midrank bands, algorithmic allocation, seeded hash priorities. Question identity is validated. No target output, usage, grade, or manually selected ID enters fitting. Source coverage and token cost proxies are reported.                                                                      |
| Judge limitations quantified where possible                   | One recorded grade per answer, zero repeat-reviewed answers, judge identity inventory; judge variance/flip rate explicitly null. Exact conditional weighted flip envelopes, b/N score bounds, full-pair tipping counts, and a repeat-judging plan.                                                                                                                       |
| Score and ordering fidelity against full benchmark            | 1,500 leave-one-model-out score runs plus 1,500 leave-two-models-out pair runs; weighted/raw estimates, MAE/RMSE/bias/worst error, tie-aware ordering, exact design intervals, optional threshold decisions and seed Jaccard stability.                                                                                                                                  |
| Learner can explain why signals should generalize             | [Guide](../task2/ISSUE_16_GUIDE.md) progresses from the basic problem to signal rationale, weighting, holdout boundaries, intervals, judge identifiability, and limitations. Metadata features are model-independent; historical difficulty transfer is a tested hypothesis, not a guarantee. Personal understanding still requires the learner to study and explain it. |

## Recorded results

Full AA-LCR scores: gpt-oss-120b **48/100**, kimi-k2.5 **66/100**,
minimax-m2.5 **64/100**. Metadata: 100 questions, 30 document sets, 173 URLs,
71,691–114,563 benchmark input tokens per question, 9,524,828 total input tokens.

At 50% retention:

| Measure                                                  | Length + difficulty | Length + document count |
| -------------------------------------------------------- | ------------------: | ----------------------: |
| Held-out MAE, percentage points                          |                2.90 |                    3.27 |
| Exact reference-assisted three-model order               |               66.7% |                   70.0% |
| Independently held-out pair order                        |               88.3% |                   90.0% |
| Mean nominal 95% score interval width, percentage points |               47.75 |                   48.48 |
| Decisive candidate pair intervals                        |                  0% |                      0% |
| Mean input-token fraction                                |              49.86% |                  49.91% |
| Mean document sets covered, of 30                        |               24.75 |                   25.20 |

These are descriptive results over fixed stored grades, not guarantees for a
future model or measurements of judge randomness. No sufficient production ratio
is certified. Metadata-only selections repeat across folds and do not constitute
independent replications. Token totals are an input-cost proxy, not measured savings.

All 300 reviews use recorded judge `qwen-3-235b-a22b-instruct-2507`, strategy `auto`.
The 66%-versus-64% pair needs only two total changed grade cells to tie or three
to reverse. Larger gaps require 18/19 and 16/17 changes to tie/reverse. These are
adversarial sensitivity thresholds, not estimated flip probabilities.

## Verification

The user confirmed the public selector/evaluation API and CLI/report seams before
tests were written. New behavior was developed in red/green slices: metadata
coverage, configurable candidate evaluation, flip sensitivity, and end-to-end reports.

From `task2/`, with the project's Python 3.12 environment:

```powershell
python -m pytest --basetemp output/pytest-issue-16
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

Results: **119 tests passed**, lint and format checks passed, strict mypy passed
for **25 source files**. Existing reference and coding-pruning regressions pass.
No tests are skipped or expected failures. Synthetic tests cover leakage prevention,
seed/order determinism, coverage weights, forbidden candidates, metadata conflicts,
insufficient budgets, census recovery, exhaustive unequal-weight flip envelopes,
report hashes/reproducibility, candidate-registration validation, and preservation of old reports on metadata failure.

`uv run --locked aa-lcr-pruning --help` successfully rebuilt the editable package
and verified its new console entry point. Sandbox temporary/cache permissions
required a workspace pytest base directory and normal-cache access for uv; these
are environment details, not test exclusions or source changes.

The default full-data command completed 3,000 evaluations. The independent
`tools/audit_aa_lcr.py` passed all input/output/implementation hashes, raw full
scores, reconstructed metadata groups/weights, weighted estimates, every score
and paired interval, and full-pair flip tipping counts. It imports no production
analysis code; interval bounds use the LCB auditor's independent linear inversion.
It does not certify semantic validity of the source metadata or true judge accuracy.

Two complete default runs produced byte-identical copies of all eleven reports, including
the manifest, in different output directories. All reported fidelity numbers remained
unchanged after the review fix.

A second CLI run at retention 0.5/1, seeds 0/1/2, and illustrative thresholds
0.5/0.6/0.7 completed another 180 evaluations and exercised decision reporting.

## Saved evidence and scope

Checked-in files under `docs/data/` contain score/pair summaries, all coverage rows,
the run manifest, and an explicitly labeled noise-summary extract linked to the
full noise report hash. Full selected-index, fidelity and sensitivity artifacts
regenerate under ignored `task2/output/aa-lcr-pruning/` with the documented command.

Publication remains per-file atomic with manifest-last hashes, not an eleven-file
transaction. Keep inputs fixed and use one writer per destination.

This ticket evaluates AA-LCR candidates offline. The project's later pinned
evalscope integration and final customer operating-point decision remain separate.

The implementation skill's [two-axis review](issue-16-review.md) has no unresolved
standards or spec findings after the candidate-registration fix.
