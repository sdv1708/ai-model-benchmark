# Issue #27: portfolio and evidence audit

Audit date: **2026-10-23, America/Los_Angeles**.
Original issue: [#27](https://github.com/sdv1708/ai-model-benchmark/issues/27).
Machine-readable results: [verification snapshot](data/issue-27-audit.json).

## Owner-directed scope

The initial request was to implement issue #27, pull latest main, create a branch,
research/verify the result, explain it from first principles, and probably skip
video components. During implementation the owner clarified: **"I am not
following the exact rules, I want to showcase this as my own project."**

The active deliverable is therefore a personal portfolio audit and written
interview/demo package. Original private-repository requirements, challenge
reviewer invitations, recordings, and form submission are outside this scope.
They are not marked fulfilled. The owner has not completed an observed interview
rehearsal. No issue closure, form submission, invitation, visibility change, push,
merge, or deployment was performed by this audit.

The project remains AI-assisted and based on the preserved challenge inputs and
EvalScope upstream. Project ownership does not imply sole authorship of those
inputs. Public portfolio wording distinguishes implementation, historical
measurements, synthetic tests, research proposals and unestablished claims.

## Changes and provenance

The working tree was initially clean. In the nested challenge checkout,
`main` was fast-forwarded from `7882d16` to
`17e6cf060749efde007eb4996350764f79902e34`, then branch
`feature/issue-27-submission-audit` was created. This is the fixed review base.

New GitHub HTTPS clones were made at:

- `D:/ai-model-quality-challenge-main/issue-27-clean-clone`, depth 1, challenge
  main `17e6cf060749efde007eb4996350764f79902e34`.
- `D:/ai-model-quality-challenge-main/issue-27-native-clone`, depth 1, native
  main `f06acd10c80470696f3d719f079e3094e448d2d8`.

No existing project virtual environments, node_modules, generated fixtures, or
local LFS objects were copied into those clones. Machine toolchains, package
caches and installed Chromium could be reused. This is fresh project setup on
Windows, not a fresh operating system or an anonymous-access audit. The native
clone used the owner's existing GitHub authentication; its source remains private.
Upstream base stays `66f0945d145ce6c30de40253cd78144003c6f1fe`.

This issue adds the [portfolio tour](PORTFOLIO.md),
[beginner-to-interview guide](ISSUE_27_GUIDE.md), this audit and its snapshot,
and updates the README/checklist. No selection policy, grading semantics,
customer rules, or application UI changed. Optional TDD is not applicable to
these editorial changes and a dependency-lock repair; existing public-boundary
regressions verify behavior. No new unagreed test seam was introduced.

## Original requirements mapped to evidence

This matrix preserves the original brief as an audit reference. A mapped item
can still be unfulfilled; the portfolio scope does not retroactively satisfy
the original submission rubric.

| Original requirement                                                           | Concrete evidence and status                                                                                                                                                                                           |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Task 1 documented clean-clone installation/launch                              | [README](../README.md#task-1-run-from-a-clean-clone), earlier [exact dev-launch evidence](issue-12-evidence.md); fresh installs, local build/managed API launch and tests below                                        |
| Publicly reachable deployed frontend, prominent URL                            | First README link; fresh production browser suite and `/` + `/health` HTTP checks                                                                                                                                      |
| Runtime upload of one or many sweeps, no rebuild                               | Existing upload/resilience browser tests pass against production; real upload API, independent generated fixture bytes                                                                                                 |
| First-class comparison for both audiences                                      | Customer/engineering browser tests; dynamic aligned rows in [comparison API](../backend/src/perf_api/comparison.py) and UI                                                                                             |
| Twelfth unseen Model L with zero code edits                                    | Fresh generated Model L drives comparison, verdict evidence and engineering inspection in the production suite                                                                                                         |
| Customer good-enough signal with familiar units                                | [Decision rules](../backend/src/perf_api/decision.py), explicit targets/assumptions; fresh live A GO/C NO GO example below                                                                                             |
| Engineer sanity checks, configuration shifts and anomalies                     | [Engineering rules](../backend/src/perf_api/engineering.py); browser coverage of sourced rows, flags and batch/cache controls                                                                                          |
| Not a static spreadsheet dump / one undifferentiated giant table               | Separate customer decisions and engineering inspection; tests exercise both flows                                                                                                                                      |
| Not every column for every audience                                            | Audience-specific components and [design rationale](task1-analysis.md); customer decision inputs/evidence differ from engineering detail                                                                               |
| No model-specific hard-coded views/copy                                        | Filename-derived identities, scenario keys, Model L regression; supplied sample is optional                                                                                                                            |
| Not a build-time upload substitute                                             | Actual deployed multipart ingestion; no rebuild between uploads                                                                                                                                                        |
| Task 1 framework choice, cuts, assumptions and future changes                  | [Design analysis](task1-analysis.md), [new interview guide](ISSUE_27_GUIDE.md)                                                                                                                                         |
| Model A-K sizes and profile 1-7 use cases                                      | [Complete analysis](task1-models-and-profiles.md), 77 workbooks/275 rows; size hypotheses are conditional, not identified parameter counts                                                                             |
| Task 1 source/live URL/video <=5 min                                           | Source and URL available; **no verified video**. Original #13 remains open, outside portfolio scope                                                                                                                    |
| Task 2 full baseline with predictions/reviews joined by index                  | Fresh `benchmark-reference` replay validates 28 pairs, 56 files, 1,905 samples; all six Part A scores exactly match saved JSON                                                                                         |
| Coding and long-context compression that preserves a useful signal             | [Policy/curves](issue-17-evidence.md) reproduced; **validated smaller benchmark ambition remains unmet**. Only 315/315 and 100/100 retained pass all tested gates                                                      |
| Account for AA-LCR judge nondeterminism                                        | [Judge-noise study](issue-16-evidence.md), [guide](ISSUE_27_GUIDE.md#9-the-judge-is-another-robot): one verdict cannot identify variance; no invented repeated-judge estimate                                          |
| Pruners live inside public EvalScope codebase, clean extension and conventions | Native derived source, registered adapters, `DefaultDataAdapter.load_subset`, weighted aggregation; 242 relevant framework tests, lint/types/import contracts pass. Derived repo itself is private                     |
| Pin EvalScope development SHA                                                  | Both README entrypoints and [baseline provenance](../task2/evalscope-baseline.json); upstream and tested native main above                                                                                             |
| Full/pruned/compare run contract                                               | [Native setup/demo](../task2/ISSUE_26_GUIDE.md), [provider runbook](../task2/ISSUE_25_GUIDE.md#7-real-endpoint-runbook); fresh synthetic saved-run comparison. Provider templates were not live-inference tested       |
| No uniform-random/easiest-only/hardest-only defended method                    | Structured difficulty and length/difficulty strategies; forbidden extremes/random used only as comparison baselines; policy never selects baselines                                                                    |
| No hand-picked subset                                                          | Population matching, coverage allocation and deterministic seeded hash selection; source identities/fingerprints retained                                                                                              |
| Defensible for an unseen fourth model; avoid three-model overfit               | Target exclusions, model/pair holdouts and limitations documented; **fourth-model transfer is not validated**. Freeze future policy before fresh-model confirmation                                                    |
| Full MMMU rather than only 660 reference rows                                  | [Full-dataset design](../task2/MMMU_PROBE_DESIGN.md), official pinned inventory: 11,550 questions / 30 subjects                                                                                                        |
| Probe encoder-specific weakness with standard API                              | Proposed paired visual stressors and no-image/factual-text/perception controls; [offline harness](../task2/MMMU_HARNESS.md) is synthetic. **Encoder-only causality is not established** through black-box API evidence |
| Handout A: one technical page; method, pruning, MMMU, assumptions, next work   | [PDF](../output/pdf/handout-a.pdf), [source](../task2/HANDOUT_A.md); one A4 page, freshly rendered and inspected                                                                                                       |
| Handout B: half-page mixed audience; value, use, signal, PM relevance          | [PDF](../output/pdf/handout-b.pdf), [source](../task2/HANDOUT_B.md); content occupies about half of one A4 page, freshly rendered and inspected                                                                        |
| Both repositories private with named reviewer access                           | Main **PUBLIC**, native **PRIVATE**, owner only; no pending invitations. Original criterion unmet and outside portfolio scope; native privacy remains a public-inspection limitation                                   |
| Videos accessible, final form prepared/submitted                               | Actual form inspected without entering/submitting data. Both video fields required there; no URLs exist. Outside current scope, so no form answers or video placeholders were invented                                 |
| Learner completes rehearsal across backend/statistics/integration/trade-offs   | [14-part explanation and practice questions](ISSUE_27_GUIDE.md), [demo tour](PORTFOLIO.md); **prepared, not observed completed**                                                                                       |

## Fresh verification results

Toolchain: Python **3.12.8**, uv **0.11.0**, Node **24.15.0**, npm **11.12.1**,
Git LFS **3.7.1**. Install dependencies from the versioned locks/snapshot; the
toolchain versions here are tested versions, not a claim that they are latest.

| Check                                                                       | Result                                                                                                                        |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Remote challenge clone with smudge skipped, then explicit `git lfs pull`    | Passed; 56 JSONL files, **964,345,076 bytes** downloaded                                                                      |
| `git lfs fsck`, manifest hash comparison                                    | Passed; every one of 56 source hashes matches the checked-in reference manifest                                               |
| Backend `uv sync --locked`, complete pytest suite                           | Passed; **56 passed**, 4 upstream dependency deprecation warnings, 2.33 s                                                     |
| Backend Mypy / Ruff check / Ruff format                                     | Passed; **24** typed source files / **29** formatted files                                                                    |
| Task 2 `uv sync --locked`, complete pytest suite                            | Passed; **152 passed**, 53.56 s                                                                                               |
| Task 2 Mypy / Ruff check / Ruff format                                      | Passed; **40** typed source files / **60** formatted files                                                                    |
| Fresh `npm ci` with baseline lock                                           | Passed; 77 installed packages, reported two high-severity dependency findings                                                 |
| Updated locked install and production build                                 | Passed; TypeScript build, Vite **6.4.5**, 38 modules                                                                          |
| Complete production browser suite                                           | **32 passed**, 30.7 s, 0 skipped; fresh isolated browser contexts against the public origin                                   |
| Complete local built-app browser suite with repaired lock                   | **32 passed**, 29.6 s, 0 skipped; preview 4174 / real API 8018                                                                |
| Native documented dependency setup + optional inherited judge prerequisites | Passed in the separate fresh GitHub clone                                                                                     |
| Complete documented relevant native suite                                   | **242 passed**, 189 upstream warnings, 276.61 s                                                                               |
| Native Mypy / Ruff / import contracts                                       | Passed; **6** typed files / **4** extension files formatted / **5 kept, 0 broken** contracts                                  |
| Historical reference replay                                                 | 28 pairs, 56 files, 1,905 samples; full six-score JSON equals checked-in record                                               |
| Historical operating-point replay                                           | Selected fields, limitations and plan equal saved extract; full retention on both benchmarks; production certification false  |
| Native synthetic local-endpoint smoke and standalone comparator             | Passed; 12/3 questions, 1.0/1.0 scores, 0 pp, [0.25, 1.0] completion bounds; subset inconclusive at 0.8                       |
| Live HTTP probes                                                            | `/` and `/health` 200; unknown API path JSON 404                                                                              |
| Supplied A/C workbooks uploaded to live API                                 | Real ZIP bytes, 10,000/333/50% scenario: A GO batch 20; C NO GO representative batch 10; engineering returns 8 configurations |
| Existing handout PDFs                                                       | Both open, one A4 page each; rendered and visually inspected, no clipping/overlap observed                                    |

Some browser resilience cases deliberately inject failure responses; the successful
upload, customer-decision and engineering flows use the real API. Automated axe,
keyboard and narrow-screen checks are not a human screen-reader audit or actual
200% browser-zoom audit. The native suite is the entire documented **relevant**
suite, not the complete optional-dependency upstream test collection.

The first restricted-sandbox backend pytest process stalled. Its existing health
test and complete suite passed with normal host permissions; the stalled audit
process was stopped. No application workaround or test alteration was introduced.
No `.env` or provider key was copied into the native clone; CI-lite used its mock
model. The native synthetic endpoint only listened locally and made no paid calls.

## Dependency findings repaired

Fresh npm audit reported source-map-js **1.2.1** and Vite **6.4.3**. Updated only
those resolved packages, within existing declared ranges, to **1.2.2** and
**6.4.5**. The lockfile changes only versions, URLs and integrity hashes for those
two entries. `npm audit --json` on the repaired lock reports **0 known
advisories**. This is a time-specific npm result, not a comprehensive security
audit of Python dependencies, application logic or the deployed system.

Research checked the
[source-map advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q),
[Vite Windows editor-path advisory](https://github.com/advisories/GHSA-587h-7wmj-h5pm)
and [Vite middleware advisory](https://github.com/advisories/GHSA-9jrq-w75r-8gcw).
The Vite advisory lists 6.4.4 as a patched 6.x release; 6.4.5 is the resolved
compatible version tested here. No exploit was attempted. Local installation,
build and browser verification use the repaired lock. The deployed app was
verified independently, but **this branch was not deployed**, so this audit does
not assert that production has received the dependency repair.

## Reproduction commands

From new clones using the README prerequisites and canonical GitHub URLs, follow
the README for backend/frontend installs, then:

```powershell
# From backend/
New-Item -ItemType Directory -Path .pytest-tmp -Force > $null
uv run pytest --basetemp=.pytest-tmp/audit -q
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

```powershell
# From frontend/, after using this branch's package-lock.json
npm ci
npm audit
npm run build
npm run test:e2e:built -- --workers=2
$env:PLAYWRIGHT_BASE_URL = 'https://ai-model-quality-challenge-rho.vercel.app'
npm run test:e2e:services -- --workers=2
Remove-Item Env:PLAYWRIGHT_BASE_URL
```

```powershell
# From the main project root, with LFS installed
git lfs pull
git lfs fsck
cd task2
uv sync --locked
uv run benchmark-reference --data-root ../Evals --output-dir output/audit-reference
uv run part-a-operating-points --data-root ../Evals --output-dir output/audit-operating --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
New-Item -ItemType Directory -Path .pytest-tmp -Force > $null
uv run pytest --basetemp=.pytest-tmp/audit -q
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

The exact native installation, relevant 242-test command, type/lint/import checks
and demo are in the native repository's `TASK2_README.md` at the verified commit.
Install `requirements/pruning-baseline.txt`, install editable `--no-deps`, add
`scikit-learn==1.9.1 threadpoolctl==3.7.0` for the inherited judge regressions,
create `.pytest-tmp`, and ensure no `.env` before its CI-lite run. Use a new demo
output directory. A shallow clone at native main works for this audit; the older
runtime pin requires fetching history or a normal full clone.

## Research and verification boundaries

The [original Task 1](../Task1_Performance.md),
[Task 2](../Task2_Model_Quality.md), parent #1, issue #27 and its prerequisites
#13/#26/#49 were read. GitHub reports #26 closed and both video issues open.
The native documentation PR is merged; older "merge pending" checklist language
was corrected. Original issue ownership labels do not override the owner's
explicit implementation and subsequent portfolio-scope instructions.

The [actual submission form](https://docs.google.com/forms/d/e/1FAIpQLSdwLrRJkKUgTd2sisyJO10VSf1-1vJ3NIywV5HtMlUSc7ijMw/viewform)
lists Name, Email, repo link, Task 1 video, optional deployed URL, Task 2 video,
and additional notes. Its repo prompt names `sophies-cerebras`,
`danielkim-cerebras`, and `kevint-cerebras`. Those GitHub identities resolve,
but no invitation was sent after the owner changed scope. Only the owner was
listed as collaborator, and both invitation lists were empty when inspected.
No human name/email was guessed and no form field was filled.

[GitHub's LFS documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
explains why pointers alone are insufficient; the remote download and all source
hashes were checked here. The
[official pinned MMMU source](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md)
confirms 150/900/10,500 splits, while pinned local code defines actual EvalScope
behavior. Rolling docs and prior evidence are not substitutes for these checks.

Logs/artifacts remain in the audit clones and ignored `task2/output/issue27`.
The committed JSON is a compact result snapshot, not a full log or a guarantee
that links, hosting or dependency advisories will remain unchanged.
Independent review is recorded [separately](issue-27-review.md).

## Final documentation and review checks

All **131 local Markdown links**, including **13 heading targets**, resolve in
the changed documents. All **9 PowerShell blocks** parse. Both the evidence JSON
and frontend lockfile parse, changed documentation passes Prettier, and
`git diff --check` passes. The independent review reports **0 Standards findings
and 0 Spec findings**. Its one handoff note, to populate the review record, is
resolved. The final follow-up changes only this verification note and the review
record, so no runtime suite rerun is warranted.
