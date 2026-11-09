# Local development setup

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| [uv](https://docs.astral.sh/uv/) | 0.13+ | Installs Python 3.12 automatically from `backend/.python-version` |
| Node.js | 24 LTS or newer | npm 10+ |
| Docker | 24+ with **buildx** | Only for container builds / `docker compose`. On macOS with Colima: `brew install docker-buildx docker-compose` and follow the post-install note to register them as CLI plugins |
| Google Cloud SDK | latest | Needed from Phase 2 onward (Vertex AI, GCS, Firestore, BigQuery) |
| Terraform | 1.9+ | Phase 11 |

## 1. Configure environment

```bash
cp .env.example .env
```

Every value is optional for Phase 1. Cloud values (`GCP_PROJECT_ID`, `GCS_UPLOAD_BUCKET`, …) are
needed from the phases that use them. The single `.env` at the repo root is read by the backend
(`receipt_shared.config.Settings`) and by Vite (only `VITE_*` variables reach the browser bundle).

## 2. Install dependencies

```bash
make install
```

Equivalent to `cd backend && uv sync` and `cd frontend && npm ci`.

## 3. Run the services (hot reload)

In three terminals:

```bash
make api      # http://localhost:8080/api/v1/health   docs: http://localhost:8080/api/v1/docs
make worker   # http://localhost:8081/health
make web      # http://localhost:5173
```

The Vite dev server proxies `/api/*` to `VITE_API_PROXY_TARGET` (default `http://localhost:8080`),
so the browser uses a single origin in development. The **System status** page shows a live health
check against the API.

## 4. Run the checks

```bash
make check
```

Runs Ruff (lint + format check), mypy (strict), pytest, ESLint, Prettier check, `tsc`, Vitest and
the production frontend build.

## 5. Try the Gemini extraction engine

```bash
make samples                       # synthetic receipts/invoices in evaluation/samples/out
cd backend && uv run receipt-extract --inspect-only ../evaluation/samples/out/*.pdf
```

`--inspect-only` runs the file checks without calling Gemini. Live extraction needs a GCP project
with Vertex AI enabled and Application Default Credentials — see [extraction.md](extraction.md).

## 6. Production-like containers (optional)

```bash
docker compose up --build
```

Builds the same images that are deployed to Cloud Run: frontend on <http://localhost:5173> (nginx),
API on <http://localhost:8080>, worker on <http://localhost:8081>. Requires Docker Compose v2 and
buildx (the Dockerfiles use BuildKit cache mounts).

## Repository layout

```
backend/            uv workspace (Python 3.12)
  shared/           receipt_shared: settings, JSON logging, HTTP middleware, domain models
  api/              receipt_api: public FastAPI service (Cloud Run)
  worker/           receipt_worker: Eventarc-triggered processing service (Cloud Run)
frontend/           React + TypeScript + Vite + Tailwind CSS
evaluation/         Extraction benchmark (Phase 10)
terraform/          Infrastructure as code (Phase 11)
sql/                BigQuery DDL and analytics queries (Phase 6)
docs/               Project documentation
.github/workflows/  CI/CD (Phase 12)
```
