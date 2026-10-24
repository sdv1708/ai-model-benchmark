# Performance Studio frontend

**Live application:** [Performance Studio on Vercel](https://ai-model-quality-challenge-rho.vercel.app/)

This React and TypeScript application displays performance workbook comparisons and their supporting evidence.
Vite serves local development assets and builds the static application.
The browser uses relative `/api/v1/...` URLs.

## Setup

Use Node.js 24.x.
Install the backend first, as described in the [usage guide](../USAGE.md).
From this directory, run:

```powershell
npm ci
npm run dev -- --port 5173 --strictPort
```

The backend must run on port 8000.
Open [the local application](http://127.0.0.1:5173).

## Interface flow

The upload control accepts one or more `.xlsx` workbooks.
The bundled sample follows the same comparison endpoint as uploaded files.
Upload diagnostics remain visible when only part of a batch is valid.

The comparison view groups records by profile, scenario, and batch size.
It displays missing models as coverage gaps.
A single uploaded workbook remains usable without a second model.

The customer view collects scenario requirements and optional context or cost assumptions.
For several models, it applies the same requirements to a specific shared scenario.
The API evaluates all matching batch sizes.
The browser displays GO, NO GO, or NEEDS DATA with the API's evidence.

The engineering view supports detailed row inspection, controlled trends, and anomaly evidence.
An engineering request failure leaves comparison and customer flows available.
Source references identify normalized records.
They do not identify original worksheet coordinates.

## Source map

| File                                            | Responsibility                                                 |
| ----------------------------------------------- | -------------------------------------------------------------- |
| `src/App.tsx`                                   | Application state, upload coordination, and active selections. |
| `src/ComparisonView.tsx`                        | Aligned model configurations.                                  |
| `src/DecisionView.tsx`                          | Requirement form and decision evidence.                        |
| `src/EngineeringView.tsx`                       | Diagnostic metrics, trends, and anomaly sources.               |
| `src/workbooks.ts`, `src/comparisons.ts`        | Workbook and comparison contracts and helpers.                 |
| `src/decisions.ts`, `src/engineering.ts`        | Analysis contracts and helpers.                                |
| `src/TableScroll.tsx`, `src/usePendingFocus.ts` | Table scrolling and pending focus behavior.                    |
| `src/styles.css`                                | Layout and presentation.                                       |
| `tests/`                                        | Browser journeys and synthetic fixture generation.             |

## State and API boundaries

The browser holds the active session in memory.
Reloading the page clears the session.
The API supplies decision rules and engineering calculations.
The browser controls presentation and selection.

Cache values use fractions in request data and percentages in the interface.
Capacity uses tokens/second.
Generation speed uses tokens/second/user.
TTFT uses milliseconds.

## Build and verify

From this directory, run:

```powershell
npm run build
npm run format:check
npx playwright install chromium
npm run test:e2e:built
```

The build runs TypeScript checks and writes `dist/`.
The built browser suite rebuilds the frontend and starts its own services.
It uses API port 8018 and preview port 4174.
The backend virtual environment supplies Python and openpyxl for fixture generation.

Browser tests cover uploads, unseen model names, comparison, decisions, diagnostics, and recovery.
They also cover keyboard navigation, narrow layouts, and automated accessibility scans.
These checks do not establish a complete screen-reader audit.

`npm run test:e2e` uses the development-server configuration.
`npm run test:e2e:services` tests an already running Vercel services environment.

## Proxy and deployment

`VITE_DEV_API_TARGET` changes the development and preview proxy target.
Its default is `http://127.0.0.1:8000`.
The variable configures Vite; the browser still sends relative API requests.

The root `vercel.json` routes the hosted frontend and backend under one domain.
The static browser bundle does not require a service binding or provider secret.
The [deployment guide](../docs/vercel-deployment.md) contains the configured service paths and verification commands.
