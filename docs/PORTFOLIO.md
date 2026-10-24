# Performance & Quality Lab: portfolio tour

[Open Performance Studio](https://ai-model-quality-challenge-rho.vercel.app) |
[Source](https://github.com/sdv1708/ai-model-benchmark) |
[Interview guide](ISSUE_27_GUIDE.md) |
[Audit](issue-27-evidence.md)

## The problem

A model can be fast and still produce poor answers. It can also answer well but
serve a workload too slowly. This project investigates those two requirements
with separate evidence: performance projections for serving decisions, and saved
benchmark grades for quality evaluation. It does not combine them into an
unsupported overall model ranking.

## What is implemented

**Performance Studio** is a deployed React/TypeScript application backed by a
typed FastAPI service. Upload conforming Excel sweeps for one or several models,
including model names absent from the supplied archive. A customer gets GO,
NO GO, or NEEDS DATA against explicit targets. An engineer gets aligned
comparisons, per-box metrics, controlled batch/cache trends, and sourced review
flags. The app processes uploads at runtime and keeps its workspace in page
memory; it has no accounts or database.

**Evaluation research and integration** validates saved predictions/reviews,
reproduces six full coding/long-context scores, experiments with structured
question selection, and compares score, ordering, and decision fidelity. The
actual registered pruners and saved-run comparator live inside a separately
versioned [EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning).
That repository is currently private. Public readers can inspect this project's
analysis, exported panels, tests, handouts and evidence; they cannot inspect or
run the private native source without access. Do not present that link as a
publicly reproducible native implementation.

**Multimodal research** proposes paired visual stresses and text controls over
the full MMMU inventory. The existing offline harness demonstrates synthetic
image transformations and response analysis. It is not a completed live-model
study or proof of an image-encoder defect.

## Results that can be defended

| Observation                                                       | Meaning and limit                                                                                                         |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 77 supplied workbooks, 11 models, 7 profiles, 275 normalized rows | Reproducible projection analysis; not production measurements                                                             |
| Saved coding scores: 241/315, 198/315, 195/315                    | Historical model outputs; not scores for today's endpoints                                                                |
| Saved long-context scores: 48/100, 66/100, 64/100                 | Historical judge grades; repeated-judge variance is unknown                                                               |
| 315/315 coding and 100/100 long-context retained                  | Only full retention passes every gate on the tested grid; 0% demonstrated sample saving                                   |
| Synthetic native demo: 12 full / 3 retained, both 100%            | Integration works; unknown questions still allow a 25%-100% complete score, so the subset decision is inconclusive at 80% |

The model order in both score rows is gpt-oss-120b, kimi-k2.5, minimax-m2.5.
See the [fresh audit](issue-27-evidence.md) for tested commits, scope and results.

## A five-minute demonstration without video

1. Open the live app in a new browser session. Click **Load sample workbook**.
   Explain capacity, generation speed and time to first token as different metrics.
2. Follow the [README](../README.md#task-1-run-from-a-clean-clone) to extract the
   supplied archive. Upload Model A and Model C profile 1 together. Choose
   10,000 input tokens / 333 output tokens / 50% cache. Set minimum capacity
   **400000**, minimum generation speed **1200**, maximum TTFT **10**.
   Model A has GO at batch 20; Model C has NO GO. Read the per-row evidence.
3. Open engineering inspection. Explain total versus per-box capacity, why a
   review flag needs investigation, and why differing cache/length settings do
   not identify the causal effect of caching. Show invalid-upload recovery if time permits.
4. Show the [full scores](data/task2-full-scores.json), then the
   [retention policy](data/task2-operating-selected.json). State the zero-saving
   outcome before describing the selection method. Use the
   [native demo recipe](../task2/ISSUE_26_GUIDE.md#path-a-install-and-demonstrate-the-native-integration)
   if you have private-source access. Otherwise use the checked-in
   [synthetic comparison evidence](data/task2-issue26-native-smoke.json), labelled
   as saved evidence rather than a run you just performed.
5. Show [Handout A](../output/pdf/handout-a.pdf) for engineers and
   [Handout B](../output/pdf/handout-b.pdf) for mixed audiences. Finish with the
   [MMMU proposal](../task2/MMMU_PROBE_DESIGN.md) and the next experiment:
   freeze the policy, evaluate an untouched model, repeat judging, and measure
   actual tokens, elapsed time and cost.

The Model L browser regression proves unseen-model support with independently
generated workbook bytes; it does not require adding a model to application code.
Commands and automated checks are in the README and audit. No recording is
needed for this portfolio presentation.

## Copy-ready project description

> Performance & Quality Lab connects a deployed model-performance analysis tool
> with reproducible evaluation research. Its React/TypeScript and FastAPI app
> ingests new Excel sweeps, compares models, and explains workload decisions for
> customers and engineers. Its evaluation work tests structured coding and
> long-context benchmark selection through native EvalScope adapters and a
> saved-run comparator. The tested smaller subsets did not meet all fidelity
> gates, so the supported default retains the full reference set. The project
> also includes a controlled multimodal probe proposal and a synthetic image
> harness, with evidence and limitations documented throughout.

Possible resume bullets, after rehearsing the details:

- Developed a React/TypeScript and FastAPI performance-analysis project with
  runtime Excel ingestion, multi-model comparison, explicit workload decisions,
  and traceable engineering diagnostics.
- Integrated structured benchmark selection and weighted reporting into
  EvalScope; evaluated historical score, rank and decision fidelity and retained
  full-reference defaults when smaller tested candidates failed the policy.
- Built reproducible reference analysis and documented a paired-image
  multimodal study with controls that distinguish visual-path sensitivity from
  unsupported encoder-causality claims.

Use verbs that match your own contribution and understanding. This is an
AI-assisted project built on open-source tools and challenge-provided synthetic
projections/saved evaluations. Ownership of the project is compatible with
crediting those inputs and assistance. Do not claim all framework code or source
datasets as your original work, an accepted upstream contribution, a real
customer deployment, measured production savings, or independent research
validation that has not happened.

## Portfolio readiness and next steps

The written project story and demo are available. The private native repository
limits public inspection of that component. Making it public or preparing a
separately shareable source package would be a separate publishing decision;
no visibility settings or invitations were changed in this audit.

The [interview rehearsal](ISSUE_27_GUIDE.md#13-rehearsal-without-a-recording) supplies
questions and self-checks. A prepared guide does not prove that its owner has
completed the rehearsal. Dependency findings and live verification outcomes are
recorded in the audit, with their actual scope.

The original challenge briefs remain [Task 1](../Task1_Performance.md) and
[Task 2](../Task2_Model_Quality.md). Videos, reviewer access and form submission
are outside the owner's current portfolio scope. Original submission compliance
is not claimed.
