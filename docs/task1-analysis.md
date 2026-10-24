# Performance design and assumptions

Performance Studio serves two related audiences.
A customer needs a workload decision with explicit requirements.
An engineer needs the configuration evidence behind that decision.
Both views use the same normalized workbook records.

## Design choices

| Choice                        | Reason                                                                   | Consequence                                                 |
| ----------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| React and TypeScript          | Support interactive forms, shared state, and explicit browser contracts. | The frontend requires a build step.                         |
| FastAPI and Pydantic          | Validate JSON boundaries and expose typed schemas.                       | Python remains a separate runtime during local development. |
| openpyxl                      | Read the supplied Excel workbook structure and cached values.            | The application cannot calculate Excel formulas.            |
| Pure analysis functions       | Keep decisions and diagnostics independent of HTTP.                      | Tests can exercise complete rules without browser setup.    |
| Same-domain service routing   | Keep browser API URLs relative.                                          | Hosted requests depend on root routing configuration.       |
| In-memory session             | Support immediate local analysis without account or storage setup.       | Reloading the page clears active state.                     |
| Exact configuration alignment | Compare the same workload shape and batch size.                          | Missing scenarios remain visible as coverage gaps.          |

These choices describe the implemented system.
They do not imply that alternative frameworks underwent a measured comparison.

## Customer decision model

A workload scenario contains input length, output length, and cache fraction.
The customer requirements can add capacity, generation speed, TTFT, context, and cost limits.
The engine evaluates every matching row as one complete configuration.

For example, a batch can provide enough aggregate throughput while exceeding the TTFT limit.
That batch fails the combined requirement.
Another batch can support GO only if its own metrics meet all applicable checks.

No requirement means no decision.
Unknown supported context or hardware cost remains unknown when a relevant check needs it.
Equality meets a specified threshold.

## Engineering evidence

The engineering view preserves reported aggregate, per-box, cached, and uncached throughput.
It shows controlled batch and cache comparisons when matching rows exist.
Derived ratios include their formulas or source descriptions.

Anomaly rules expose questionable values without deleting them.
A source reference identifies a normalized record.
The current parser does not retain original worksheet row coordinates in API responses.

## Assumptions

Workbooks contain projections, not production measurements.
A projected GO does not establish a service-level guarantee.
The app does not interpolate missing workload configurations.

Input length does not prove supported context length.
A supported context window must come from an explicit assumption.
Hardware cost requires an explicit box-hour price.
The resulting estimate assumes sustained projected capacity and excludes other charges.

Cache fractions describe the supplied scenarios.
They do not establish the cache hit rate of a deployed workload.
Aggregate-to-per-box ratios do not identify hardware allocation or model parameter counts.
The [projection analysis](task1-models-and-profiles.md) separates observations from hypotheses.

## Current limits

The application has no authentication, persistent sessions, or database.
It reads uploaded workbooks into memory.
Application-level upload size and processing limits are not implemented.
The host can enforce separate request limits.

Automated tests cover supported workbook structures and known error paths.
Browser checks cover keyboard behavior, constrained layouts, and automated accessibility scans.
A full screen-reader audit and measured production calibration remain separate work.

## Measurement extensions

A production validation would join projections with actual serving measurements by configuration.
Useful measurements include sustained throughput, cache behavior, and latency percentiles.
The comparison should retain measurement dates, hardware, precision, and service versions.
This evidence would show how often projected GO decisions satisfy real workload requirements.
