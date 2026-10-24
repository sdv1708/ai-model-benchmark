# AI Engineer — Model Quality & Performance Challenge

**Live Task 1 app:** [Performance Studio](https://ai-model-quality-challenge-rho.vercel.app)

Welcome, and thanks for taking the time. This challenge has two independent tasks.

## Task 2 full-benchmark reference analysis

Issue #25 supplies [Handout B: Why this matters and how to use it (half-page PDF)](./output/pdf/handout-b.pdf),
its [editable source](./task2/HANDOUT_B.md), and a
[beginner-to-interview guide with operational commands](./task2/ISSUE_25_GUIDE.md).
It translates the defended full-retention result into customer guidance,
GO/NO GO/inconclusive interpretation and a runnable synthetic practice workflow.
See [acceptance evidence](./docs/issue-25-evidence.md).

Issue #24 supplies [Handout A: Why this works (one-page PDF)](./output/pdf/handout-a.pdf),
its [editable source](./task2/HANDOUT_A.md), and a
[first-principles interview guide](./task2/ISSUE_24_GUIDE.md).
The handout defends 0% pruning on the tested Part A grid and distinguishes
the proposed MMMU study from synthetic validation. See [acceptance evidence](./docs/issue-24-evidence.md).

Issue #23 implements an [offline paired-image harness](./task2/MMMU_HARNESS.md)
and [beginner-to-interview walkthrough](./task2/ISSUE_23_GUIDE.md): reproducible
degradations, stable pair identities, future request plans and saved-response
diagnostics. Its demo uses synthetic images and scripted responses; no new
live-model conclusion is claimed. See [acceptance evidence](./docs/issue-23-evidence.md).

Issue #22 adds the [full-dataset MMMU visual-path probe proposal](./task2/MMMU_PROBE_DESIGN.md)
and [beginner-to-interview guide](./task2/ISSUE_22_GUIDE.md). It distinguishes the
11,550-question official inventory from the 660 supplied references and specifies
sampling, visual stressors, controls and API measurement. This is a researched,
unrun design, not validated multimodal compression. See [acceptance evidence](./docs/issue-22-evidence.md).

Read the [complete Task 2 issues #14–#17 walkthrough](./task2/ISSUE_17_GUIDE.md)
for worked examples and the shared operating-point policy. Its conservative
illustrative requirements retain the full recorded references: no smaller tested
candidate meets every score, ranking and decision gate. See
[issue #17 evidence](./docs/issue-17-evidence.md) for reproduction and limitations.

The [reference-analysis package](./task2/README.md) validates all supplied evaluation
artifacts and reproduces six full LiveCodeBench/AA-LCR model scores without live
inference. Run from the repository root with Python 3.12 and uv:

```powershell
cd task2
uv sync --locked
uv run benchmark-reference --data-root ../Evals --output-dir output/reference
```

See the [implementation and interview guide](./task2/INTERVIEW_GUIDE.md) and
[issue #14 acceptance evidence](./docs/issue-14-evidence.md). The
[native EvalScope baseline](./task2/ISSUE_18_GUIDE.md) is now established in a
private derived repository, with a registered synthetic smoke benchmark and
[pinned source versions](./task2/evalscope-baseline.json).
Issue #21 adds the [saved full-versus-pruned comparison workflow and interview guide](./task2/ISSUE_21_GUIDE.md),
with validated counts, weighted score differences, ordering/threshold evidence and
explicit uncertainty limits. See [acceptance evidence](./docs/issue-21-evidence.md).

Issue #19 adds the [native LiveCodeBench pruner](./task2/ISSUE_19_GUIDE.md), with
fingerprint-bound historical selection, configurable retained ratios, weighted
reporting and framework tests. Its default retains all 315 recorded coding tasks,
consistent with issue #17; smaller ratios remain experimental.

Issue #20 adds the [native AA-LCR pruner and learning guide](./task2/ISSUE_20_GUIDE.md),
with pinned historical source identities, length/difficulty selection, explicit
judge-noise limits and 1,200 native parity cases. Its defended default retains
all 100 questions. See [acceptance evidence](./docs/issue-20-evidence.md).

Issue #15 adds [LiveCodeBench pruning experiments](./task2/ISSUE_15_GUIDE.md): two
reference-only stratified candidates, three comparison baselines, exact finite-pool
uncertainty, threshold abstention, and 3,000 score/pair-transfer evaluations. From `task2/`, run
`uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning`.
See [measured fidelity and acceptance evidence](./docs/issue-15-evidence.md).

Issue #16 adds [AA-LCR long-context pruning and judge-noise analysis](./task2/ISSUE_16_GUIDE.md):
metadata-aware candidates, five retention levels, independent model-pair checks,
and explicit separation of subset uncertainty from unidentifiable judge randomness.
From `task2/`, run `uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-pruning`.
See [measured results and acceptance evidence](./docs/issue-16-evidence.md).

## Task 1 deployment

Task 1 is configured as one Vercel project with two services in the root
[`vercel.json`](./vercel.json): the Vite frontend and FastAPI backend. Both use
one domain; `/api/*` and `/health` reach the backend and other paths reach the
frontend. See [`docs/vercel-deployment.md`](./docs/vercel-deployment.md) for
local services verification, deployment settings, and the live smoke procedure.

## Task 1: run from a clean clone

Install Git, Node.js **24.x** (includes npm), Python **3.12**, and
[uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.13 is
outside the backend's declared version range. GitHub access to this private
repository is required to clone. Task 1 needs no API keys or environment file.

```powershell
git clone https://github.com/sdv1708/ai-model-quality-challenge.git
cd ai-model-quality-challenge
cd backend
uv sync --locked
cd ../frontend
npm ci
cd ..
```

From the repository root, start the API in terminal 1:

```powershell
cd backend
uv run uvicorn perf_api.main:app --reload --host 127.0.0.1 --port 8000
```

From the repository root, start the frontend in terminal 2:

```powershell
cd frontend
npm run dev -- --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. The frontend proxies `/api` to the API on port 8000.
The standalone health endpoint is <http://127.0.0.1:8000/health> and interactive
API documentation is <http://127.0.0.1:8000/docs>. Stop each server with Ctrl+C.
These shell commands also work in a POSIX shell; the extraction command below
is specifically for PowerShell.

Click **Load sample workbook** to use the bundled Model A workbook through the real API.
To compare supplied models, extract the archive from the repository root:

```powershell
Expand-Archive -LiteralPath perf_data.zip -DestinationPath perf_data
```

Upload `perf_data/Model_A_profile_1/Model A profile 1.xlsx` together with
`perf_data/Model_C_profile_1/Model C profile 1.xlsx`. Select profile 1 and the
10,000-input / 333-output / 50%-cache scenario. For a concrete customer example,
set minimum capacity to **400000**, minimum generation speed to **1200**, and
maximum TTFT to **10**; leave context and cost limits empty. Model A has a GO
configuration at batch 20; Model C is NO GO. Inspect their evidence and the
engineering section. These are projection-based decisions. The engineering
batch selector controls inspection; customer evaluation searches matching rows.

On macOS/Linux, use `unzip perf_data.zip -d perf_data`. Git LFS is needed for
Task 2's `Evals/**/*.jsonl`, but the Task 1 archive and public sample are ordinary
tracked files. A Task 1-only clone can leave those evaluation files as LFS
pointers; do not mistake them for usable Task 2 data.

## Task 1 analysis and verification

- [Architecture, audience choices, assumptions, and trade-offs](./docs/task1-analysis.md)
- [Evidence-backed model A–K estimates and profile 1–7 use cases](./docs/task1-models-and-profiles.md)
- [Clean-clone verification and issue #12 acceptance evidence](./docs/issue-12-evidence.md)
- [Backend API and checks](./backend/README.md), [frontend and browser checks](./frontend/README.md)
- [Deployment configuration and production smoke evidence](./docs/vercel-deployment.md)

To check a fresh installation, run the following from the repository root:

```powershell
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
cd ../frontend
npx playwright install chromium
npm run test:e2e:built
```

The built browser suite builds the frontend and starts its own API on **8018**
and preview server on **4174**; keep those ports free. It exercises fresh-model
uploads, both audiences, comparisons, validation recovery, and accessibility.
For the earlier resilience work, see [`ISSUE_10_GUIDE.md`](./ISSUE_10_GUIDE.md).

Read each task's spec in full before starting. Each lists hard requirements and a
set of **forbidden trivial baselines** that will not pass the rubric.

---

## What's in this repo

| Path                     | What it is                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `Task1_Performance.md`   | Task 1 spec — performance UI for customer + internal audiences                                                |
| `Task2_Model_Quality.md` | Task 2 spec — benchmark/eval pruning inside `evalscope`                                                       |
| `perf_data.zip`          | Task 1 data — perf projections, Models A–K × 7 traffic profiles (`.xlsx`)                                     |
| `Evals/`                 | Task 2 data — model outputs (`predictions/`) + per-sample scores (`reviews/`) for LiveCodeBench, AA-LCR, MMMU |

> **Git LFS:** the files under `Evals/` are stored via [Git LFS](https://git-lfs.github.com/).
> Install it (`git lfs install`) before cloning, or the `.jsonl` files will appear as
> small pointer stubs instead of the real data.

---

## The two tasks

### Task 1 — Performance UI for Customer and Product

Turn an internal `.xlsx` perf projection sheet into something two audiences can act on:
a customer/PM who needs a **go/no-go** signal, and an internal engineer who needs to
**sanity-check** a projection. See [`Task1_Performance.md`](./Task1_Performance.md).

Run contract: document your own install and launch steps in your README — a reviewer
will clone and follow them. Your choice of framework and packaging. **Also deploy it:**
ship a publicly reachable URL (a free host is fine — Vercel, Netlify, Cloudflare Pages,
GitHub Pages, …) so a reviewer can click through without cloning, and let them **upload
one or more perf sweeps to render and compare the views live** (we'll test it with a new
model). See [`Task1_Performance.md`](./Task1_Performance.md#deploying-for-free).

### Task 2 — Benchmark Compression for a Real Customer

Prune coding (LiveCodeBench), long-context (AA-LCR), and (forward-looking) multimodal
(MMMU) benchmarks to the smallest sample set that still gives a useful good-or-not
signal. Your pruner **must live inside [`evalscope`](https://github.com/modelscope/evalscope)**
as an upstream-quality extension. See [`Task2_Model_Quality.md`](./Task2_Model_Quality.md).

Run contract:

```bash
evalscope eval --model <model> --datasets live_code_bench --output ./results_full/
evalscope eval --model <model> --datasets live_code_bench_pruned \
    --dataset-args '{"pruning_strategy": "your_strategy", "prune_ratio": 0.1}' \
    --output ./results_pruned/
python -m evalscope_ext.tools.compare_runs --full ./results_full/ --pruned ./results_pruned/
```

Each task's spec defines exactly what to submit (code, written handouts, and/or video).

---

## How to submit

**Submit via this form:** https://docs.google.com/forms/d/e/1FAIpQLSdwLrRJkKUgTd2sisyJO10VSf1-1vJ3NIywV5HtMlUSc7ijMw/viewform?usp=publish-editor

Your submission **must** include:

1. **A private GitHub repo** with your code.
   - Keep it **private**, and grant access to the reviewers listed in the form.
   - Make it runnable from the instructions above — a reviewer will clone and run it.
   - For Task 2, pin the `evalscope` commit SHA you developed against in your fork's README.

2. **A live URL for the Task 1 UI** — **required**.
   - A publicly reachable link to your deployed frontend where a reviewer can **upload one
     or more perf sweeps, compare them, and get the views** (the shipped sweeps may be
     pre-loaded as a sample).
   - Put it at the top of your README **and paste it into the submission form above**.
   - A free host is expected — see
     [`Task1_Performance.md`](./Task1_Performance.md#deploying-for-free) for options.
   - The repo stays private; only the deployed UI is public (the perf data is synthetic).

3. **Video walkthrough(s)** explaining your work — **required**.
   - Task 1: a ≤5-minute video covering the questions in `Task1_Performance.md`
     (what you cut and why, framework chosen vs ruled out, your assumptions, and your
     read on the model sizes / profile use-cases).
   - Task 2: walk through your pruning approach and the trade-offs in your handouts.
   - Link the video(s) in the form (Loom, Drive, YouTube-unlisted, etc.). Make sure
     reviewers can actually open the link.

A submission without a private repo, a live Task 1 URL, **and** video(s) is incomplete.
