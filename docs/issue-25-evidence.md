# Issue #25: half-page operational Handout B

Implements [issue #25](https://github.com/sdv1708/ai-model-benchmark/issues/25),
read with its parent #1 and closed prerequisites #21/#23 on 23 October 2026.
The user's explicit implementation request authorizes this learner-labelled
ticket and asks for research and detailed interview preparation.

The initial checkout was clean. Main was switched to and fast-forwarded from
`0e49b9a` to `77c8cb5c18b15f426ac66577c4ab2459b6f8ebde` before creating
`feature/issue-25-operational-handout`. GitHub resolves the configured challenge
remote to canonical `sdv1708/ai-model-benchmark`; the canonical issue was read
explicitly after the old repository name returned an empty response.

## Deliverables and acceptance

| Requirement | Reviewable artifact / evidence |
| --- | --- |
| Concrete customer-conversation change | [Handout B source](../task2/HANDOUT_B.md): agree coding/document requirements and present a repeatable conditional decision; 0% defended pruning and absent cost savings are explicit |
| Tomorrow-ready EvalScope commands and interpretation | Two commands in the handout run the native synthetic evaluator/comparison; linked [guide](../task2/ISSUE_25_GUIDE.md) includes pinned installation, full/candidate coding and AA-LCR endpoint templates, prerequisites, failure checks and interpretation |
| Multimodal value beyond random sampling | Deliberate stress coverage, paired answer-preserving visual changes and text controls; visual-path sensitivity and synthetic-only status explicit |
| Customer-facing PM relevance | Acceptance criteria, validation budget, image-workflow risks and evidence-backed rollout promises |
| Half a page | [PDF](../output/pdf/handout-b.pdf) uses only the top half of one A4 sheet; bottommost character is 355.656 pt from the top, above the 420.945 pt midpoint |
| Different audience from Handout A | Action/customer/outcome sequence and executable practice rather than technical selection formulae; learner arithmetic lives in the companion guide |
| Detailed learning and interview readiness | School-test analogy, 25-100% worked bound, weighted 75% versus raw 50%, judge uncertainty, runbook, short interview answer and 13 follow-up questions |

The [renderer](scripts/render_handout_b.py) reads canonical Markdown and enforces
a half-page frame, command width, complete content, verified local link targets
and staged publication. The PDF uses 17 pt title, 9.5 pt body and 8 pt code/footer.
It contains **307 extracted words** and **four clickable links**. Normalized PDF
text exactly matches normalized canonical Markdown, including the commands.
PDF SHA-256: `df378bb528ddb1fec960558ec92701528c446c8efcdaf0b7ad034c7ecd9be262`.
Existing `.gitattributes` marks PDFs binary.

This is a documentation synthesis ticket. There is no selection-policy change,
runtime dependency change or new model-quality claim. Optional TDD was not
applied to editorial changes; no new test seam was introduced. Existing public
regressions, native integration and document checks supply verification.
No walkthrough video is needed for this ticket. The guide clearly distinguishes
the overall challenge's still-required submission videos from this written work.

## Research and source checks

The authoritative brief is [Task 2](../Task2_Model_Quality.md), Handout B's four
prompts, plus issue #25. Source code at the pinned native implementation wins
over rolling framework documentation when flags or behavior differ.

- Native fork commit `5fd26289972f6d01b13ea95bb30481ebd103fa2d`, inherited upstream
  `66f0945d145ce6c30de40253cd78144003c6f1fe`: read `COMPARE_RUNS.md`,
  `AA_LCR_PRUNED.md`, `LIVE_CODE_BENCH_PRUNED.md`, `PRUNING_BASELINE.md`, actual
  CLI arguments, smoke script and comparator. Confirmed `--work-dir`, nested
  dataset `extra_params`, `--no-timestamp`, judge setup, fixed-population ratio 1.0,
  completion-bound semantics and exit-status distinction.
- [Official EvalScope quick start](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html):
  CLI workflow and saved evaluation artifacts. Current docs corroborate the
  framework workflow; they do not supersede the source pin.
- [Official pinned MMMU README](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md):
  30 subjects and split inventory 150 + 900 + 10,500 = 11,550. The raw primary
  source was successfully read after the GitHub HTML endpoint timed out.
- [MMStar paper](https://arxiv.org/abs/2403.20330): visual-dependence and text-only
  answerability motivate controls. This does not validate our probe budgets,
  perturbation strengths or any candidate model.
- [Selected policy records](data/task2-operating-selected.json),
  [#17 evidence](issue-17-evidence.md), [#21 smoke](data/task2-run-comparison-smoke.json),
  [MMMU proposal](../task2/MMMU_PROBE_DESIGN.md) and
  [harness contract](../task2/MMMU_HARNESS.md) checked for every quantitative claim.

Historical selections and scores were not rerun as new model observations.
All real-provider commands in the guide are source-checked templates requiring
provider/context/sandbox preflight, not freshly executed paid inference.
The 70%, 60% and 80% thresholds are explicitly illustrative, never invented
customer requirements. Smaller live-run ratios are explicitly research settings.

## Fresh native integration

The documented practice invokes a real Native evaluator against a synthetic,
loopback-only candidate/judge fixture. The initial sandboxed attempt could not
connect to loopback and failed; rerunning with loopback access succeeded using
fresh output `outputs/handout-b-verified` in the native fork:

```powershell
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/handout-b-verified
python -m evalscope_ext.tools.compare_runs --full outputs/handout-b-verified/full --pruned outputs/handout-b-verified/pruned --threshold 0.8
```

Fresh result: **12 full / 3 retained questions**, 12 / 3 attempts, scores
**1.0 / 1.0**, signed/absolute error **0 pp**, bounds **[0.25, 1.0]**,
full **GO**, subset **inconclusive**, point-only **GO**,
`decision_certified=false`, ordering unavailable for one model. Both native
evaluations and automatic comparison completed with exit 0. A separate read-only
comparison against the prior #21 saved runs also reproduced the same values.
The synthetic reduction demonstrates integration, not real compression safety.
No paid provider inference, judge call or live MMMU experiment was performed.

## Verification

From `task2/`, using the existing Python 3.12.8 environment:

```powershell
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp/issue25
```

All checks passed: **152 tests in 47.20 seconds**, Mypy **40 source files**,
Ruff lint and formatting **59 files**. The new renderer separately passed
Ruff lint/format. All four PowerShell code blocks in the guide parsed under
PowerShell 7.6.5. Both live-run blocks were then executed with a command capture
in place of Python and synthetic environment values: their four evaluation
argument lists were accepted by the pinned native CLI parser, including nested
dataset JSON, ratios, panel paths, sandbox and judge configuration. Their two
comparison argument lists were also captured. No provider was called. The
standalone comparator additionally passed on the fresh synthetic saved roots.

Documentation-only PDF dependencies came from the bundled runtime, without
adding them to benchmark dependencies. Reproduce from the submission root:

```powershell
python docs/scripts/render_handout_b.py
pdftoppm -scale-to 1800 -singlefile -png output/pdf/handout-b.pdf tmp/pdfs/handout-b
```

ReportLab output was reopened with pypdf/pdfplumber, checked for canonical text,
page count, four URI annotations, font sizes and character bounds. The Poppler
render was visually inspected: no clipped text, overlap or missing glyphs.
Poppler emitted system-font lookup warnings for unused fallback fonts; the
rendered Helvetica/Courier document was intact. Unrelated Task 1 code and the
native fork's unchanged full suite were not retested for this editorial issue.
Regenerating the final PDF produced identical bytes. All **106 local Markdown
links** across the six changed Markdown documents resolve. `git diff --check`
passed; intermediate render and command-capture files were removed.

The implement skill's independent parallel Standards and Spec reviews against
fresh main completed with **0 findings on each axis**. No implementation changes
were required. See [the two-axis review](issue-25-review.md).
