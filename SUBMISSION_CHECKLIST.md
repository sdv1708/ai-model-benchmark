# Submission checklist

This is a handoff record, not a claim that the submission form was sent.
Issue #26 completes written Task 2 documentation. Its recording requirements are
[deferred to open issue #49](https://github.com/sdv1708/ai-model-benchmark/issues/49),
at the owner's request. The video has not been cancelled; the overall submission
still requires it.

## Task 2 deliverables

| Requirement | Location / status |
| --- | --- |
| Native pruner source | Private [EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning); both adapters and comparator implemented |
| Upstream SHA prominently pinned | `66f0945d145ce6c30de40253cd78144003c6f1fe` in both READMEs |
| Tested implementation | `800119ff6870ca958f5d8459970f5fe75bfac305`; documentation provenance in [issue #26 evidence](docs/issue-26-evidence.md) |
| Setup, relevant tests and complete run contract | [final guide](task2/ISSUE_26_GUIDE.md); fork `TASK2_README.md`, `COMPARE_RUNS.md`, `AA_LCR_PRUNED.md` |
| Reproducible historical evidence | [full scores](docs/data/task2-full-scores.json), [selected policy](docs/data/task2-operating-selected.json), [fresh verification](docs/issue-26-evidence.md) |
| Handout A: one technical page | [PDF](output/pdf/handout-a.pdf), [editable source](task2/HANDOUT_A.md) |
| Handout B: half mixed-audience page | [PDF](output/pdf/handout-b.pdf), [editable source](task2/HANDOUT_B.md) |
| Multimodal roadmap | [full-MMMU proposal](task2/MMMU_PROBE_DESIGN.md), [offline harness](task2/MMMU_HARNESS.md); no live-quality result |
| Walkthrough demonstrates method, integration, evidence, trade-offs and handouts | [written demonstration/rehearsal](task2/ISSUE_26_GUIDE.md#written-walkthrough-and-demonstration); recording not made |
| Video link accessible to reviewers | **DEFERRED to [#49](https://github.com/sdv1708/ai-model-benchmark/issues/49)**; still required, no recording/URL yet |
| Both private repositories accessible to named reviewers | **Not verified in #26.** Confirm the form's reviewer identities and grant/check both repositories before submission |
| Issue #26 documentation published remotely | **Pending.** Local commits/branches must be pushed or supplied as an archive before remote reviewers can use new branch links |

## Overall challenge handoff

| Requirement | Location / status |
| --- | --- |
| Task 1 live URL | [Performance Studio](https://ai-model-quality-challenge-rho.vercel.app); prior deployment evidence in [deployment guide](docs/vercel-deployment.md), not freshly revalidated in #26 |
| Task 1 launch, upload and comparison instructions | [root README](README.md#task-1-run-from-a-clean-clone) |
| Task 1 video, at most five minutes | Tracked separately in [#13](https://github.com/sdv1708/ai-model-benchmark/issues/13); no verified URL recorded here |
| Task 2 smaller defended subset | **Unmet research ambition:** full retention is the only passing tested operating point; no compression savings claimed |
| Submission form completed | **Not performed.** Use the form linked in [README submission instructions](README.md#how-to-submit) after resolving or accepting open requirements |

When resuming #49, cover the seven walkthrough beats, use synthetic fixture
results with their labels visible, show both handouts, and state 0% defended
pruning. Add the actual video URL here and verify reviewer access while signed
out or from a reviewer account. A placeholder URL or this script is not a video.
