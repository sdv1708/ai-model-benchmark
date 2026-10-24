# Portfolio readiness and original submission checklist

## Current scope: personal portfolio

On 2026-10-23 the owner clarified: "I am not following the exact rules, I want
to showcase this as my own project." Issue #27 is implemented against that
updated direction. No challenge-reviewer invitation, repository visibility
change, video, or form submission is required for this portfolio audit.
Original requirements are retained below for provenance, not silently marked met.

| Portfolio item                               | Location / status                                                                                                                                            |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Clear project identity and public entrypoint | [Performance & Quality Lab](README.md), [tour and copy-ready description](docs/PORTFOLIO.md)                                                                 |
| Working public performance demo              | [Performance Studio](https://ai-model-quality-challenge-rho.vercel.app); fresh complete browser verification in [issue #27 audit](docs/issue-27-evidence.md) |
| Reproducible source/data and honest claims   | [Requirement/evidence matrix and fresh-clone results](docs/issue-27-evidence.md)                                                                             |
| Native implementation availability           | EvalScope companion is still private; its source/demo requires access. Public analysis and saved evidence are available; no visibility change performed      |
| Written demonstration, no video needed       | [Five-minute demo](docs/PORTFOLIO.md#a-five-minute-demonstration-without-video)                                                                              |
| Detailed beginner-to-interview explanations  | [Issue #27 guide](docs/ISSUE_27_GUIDE.md)                                                                                                                    |
| Owner has completed an independent rehearsal | **Not established.** [Questions and self-checks](docs/ISSUE_27_GUIDE.md#13-rehearsal-without-a-recording) are prepared; practice remains the owner's step    |
| Code review and validation                   | [Audit](docs/issue-27-evidence.md), [independent review](docs/issue-27-review.md)                                                                            |

## Original challenge handoff

This is a handoff record, not a claim that the submission form was sent.
Issue #26 completes written Task 2 documentation. Its recording requirements are
[deferred to open issue #49](https://github.com/sdv1708/ai-model-benchmark/issues/49),
at the owner's request. The video has not been cancelled; the overall submission
still requires it.

## Task 2 deliverables

| Requirement                                                                     | Location / status                                                                                                                                                                                            |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Native pruner source                                                            | Private [EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning); both adapters and comparator implemented                                                                               |
| Upstream SHA prominently pinned                                                 | `66f0945d145ce6c30de40253cd78144003c6f1fe` in both READMEs                                                                                                                                                   |
| Tested implementation                                                           | `800119ff6870ca958f5d8459970f5fe75bfac305`; documentation provenance in [issue #26 evidence](docs/issue-26-evidence.md)                                                                                      |
| Setup, relevant tests and complete run contract                                 | [final guide](task2/ISSUE_26_GUIDE.md); fork `TASK2_README.md`, `COMPARE_RUNS.md`, `AA_LCR_PRUNED.md`                                                                                                        |
| Reproducible historical evidence                                                | [full scores](docs/data/task2-full-scores.json), [selected policy](docs/data/task2-operating-selected.json), [fresh verification](docs/issue-26-evidence.md)                                                 |
| Handout A: one technical page                                                   | [PDF](output/pdf/handout-a.pdf), [editable source](task2/HANDOUT_A.md)                                                                                                                                       |
| Handout B: half mixed-audience page                                             | [PDF](output/pdf/handout-b.pdf), [editable source](task2/HANDOUT_B.md)                                                                                                                                       |
| Multimodal roadmap                                                              | [full-MMMU proposal](task2/MMMU_PROBE_DESIGN.md), [offline harness](task2/MMMU_HARNESS.md); no live-quality result                                                                                           |
| Walkthrough demonstrates method, integration, evidence, trade-offs and handouts | [written demonstration/rehearsal](task2/ISSUE_26_GUIDE.md#written-walkthrough-and-demonstration); recording not made                                                                                         |
| Video link accessible to reviewers                                              | **DEFERRED to [#49](https://github.com/sdv1708/ai-model-benchmark/issues/49)**; still required, no recording/URL yet                                                                                         |
| Both private repositories accessible to named reviewers                         | #27 verified the form's identities and found only the owner on both collaborator lists, with no pending invitations. **Reviewer access is not granted.** Invitations are outside the current portfolio scope |
| Issue #26 documentation published remotely                                      | **Merged:** native main `f06acd10c80470696f3d719f079e3094e448d2d8`; challenge main `17e6cf060749efde007eb4996350764f79902e34`, freshly cloned for #27                                                        |
| Submission repository visibility                                                | On the #27 audit, `sdv1708/ai-model-benchmark` is **public** and EvalScope is **private**. This is allowed by the current portfolio scope; the original private-submission criterion is unmet                |

## Overall challenge handoff

| Requirement                                       | Location / status                                                                                                                                                                                                       |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Task 1 live URL                                   | [Performance Studio](https://ai-model-quality-challenge-rho.vercel.app); freshly revalidated in [#27](docs/issue-27-evidence.md), with earlier deployment evidence in the [deployment guide](docs/vercel-deployment.md) |
| Task 1 launch, upload and comparison instructions | [root README](README.md#task-1-run-from-a-clean-clone)                                                                                                                                                                  |
| Task 1 video, at most five minutes                | Tracked separately in [#13](https://github.com/sdv1708/ai-model-benchmark/issues/13); no verified URL recorded here                                                                                                     |
| Task 2 smaller defended subset                    | **Unmet research ambition:** full retention is the only passing tested operating point; no compression savings claimed                                                                                                  |
| Submission form completed                         | **Not performed.** Use the form linked in [README submission instructions](README.md#how-to-submit) after resolving or accepting open requirements                                                                      |

When resuming #49, cover the seven walkthrough beats, use synthetic fixture
results with their labels visible, show both handouts, and state 0% defended
pruning. Add the actual video URL here and verify reviewer access while signed
out or from a reviewer account. A placeholder URL or this script is not a video.
