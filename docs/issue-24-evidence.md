# Issue #24: one-page technical Handout A

Implements [issue #24](https://github.com/sdv1708/ai-model-benchmark/issues/24).
The user explicitly requested implementation of this learner-labelled ticket,
research, latest main, a new branch, and a detailed first-principles explanation.
The initially clean checkout was switched to main and fast-forwarded to
`0e49b9a4c6671450a7d83563a4cfa3772be3c9bd` before creating
`feature/issue-24-technical-handout`. No existing work was discarded.

## Deliverables and scope

- [Handout A PDF](../output/pdf/handout-a.pdf): one A4 page, 10.2 pt body,
  8.5 pt evidence footer, four clickable source links.
- [Canonical Markdown](../task2/HANDOUT_A.md): editable text matching the PDF.
- [Detailed learning/interview guide](../task2/ISSUE_24_GUIDE.md): plain-language
  examples, calculations, limitations, provenance and rehearsal questions.
- [Documentation renderer](scripts/render_handout_a.py): staged publication,
  source-link checks and one-page enforcement; no benchmark dependency changes.

This is a synthesis/documentation ticket. It introduces no new selection policy,
benchmark behavior, model inference or independent validation population. The
implement skill's optional TDD workflow was not applied to editorial changes;
existing public-behavior regressions and independent evidence auditors were used.
No permission to publish a PR, push or close the issue was needed or inferred.

## Every original technical prompt

Authority: [Task 2 brief](../Task2_Model_Quality.md), section
`Handout A - "Why this works"`, plus issue #24 and its parent #1.
Prerequisites #17, #21 and #23 were read and are closed.

| Required prompt / acceptance criterion | Handout content and challengeable evidence |
| --- | --- |
| Why this Part A approach? What problem? | Decision-preserving evaluation; metadata/reference strata, proportional allocation and population weighting; [#17 evidence](issue-17-evidence.md) |
| How much pruned; why sufficient? | 315/315 coding, 100/100 AA-LCR: 0% pruned; tested grid and every-fold gates; exact half-retention failures; [selected records](data/task2-operating-selected.json) and [curves](data/task2-operating-curves.csv) |
| Part B; why encoder stress? | Full 30-subject population, weighted versus diagnostic panels, targeted visual changes, semantic QA and reasoning controls; explicit visual-path/encoder-causality limit; [design](../task2/MMMU_PROBE_DESIGN.md) |
| Distribution, scale and model assumptions? | Valid grades/joins, stable strata, limited difficulty transfer, three-model search reuse, unmeasured judge noise and cost; no production guarantee |
| More data? | Untouched model families, customer tasks and whole-document-set holdouts |
| Live endpoint? | Freeze requirements, full/subset fresh-model validation, repeated generation/regrading, human judge audit, cost measurement and visual controls |
| More time? | Intermediate retention sizes, power calibration, duplicate/coverage audits and frozen confirmation |
| Claims tied to evidence or marked assumptions? | Historical results, synthetic integration/harness counts, illustrative gates and proposed budgets are explicitly labelled; four inline source references |
| One readable page? | Generated PDF verified as one A4 page; rendered with Poppler and visually inspected; 614 whitespace-delimited extracted words |
| Engineer can challenge selection? | Selection features, weighting formula, exclusion folds, complete policy metrics, grid, seeds, failed-gate examples, versions/commands in linked records |
| Learner can present without hidden analysis? | Essential reasoning is in the one-page artifact; companion guide supplies worked arithmetic, a 90-second explanation and oral exercises |

## Fresh evidence checks

From `task2/`, the existing Python 3.12.8 environment reran:

```powershell
.\.venv\Scripts\python.exe -m benchmark_reference.operating_cli --data-root ../Evals --output-dir output/issue24-operating --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
.\.venv\Scripts\python.exe tools/audit_lcb.py --data-root ../Evals --reports output/issue24-operating/live_code_bench_v5
.\.venv\Scripts\python.exe tools/audit_aa_lcr.py --data-root ../Evals --reports output/issue24-operating/aa_lcr
.\.venv\Scripts\python.exe tools/audit_operating_points.py --reports output/issue24-operating
```

All three independent auditors passed: 1,500 score + 1,500 pair-transfer runs
per benchmark (6,000 replay evaluations total), plus 50 fidelity points, every
policy gate, selected points and hashes. They reuse recorded grades and do not
constitute independent model or judge observations.

The regenerated `operating_points.json` is byte-identical to the report whose
SHA-256 is recorded in `docs/data/task2-operating-selected.json`:
`1a9e308d6e65dcc7f74ca4863aec32cae61b41f266c8f549d75eef076972e338`.
Both selected records match the committed extracts. CSV rows are compared as
parsed data because the checkout uses CRLF while newly written reports use LF.

Half-retention coding difficulty: 158 questions, worst-fold MAE
`0.018286808976464137` (1.83 pp rounded), minimum pair-order agreement `0.6`,
minimum pair-interval decisiveness `0.0`. AA-LCR length+difficulty: 50 questions,
worst-fold MAE `0.03164583333333333` (3.16 pp rounded). The 2.90 pp pooled value
is a separate statistic from the fidelity replay; it is not used to waive the
worst-fold gate. It was independently recomputed as 2.9037235449735452 pp over
60 half-retention held-out-model runs in the fresh fidelity output.

The #21 smoke's 12 full / 3 retained questions, equal 1.0 scores, `[0.25,1.0]`
completion bounds and inconclusive subset at threshold 0.8 were checked against
[the saved output](data/task2-run-comparison-smoke.json). That native experiment
was not rerun for this editorial ticket. The #23 demo counts (38 pairs,
82 planned calls, 79 scripted responses) were checked against its contract,
implementation and existing regression tests. No fresh live endpoint was used.

## Research checked 23 October 2026

Research corroborates interpretation/design, not a new measured model result.

- [Official MMMU README at the pinned revision](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/README.md),
  successfully read through its raw endpoint: 30 subjects; 150 development +
  900 validation + 10,500 test = 11,550 questions; test-answer release; native
  OpenAI-compatible EvalScope workflow. No full-dataset image census was run.
- [MMStar paper](https://arxiv.org/abs/2403.20330): motivates checking visual
  dependence and text-only answerability. It does not validate our chosen
  panel sizes or transformations.
- [NIST confidence-interval interpretation](https://itl.nist.gov/div898/handbook/prc/section1/prc14.htm):
  repeated-sampling coverage, not an unseen-model guarantee. Its illustrative
  normal-mean formula is not our finite-pool construction.
- [scikit-learn nested/non-nested validation example](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html):
  search/evaluation reuse can create optimistic conclusions; motivates fresh
  confirmation. We do not claim nested validation was implemented.
- [Official EvalScope repository](https://github.com/modelscope/evalscope):
  framework purpose and extensibility; the implementation contract remains the
  pinned fork, not an assumption that current main APIs are identical.

The pinned Hugging Face card was unavailable through this session's web tool.
The official pinned MMMU repository independently supplied the split counts;
the inherited HF pin and its audit remain recorded in the #22 design. No stale
or failed web response was treated as fresh dataset inspection.

## Artifact verification and review

PDF authored with bundled ReportLab 4.4.9 and pypdf 6.10.0, without adding those
documentation-only packages to Task 2 dependencies. A4 output, one page, complete
text, four URI annotations, expected font sizes and margins were checked. Poppler
render was inspected for clipping, missing characters, overlap and readability.
The canonical Markdown is the single source of PDF content.

The final complete Task 2 suite passed: **152 tests**, Ruff lint/format, strict
Mypy (40 source files). The new documentation renderer separately passed Ruff
lint/format. Local Markdown link checks covered **91 links with zero broken**
targets across the five changed documentation files. These are scoped Task 2
checks; unrelated Task 1 and the separate native fork were not retested.

The rendered PDF contains 614 extracted words; all characters fall inside the
page margins. PDF SHA-256:
`e710b0647713f14a59adab134191eae8c93c5e1f171d9c9c17082f27e581b122`.
Rendering it again after renderer formatting produced the same bytes.
PDFs are explicitly marked binary in `.gitattributes` to prevent CRLF conversion
from changing their encoded bytes during staging or checkout.

The implement skill's independent parallel review against freshly pulled main
is complete: **Standards 0 actionable findings; Spec 0 findings**. See the
[separate review reports](issue-24-review.md). No implementation changes were
required. PDF text also exactly matches normalized canonical Markdown; staged
and working PDF Git blob hashes agree after binary protection.
