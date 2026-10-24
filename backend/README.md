# Performance API

The API converts Excel performance projections into typed records and analysis results.
It uses FastAPI, Pydantic, and openpyxl.
Pure analysis functions remain separate from HTTP routes.

## Setup and launch

From this directory, run:

```powershell
uv sync --locked
uv run uvicorn perf_api.main:app --reload --host 127.0.0.1 --port 8000
```

Use Python 3.12.
Open [interactive API documentation](http://127.0.0.1:8000/docs) after startup.
The [project usage guide](../USAGE.md) contains a complete upload and decision example.

## HTTP endpoints

| Method and path                      | Request                                             | Response                                                                  |
| ------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------- |
| `GET /health`                        | None                                                | `status` and service identity.                                            |
| `POST /api/v1/workbooks/normalize`   | Multipart field `workbook` with one `.xlsx` file.   | Model, profile, record count, and normalized records.                     |
| `POST /api/v1/comparisons/workbooks` | Repeated multipart field `workbooks`.               | Usable workbooks, models, aligned configurations, and diagnostics.        |
| `POST /api/v1/decisions/evaluate`    | JSON with `workbook`, `targets`, and `assumptions`. | Decision status, representative row, and evidence for all matching rows.  |
| `POST /api/v1/engineering/analyze`   | JSON with a nonempty `workbooks` array.             | Configuration metrics, controlled trends, anomaly flags, and limitations. |

For JSON analysis requests, use the normalization response as the `workbook` value.
For engineering requests, place one or more normalization responses in the `workbooks` array.
The API reference gives the complete generated schemas.

The normalization route returns HTTP 400 for an unsupported filename extension.
It returns HTTP 422 for malformed workbook structure or data.
The comparison route reports individual rejected files in `diagnostics` when valid configurations remain.
It returns HTTP 422 when no usable configuration remains.
Pydantic returns HTTP 422 for invalid JSON request fields.

## Workbook contract

The parser requires a `Summary` worksheet.
Headers occupy row 2, within columns 1 through 19.
Data starts in row 3.
Header text must match these names:

```text
Input Length
Output Length
Cache %
Batch Size
Max number of milliseconds
Target Max number of milliseconds
Prompt only Throughput (t/s)
Gen only Throughput (t/s)
Throughput (t/s)
Throughput / box (t/s/hardware)
Uncached Throughput (t/s)
Uncached Throughput / box (t/s/hardware)
Cached Throughput (t/s)
Cached Throughput / box (t/s/hardware)
TTFT (ms)
Real Prompt Speed (t/s/user)
Prompt Speed with Queueing (t/s/user)
Gen Speed (t/s/user)
RPM
```

Column order can vary within that header range.
The parser maps columns by their names.
It fills missing input length, output length, and cache values from preceding rows.
Other missing values cause errors.
A blank row inside the data table causes an error.
An empty table also causes an error.

openpyxl reads cached formula values with `data_only=True`.
The API does not recalculate formulas.
A formula without a cached numeric result can fail validation.

The filename pattern `Model Z profile 3.xlsx` produces model `Model Z` and profile `3`.
Other names use the filename stem and profile `unknown`.
Cache values use fractions, such as `0.5` for 50%.

## Normalized records

| Group              | Fields                                                                                          | Units                       |
| ------------------ | ----------------------------------------------------------------------------------------------- | --------------------------- |
| Scenario           | `input_length`, `output_length`, `cache_percentage`, `batch_size`                               | Tokens, fraction, count.    |
| Timing             | `max_ms`, `target_max_ms`, `ttft_ms`                                                            | Milliseconds.               |
| Throughput         | `prompt_throughput`, `gen_throughput`, `throughput`, `uncached_throughput`, `cached_throughput` | Tokens/second.              |
| Per-box throughput | `throughput_per_box`, `uncached_throughput_per_box`, `cached_throughput_per_box`                | Tokens/second/hardware box. |
| Per-user speed     | `real_prompt_speed`, `prompt_speed_queued`, `gen_speed`                                         | Tokens/second/user.         |
| Request rate       | `rpm`                                                                                           | Requests/minute.            |

`WorkbookNormalizationResponse` adds `model_name`, `profile_id`, `record_count`, and `records`.
The parser validates numeric conversion.
Engineering diagnostics identify selected questionable values after parsing.
Parser acceptance alone does not establish physical validity.

## Comparison rules

The key combines profile, input length, output length, cache fraction, and batch size.
Cache fractions are rounded to four decimal places for alignment.
Output ordering is deterministic and independent of upload order.

Identical repeated model/profile sweeps appear once with a diagnostic.
Conflicting copies are excluded.
A sweep with duplicate configuration keys is excluded.
A configuration is comparable when at least two models share its key.
`missing_models` identifies incomplete model coverage.

## Decision contract

`targets` can contain these optional fields:

| Field                                             | Meaning                         |
| ------------------------------------------------- | ------------------------------- |
| `input_tokens`, `output_tokens`, `cache_fraction` | Scenario filters.               |
| `min_throughput_tps`                              | Minimum aggregate capacity.     |
| `min_generation_speed_tps_per_user`               | Minimum per-user output speed.  |
| `max_ttft_ms`                                     | Maximum time to first token.    |
| `min_context_window_tokens`                       | Minimum supported context.      |
| `max_cost_usd_per_million_tokens`                 | Maximum hardware cost estimate. |

`assumptions` can contain `context_window_tokens` and `hardware_cost_usd_per_box_hour`.
Both objects are required, but either can be empty.

The engine evaluates complete matching rows.
A GO result needs one row with every applicable check met.
A NO GO result needs a known failure in every matching row.
Otherwise, the result is `insufficient_data`.
Empty requirements and unmatched scenarios also produce `insufficient_data`.
Equality meets a threshold.

The context check covers both the requested minimum and the row's input-plus-output length.
Supplying a supported context assumption also activates the row-fit check.
The engine does not infer supported context from workbook scenario lengths.

Cost requires an explicit box-hour price and positive per-box throughput:

```text
cost = box_hour_price * 1,000,000 / (throughput_per_box * 3,600)
```

The estimate assumes sustained projected capacity and excludes other charges.
It does not represent a customer price.

The first passing row represents GO.
For an incomplete possible pass, the first row without a known failure is shown.
For NO GO, it prefers the row with the fewest failed checks.
Workbook order resolves remaining ties.

## Engineering contract

The response preserves the projection record and supplies source indices.
It includes reported metrics and derived cached/uncached ratios when denominators permit calculation.
Trends hold other configuration dimensions constant.

| Rule                                 | Trigger                                                                                            |
| ------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `ANOMALY_NONPOSITIVE_METRIC`         | Selected throughput, TTFT, or generation-speed metrics are zero or negative.                       |
| `ANOMALY_THROUGHPUT_MISMATCH`        | Cached plus uncached throughput differs from aggregate throughput beyond the configured tolerance. |
| `ANOMALY_THROUGHPUT_DROP_ON_SCALING` | Throughput drops by more than 5% across a controlled batch or cache increase.                      |

The decomposition tolerance uses relative tolerance `0.001` and absolute tolerance `0.01` tokens/second.
Flags do not remove rows.
The source reference currently identifies normalized workbook and record indices.
Filename, worksheet, and sheet-row coordinates can remain absent.

## Runtime and verification

The application reads uploads into memory and has no persistent upload store.
It has no authentication or application-level upload size limit.
Hosted request limits come from the hosting configuration.

From this directory, run:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The [deployment guide](../docs/vercel-deployment.md) explains service routing.
The local API exposes `/docs`, `/redoc`, and `/openapi.json`.
The configured hosted rewrites expose `/api/*` and `/health` through the backend.
