# Projection analysis: models and workload profiles

This analysis uses 77 supplied workbooks and 275 projection rows.
The archive contains 11 anonymous models and seven traffic profiles.
Each model has 25 matching scenario/batch configurations.
Profile 2 contributes one batch; the other profiles contribute four each.

The [normalized CSV](data/task1-projections.csv) preserves workbook paths and worksheet row numbers.
The [summary JSON](data/task1-summary.json) records the archive hash, comparisons, and engineering flags.
From `backend/`, reproduce these files with:

```powershell
uv run python ../docs/scripts/summarize_task1.py
```

The script reads `perf_data.zip` without extracting or changing its inputs.
It uses the application parser and verifies matching model coverage.
Interpretation remains separate from generated metrics.

## Observed performance and conditional size estimates

Per-box throughput permits a closer comparison than aggregate capacity.
Different aggregate-to-per-box ratios can otherwise obscure resource differences.
The burden proxy compares every model with Model A across 25 matched configurations:

```text
relative_burden = median(Model A throughput_per_box / model throughput_per_box)
```

The table's throughput and generation speed use profile 1, batch 10, and the 10,000-input/333-output/50%-cache scenario.
Rank ranges and burden ratios use all matched configurations.
Rank 1 means the highest per-box throughput.

The size columns use an illustrative dense-model assumption.
They assume comparable hardware, precision, utilization, and inverse size-to-throughput scaling.
The first estimate assumes Model A has 70 billion parameters.
The sensitivity column changes that anchor from 30 billion to 100 billion.
Neither anchor comes from the supplied model identities.

| Model | Per-box throughput (t/s) | Generation (t/s/user) | Per-box rank range | Burden vs A | Conditional size if A=70B | Sensitivity if A=30–100B |
| ----- | -----------------------: | --------------------: | ------------------ | ----------: | ------------------------: | ------------------------ |
| A     |                   37,374 |                 1,354 | 4–9                |       1.000 |                       70B | 30–100B                  |
| B     |                    9,325 |                   865 | 8–9                |       4.189 |                      293B | 126–419B                 |
| C     |                    3,210 |                   451 | 11–11              |      11.352 |                      795B | 341–1,135B               |
| D     |                    4,821 |                   890 | 10–10              |       7.884 |                      552B | 237–788B                 |
| E     |                   46,107 |                 1,395 | 2–7                |       0.652 |                       46B | 20–65B                   |
| F     |                   23,950 |                 1,207 | 5–8                |       1.408 |                       99B | 42–141B                  |
| G     |                   69,008 |                 1,737 | 2–3                |       0.484 |                       34B | 15–48B                   |
| H     |                   34,337 |                 1,313 | 3–5                |       0.974 |                       68B | 29–97B                   |
| I     |                   90,066 |                 1,512 | 1–1                |       0.351 |                       25B | 11–35B                   |
| J     |                   19,328 |                 1,217 | 6–8                |       1.648 |                      115B | 49–165B                  |
| K     |                   30,823 |                 1,419 | 4–6                |       1.095 |                       77B | 33–110B                  |

These conditional sizes are hypotheses, not identified parameter counts.
The sensitivity ranges are not confidence intervals.
Hardware allocation, quantization, mixture-of-experts routing, and bottlenecks can invalidate the assumed mapping.
The application does not use these estimates for customer decisions.

Model I has the highest per-box throughput in every matched configuration.
Model G also ranks near the top.
Models C and D have lower per-box throughput throughout the supplied comparisons.
These observations describe serving burden under the recorded projections.
They cannot identify an architecture or a real model name.

Generation speed and throughput rankings can differ.
For example, Model G has higher per-user generation speed than Model I in the displayed scenario.
A capacity ranking alone therefore cannot answer an interactive latency question.

## Traffic profiles

The following use cases interpret workload shapes.
They are examples, not identified customer workloads.

| Profile | Input tokens | Output tokens | Cache | Example use                                       | Important checks                                           |
| ------- | -----------: | ------------: | ----: | ------------------------------------------------- | ---------------------------------------------------------- |
| 1       |       10,000 |           333 |   50% | Document question answering with shared context.  | TTFT, capacity, and context support.                       |
| 2       |       10,000 |         4,000 |    0% | A long report from a new specification.           | Generation speed and complete-response duration.           |
| 3       |        3,200 |           400 |   50% | Customer support with reused instructions.        | Interactive TTFT, output speed, and capacity.              |
| 4       |        1,000 |         1,000 |   50% | Drafting, translation, or code completion.        | Generation speed and batch saturation.                     |
| 5       |        8,000 |         1,000 |   50% | Multi-document synthesis.                         | Prompt processing, generation speed, and per-box capacity. |
| 6       |       60,000 |           200 |   90% | Repeated extraction from a large shared document. | Actual cache reuse and supported context.                  |
| 7       |       17,000 |         3,500 |   70% | Detailed analysis or repeated agent requests.     | Cache assumptions, generation duration, and capacity.      |

Profile 6 illustrates why aggregate token throughput needs careful interpretation.
A high reused-token share does not represent the same new work as a fresh prompt.
Its projected input length also does not prove supported context length.

Profile 2 contains only one batch size per model.
It cannot establish a batch-scaling trend.
The engineering view shows unavailable comparisons when matching pairs do not exist.

## Practical example

The [usage guide](../USAGE.md#compare-two-supplied-models) compares Models A and C under profile 1.
At the stated requirements, Model A has a GO configuration and Model C returns NO GO.
That conclusion combines capacity, per-user generation speed, and TTFT on complete rows.
It does not depend on a model-size hypothesis.

## Interpretation limits

The workbooks contain projections.
They do not supply production measurements, complete hardware identity, or verified model parameter counts.
Cache behavior, service overhead, and real workload variation require separate measurements.

The [performance design](task1-analysis.md) explains the decision rules and engineering boundaries.
The [backend reference](../backend/README.md) defines the exact workbook and API contracts.
