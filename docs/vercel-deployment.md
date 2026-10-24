# Deployment guide

The root `vercel.json` defines a Vite frontend and FastAPI backend in one Vercel project.
The services share a public domain.
The repository contains the service configuration; deployment remains a separate operation.

## Service configuration

| Service    | Root        | Configuration                                                             |
| ---------- | ----------- | ------------------------------------------------------------------------- |
| `backend`  | `backend/`  | Framework `fastapi`; entry point `src.perf_api.main:app`.                 |
| `frontend` | `frontend/` | Framework `vite`; install `npm ci`; build `npm run build`; output `dist`. |

Use the repository root as the hosting project's root directory.
The Python package requires Python 3.12.
The frontend development instructions use Node.js 24.x.

## Request routing

| Path                | Destination       |
| ------------------- | ----------------- |
| `/api/*`            | Backend service.  |
| `/health`           | Backend service.  |
| All remaining paths | Frontend service. |

The backend receives the original request path.
Browser requests use relative `/api/v1/...` URLs.
This configuration does not require browser CORS settings or service bindings.
The local API documentation paths are not configured as public backend rewrites.

## Local development

The [usage guide](../USAGE.md#start-performance-studio) starts Vite and Uvicorn separately.
Vite forwards `/api` to `http://127.0.0.1:8000` by default.
`VITE_DEV_API_TARGET` changes that development and preview target.
The hosted service routing comes from `vercel.json`.

An installed and authenticated Vercel CLI can run the configured services from the repository root:

```powershell
vercel dev --local --listen 3000
```

With those services running, execute the browser suite from `frontend/`:

```powershell
npm run test:e2e:services
```

The standalone built browser suite uses its own services and does not require Vercel:

```powershell
npm run test:e2e:built
```

## Hosted verification

1. Open the deployed root URL.
2. Check that `/health` returns HTTP 200 with `status: ok`.
3. Load the bundled sample through the application.
4. Upload a second valid workbook.
5. Inspect the comparison, customer evidence, and engineering evidence.
6. Upload an invalid workbook.
7. Check that the interface displays a useful diagnostic.
8. Check that an unknown `/api` path returns an API error.

A successful build alone does not establish correct service routing.
These checks must use the deployed domain.
No deployment or current availability claim follows from this configuration document.

## Deployment content

`.vercelignore` excludes evaluation artifacts, benchmark code, reference documentation, and generated reports from deployment uploads.
It also excludes local environment files, dependencies, and caches.
The bundled frontend sample remains a public application asset.
The backend code contains no persistent upload store.

Hosting limits and application limits are separate.
The API has no application-level upload size limit.
Memory use and workbook processing behavior need validation for the intended deployment load.

## Configuration references

The configured platform documents [services](https://vercel.com/docs/services) and [service routing](https://vercel.com/docs/services/routing).
The exact service topology for this project is defined in [vercel.json](../vercel.json).
