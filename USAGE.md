# Usage guide

This guide covers local installation, workbook analysis, API use, and offline benchmark experiments.
Run each command from its stated directory.
The shell examples use PowerShell.

## Use the live application

1. Open [Performance Studio on Vercel](https://ai-model-quality-challenge-rho.vercel.app/).
2. Select **Load sample workbook**, or upload one or more `.xlsx` workbooks.
3. Inspect the comparison, customer decisions, and engineering evidence.

The live application requires no local installation.
The workbook procedures below apply to both the live and local application.
Benchmark analysis requires the local setup described below.

## Requirements

| Tool    | Version or purpose                                             |
| ------- | -------------------------------------------------------------- |
| Git     | Clone the repository.                                          |
| Git LFS | Download the full evaluation JSONL files.                      |
| Python  | Use version 3.12. Both Python packages require `>=3.12,<3.13`. |
| uv      | Install Python dependencies from the package lockfiles.        |
| Node.js | Use version 24.x with npm for the frontend.                    |

Dependency installation requires package downloads unless the required packages are cached.
Task 1 needs no environment file or API key.
The benchmark commands analyze local artifacts and need no provider key.

## Install the project

1. Clone the repository.

   ```powershell
   git clone https://github.com/sdv1708/ai-model-quality-challenge.git
   cd ai-model-quality-challenge
   ```

2. Install the backend dependencies.

   ```powershell
   cd backend
   uv sync --locked
   cd ..
   ```

3. Install the frontend dependencies.

   ```powershell
   cd frontend
   npm ci
   cd ..
   ```

4. For benchmark analysis, download the evaluation data.

   ```powershell
   git lfs install
   git lfs pull
   ```

5. For benchmark analysis, install the analysis package.

   ```powershell
   cd task2
   uv sync --locked
   cd ..
   ```

Git LFS stores data separately from ordinary Git objects.
A JSONL file that starts with `version https://git-lfs.github.com/spec/v1` is a pointer.
The analysis package rejects these pointers.
The bundled workbook and `perf_data.zip` do not require Git LFS.

## Start Performance Studio

1. From the repository root, start the API in terminal 1.

   ```powershell
   cd backend
   uv run uvicorn perf_api.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. From the repository root, start Vite in terminal 2.

   ```powershell
   cd frontend
   npm run dev -- --port 5173 --strictPort
   ```

3. Open [the local application](http://127.0.0.1:5173).
4. Select **Load sample workbook**.
5. Inspect the customer and engineering sections.

The [health endpoint](http://127.0.0.1:8000/health) returns `status: ok` when the API starts.
The [API reference](http://127.0.0.1:8000/docs) displays request and response schemas.
Vite forwards `/api` requests to port 8000.

To stop a server, press Ctrl+C in its terminal.

## Compare two supplied models

1. From the repository root, extract the workbook archive.

   ```powershell
   Expand-Archive -LiteralPath perf_data.zip -DestinationPath perf_data
   ```

   On macOS or Linux, use `unzip perf_data.zip -d perf_data`.

2. Upload these two files together:

   ```text
   perf_data/Model_A_profile_1/Model A profile 1.xlsx
   perf_data/Model_C_profile_1/Model C profile 1.xlsx
   ```

3. Select profile `1`.
4. Select the scenario with 10,000 input tokens, 333 output tokens, and 50% cache.
5. Enter these customer requirements:

   | Requirement              |  Value | Unit               |
   | ------------------------ | -----: | ------------------ |
   | Minimum capacity         | 400000 | tokens/second      |
   | Minimum generation speed |   1200 | tokens/second/user |
   | Maximum TTFT             |     10 | milliseconds       |

6. Leave context and cost requirements empty.
7. Inspect the decision evidence for each model.

Model A has a GO configuration at batch size 20.
Model C returns NO GO for these requirements.
The result uses the supplied projections and this exact scenario.

The customer evaluation searches all matching batch sizes.
The engineering batch selector controls inspection only.
A different inspection row does not change the customer requirements.

## Interpret the results

**GO** means at least one complete projected configuration meets every applicable check.
The evidence shows the values and assumptions used.
A GO result still needs validation against measured serving performance.

**NO GO** means every matching configuration has a known failure.
Changing a requirement can change this result.

**NEEDS DATA** means a possible decision depends on missing information.
An absent scenario or empty requirements can also cause this result.
The evidence identifies the missing facts.

For a context check, supply both the required minimum and the supported context window.
For a cost check, supply both the cost ceiling and the hardware box-hour price.
Empty requirement fields are not evaluated.

The hardware cost estimate assumes sustained projected capacity.
It is not an endpoint price or a customer quote.

## Inspect engineering evidence

1. Select a model and profile.
2. Select a scenario and batch size.
3. Inspect aggregate and per-box throughput.
4. Compare cached and uncached components.
5. Inspect controlled batch and cache trends.
6. Read each anomaly rule and its source references.

A source row number identifies a normalized record.
It does not identify an Excel worksheet row.
Missing trend pairs remain unavailable.
An anomaly flag preserves the underlying projection values.

## Use your own workbook

Use an `.xlsx` file with a worksheet named `Summary`.
Put the 19 required headers in row 2, within the first 19 columns.
Start data in row 3.
The [backend reference](backend/README.md#workbook-contract) lists all required headers.

Use a filename such as `Model Z profile 3.xlsx` to supply model and profile identity.
Use numeric values for projection metrics.
Store cache values as fractions: `0.5` means 50%.

The parser fills omitted input length, output length, and cache values from preceding rows.
This supports merged scenario cells.
Other missing values cause validation errors.
Cached formula results must exist because the parser does not calculate Excel formulas.

Avoid conflicting copies of the same model/profile sweep.
The comparison route excludes ambiguous sweeps and reports the reason.

## Call the API

Start the API before these commands.
Run the examples from the repository root.
Use `curl.exe` on Windows to select the curl executable.
On macOS or Linux, use `curl`.

Normalize the bundled workbook:

```powershell
curl.exe --fail-with-body -F "workbook=@frontend/public/sample/Model A profile 1.xlsx" http://127.0.0.1:8000/api/v1/workbooks/normalize -o normalized.json
```

Create a decision request:

```powershell
$request = @{
    workbook = Get-Content -LiteralPath normalized.json -Raw | ConvertFrom-Json
    targets = @{
        input_tokens = 10000
        output_tokens = 333
        cache_fraction = 0.5
        min_throughput_tps = 400000
        min_generation_speed_tps_per_user = 1200
        max_ttft_ms = 10
    }
    assumptions = @{}
} | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/decisions/evaluate -Method Post -ContentType application/json -Body $request
```

The result contains `status`, `selected_record`, `evidence`, and `evaluated_configurations`.
The [backend reference](backend/README.md#http-endpoints) describes comparison and engineering requests.

## Reproduce full benchmark scores

From `task2/`, run:

```powershell
uv run benchmark-reference --data-root ../Evals --output-dir output/reference
```

A successful run validates 28 file pairs and 1,905 joined results.
It writes six full scores.

| Output             | Content                                                         |
| ------------------ | --------------------------------------------------------------- |
| `samples.jsonl`    | Normalized samples with prediction and review source locations. |
| `full_scores.json` | Three coding scores and three long-context scores.              |
| `manifest.json`    | Source hashes, counts, policy, and report hashes.               |

MMMU rows receive validation but do not enter the six Part A summaries.
The loader expects the supplied fixed inventory.
An arbitrary benchmark export requires a separate loader adaptation.

## Run subset experiments

From `task2/`, run the coding study:

```powershell
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-pruning
uv run python tools/audit_lcb.py --data-root ../Evals --reports output/lcb-pruning
```

Run the long-context study:

```powershell
uv run aa-lcr-pruning --data-root ../Evals --output-dir output/aa-lcr-pruning
uv run python tools/audit_aa_lcr.py --data-root ../Evals --reports output/aa-lcr-pruning
```

Each default study evaluates five retained fractions with twenty seeds.
It includes 1,500 score evaluations and 1,500 pair-transfer evaluations.
These are saved-grade calculations, not model inference calls.

For a smaller exploratory coding study, run:

```powershell
uv run lcb-pruning --data-root ../Evals --output-dir output/lcb-small --keep-ratios 0.5 1.0 --seeds 0 1
```

To add illustrative thresholds, use `--thresholds 0.6 0.7 0.8`.
Thresholds use a scale from 0 to 1.
They represent explicit analysis settings, not established customer requirements.

Use separate output directories for separate configurations.
Keep input files unchanged during a run.
Use one writer per output directory.

## Compare operating points

From `task2/`, reproduce the recorded threshold settings:

```powershell
uv run part-a-operating-points --data-root ../Evals --output-dir output/operating-points --lcb-thresholds 0.7 --aa-lcr-thresholds 0.6
uv run python tools/audit_operating_points.py --reports output/operating-points
```

The command writes `operating_points.json`, `curves.csv`, `manifest.json`, and benchmark report subdirectories.
The recorded policy selects full retention for both benchmarks.
A smaller sample count alone does not establish a useful operating point.

The [benchmark reference](task2/README.md#operating-point-policy) explains the gates and their limits.

## Run the image-pair demonstration

From `task2/`, choose an unused output directory:

```powershell
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
```

The demonstration creates synthetic inputs, transformed pairs, a request plan, scripted responses, and diagnostic reports.
It does not contact an endpoint.
The output profile deliberately uses `example.invalid`.

Inspect the generated `report-SYNTHETIC.json` and `bundle/manifest.json`.
Use a new destination for another run; the demonstration refuses an existing directory.

The [image harness reference](task2/MMMU_HARNESS.md) explains custom inputs and saved response analysis.

## Verification

From `backend/`, run:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

From `task2/`, run:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

From `frontend/`, run:

```powershell
npm run build
npm run format:check
npx playwright install chromium
npm run test:e2e:built
```

The built browser suite starts its own API on port 8018 and preview server on port 4174.
Keep those ports free.
The suite rebuilds the frontend before browser tests.
Browser installation requires a download unless Chromium is already cached.

## Fault recovery

| Symptom                            | Action                                                                                          |
| ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| Python version error               | Install Python 3.12. Repeat `uv sync --locked` in the affected package.                         |
| JSONL pointer error                | Run `git lfs pull` from the repository root.                                                    |
| Upload request fails               | Check the API health endpoint. Confirm that the API uses port 8000.                             |
| Missing `Summary` sheet or columns | Compare the workbook with the bundled sample and the backend contract.                          |
| Numeric validation error           | Supply numeric cells and cached formula results.                                                |
| Model or profile appears unknown   | Use the filename pattern `Model Z profile 3.xlsx`.                                              |
| Mixed upload warning               | Read each file diagnostic. Correct rejected files and upload them again.                        |
| No matching configuration          | Select a scenario present in the uploaded workbook.                                             |
| Cost or context remains unknown    | Supply the relevant assumption and requirement.                                                 |
| Existing image output error        | Choose a new destination directory.                                                             |
| Port already in use                | Stop the conflicting process or configure a matching API proxy target.                          |
| EvalScope adapter is unavailable   | Use the local reference commands. Native adapter source requires the separate private checkout. |

`VITE_DEV_API_TARGET` changes the Vite development and preview proxy target.
For example, set it to `http://127.0.0.1:8001` when the API uses port 8001.
The [deployment guide](docs/vercel-deployment.md) covers hosted routing.
