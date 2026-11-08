# Implementation Plan

AI-Powered Receipt & Invoice Extractor — phased build plan and status tracker.

Each phase ends with: what was implemented, files changed, commands run, tests and
their **actual** results, known issues, required configuration, and the next phase.
A phase is only marked done after its deliverable has been verified.

## Status

| # | Phase | Status |
|---|-------|--------|
| 1 | Project initialization | Done — see Phase log |
| 2 | Gemini extraction engine | Not started |
| 3 | Validation engine | Not started |
| 4 | Cloud Storage integration | Not started |
| 5 | Eventarc + Cloud Run processing | Not started |
| 6 | BigQuery data warehouse | Not started |
| 7 | FastAPI backend | Not started |
| 8 | React frontend | Not started |
| 9 | Manual review workflow | Not started |
| 10 | Extraction evaluation framework | Not started |
| 11 | Terraform infrastructure | Not started |
| 12 | GitHub Actions CI/CD | Not started |
| 13 | Security | Not started |
| 14 | Monitoring and observability | Not started |
| 15 | Testing (integration + E2E) | Not started |
| 16 | Documentation | Not started |

## Architecture decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Python packaging | One **uv workspace** in `backend/` with three members: `receipt-shared`, `receipt-api`, `receipt-worker` | One lockfile, shared code installed as a real package, each service ships only its own deps |
| Python version | 3.12 (pinned in `backend/.python-version`, `python:3.12-slim` images) | Meets the 3.12+ requirement; local and container match |
| Lint/format | Ruff (lint + format), mypy (strict on shared code) | Fast, single tool for most checks |
| Python tests | pytest + httpx `TestClient` | Standard for FastAPI |
| Config | `pydantic-settings` reading environment variables; one `Settings` class in `receipt_shared.config` | No hardcoded project IDs or secrets |
| Logging | JSON lines on stdout with a Cloud Logging-compatible `severity` field | Cloud Run ships stdout to Cloud Logging; structured fields become queryable |
| Frontend | React + TypeScript + Vite + Tailwind CSS v4, React Router, TanStack Query, Vitest + Testing Library, ESLint + Prettier | Required stack, plus standard data-fetching and test tooling |
| Frontend hosting | Static build served by nginx in a third Cloud Run service | Keeps all hosting in Cloud Run/Terraform; same CI path as the backend |
| Auth | Firebase Authentication (email/password) on the frontend; backend verifies ID tokens with `firebase-admin` | Required by the spec; local dev uses the Firebase Auth emulator |
| Operational state | Firestore (Native mode), document `documents/{document_id}`, sub-collections for processing history and corrections | Required by the spec; strong per-document consistency for idempotency |
| Analytics store | BigQuery `receipt_analytics`; writes go to a staging table and are `MERGE`d on `document_id` | Idempotent loads even when events repeat |
| Upload path | API issues a V4 signed `PUT` URL → browser uploads directly to GCS → `object.finalized` direct event → Eventarc → worker | Large files never pass through the API |
| Idempotency key | `document_id` + GCS object `generation`, claimed in a Firestore transaction | Eventarc delivery is at-least-once |
| AI | Google Gen AI SDK (`google-genai`) with `vertexai=True`, `response_schema` for structured output; model and location from env | Required; configurable model |

## Phase breakdown

### Phase 1 — Project initialization
- Repository layout: `frontend/`, `backend/{api,worker,shared}/`, `evaluation/`, `terraform/`, `sql/`, `docs/`, `.github/workflows/`.
- Root: `README.md`, `.gitignore`, `.env.example`, `docker-compose.yml`, this file.
- Backend: uv workspace, shared `Settings`, JSON logging, core domain enums/models, FastAPI apps for API and worker with `/api/v1/health` and `/health`, Ruff/mypy/pytest config, Dockerfiles.
- Frontend: Vite + React + TS + Tailwind, app shell (sidebar layout), API client with a live health check, ESLint/Prettier/Vitest, Dockerfile (nginx).
- Verify: lint, typecheck, tests, both backends start and answer health checks, frontend dev server serves and reaches the API through the dev proxy, production build succeeds.

### Phase 2 — Gemini extraction engine (`receipt_shared.extraction`)
- Pydantic extraction schema (all fields from the spec, nullable, `Decimal` money, `date` dates).
- Prompt with explicit anti-hallucination and prompt-injection rules; document content passed as data parts, never concatenated into instructions.
- File inspection: MIME sniffing by magic bytes, size limit, PDF page-count limit (`pypdf`).
- `GeminiExtractor` with timeout, retries with exponential backoff and jitter on 429/5xx, structured logs (latency, model, token usage — no document contents).
- CLI: `uv run extract path/to/receipt.pdf` for local testing against Vertex AI.
- Unit tests with a mocked client; an opt-in live test marked `integration`.

### Phase 3 — Validation engine (`receipt_shared.validation`)
- Rule-based validator returning `ValidationResult` (`is_valid`, `validation_status`, errors, warnings, `failed_fields`, `duplicate_status`).
- Required fields, date sanity, non-negative totals, ISO 4217 currency allow-list, document type, subtotal + tax − discount ≈ total, line-item sum ≈ subtotal/total, configurable tolerances.
- Duplicate detection: exact file hash = duplicate; same merchant + number + date + total = *possible* duplicate → review, never auto-discard.
- A unit test per rule.

### Phase 4 — Cloud Storage integration
- API endpoint for signed upload URLs (content type and declared size bound into the signature; `x-goog-content-length-range`).
- Path `uploads/{user_id}/{document_id}/{filename}`, plus `processed/` and `evaluation/` prefixes.
- Worker re-checks magic bytes and size after upload; records SHA-256.
- Local dev: real dev bucket (signed URLs need real GCS), or the GCS emulator for tests.

### Phase 5 — Eventarc + worker
- CloudEvents receiver (binary and structured modes) for `google.cloud.storage.object.v1.finalized`.
- Firestore transaction claims `(document_id, generation)`; replays are acknowledged with 2xx and skipped.
- State machine: UPLOADED → PROCESSING → EXTRACTED → VALIDATING → VALID / REVIEW_REQUIRED / FAILED; APPROVED / REJECTED from review.
- Transient errors → 5xx (Eventarc retries); permanent errors → FAILED + 2xx (no retry storm).

### Phase 6 — BigQuery
- Dataset `receipt_analytics`, tables `documents`, `extracted_transactions`, `line_items`, `review_records`, `extraction_metrics` (DDL in `sql/schema/`, also in Terraform).
- Staging + `MERGE` on `document_id`; line items replaced per document inside the same script.
- Analytics queries in `sql/queries/`.

### Phase 7 — FastAPI backend
- All endpoints from the spec, Firebase token verification dependency, per-user authorization on every document lookup, cursor pagination, rate limiting, consistent error model, OpenAPI docs.

### Phase 8 — React frontend
- Login/registration, overview, upload (drag and drop, progress, live status), documents list, details (signed read URL preview), review queue + editor, analytics (charts), settings.

### Phase 9 — Manual review
- Corrections stored separately from original extraction; field-level audit trail; revalidation before approval; approval writes to BigQuery; rejection with reason.

### Phase 10 — Evaluation
- Synthetic document generator (PDF + PNG, varied layouts, receipts and invoices) with ground-truth JSON; ~150 documents.
- `evaluation/run.py` computing field-, document-, money- and line-item-level accuracy, by document type, with latency and review rate; JSON + Markdown reports stamped with model version and date.

### Phase 11 — Terraform
- Modules: storage, cloud_run, eventarc, bigquery, firestore, artifact_registry, iam, monitoring, service_accounts, project_services.
- `environments/dev` and `environments/prod`, GCS remote state (native locking), labels, least-privilege IAM, WIF for GitHub.

### Phase 12 — GitHub Actions
- `ci.yml` (tests, lint, format, `pip-audit`/`npm audit`, `terraform fmt`/`validate`, Docker builds), `deploy-dev.yml` (on main, WIF, push to Artifact Registry, deploy, smoke test), `deploy-prod.yml` (protected environment, versioned images, Terraform apply, health check).

### Phases 13–16
- Security hardening and documentation of assumptions, monitoring dashboards and alerts (log-based metrics), integration and E2E tests against dev, final documentation.

## Operating rules
- No credentials, project IDs or secrets in the repository.
- Billable cloud operations (Terraform apply, deployments, live Gemini runs) are run only after explicit approval.
- `terraform destroy` is never run without explicit approval.
- Test results and deployment status are reported only as observed.

## Phase log

### Phase 1 — Project initialization (2026-11-08)

**Implemented**
- Repository layout, root config (`.gitignore`, `.editorconfig`, `.env.example`, `Makefile`, `docker-compose.yml`).
- Backend uv workspace (Python 3.12): `receipt-shared` (env-driven `Settings`, Cloud Logging-compatible
  JSON logging, request-ID/access-log middleware, document status state machine and enums),
  `receipt-api` (FastAPI app factory, CORS, consistent error model, `/api/v1/health`, OpenAPI at
  `/api/v1/docs`), `receipt-worker` (FastAPI app, `/health`; docs disabled outside `local`).
- Multi-stage Dockerfiles (uv, non-root user, `PORT`-aware) for API and worker.
- Frontend: Vite + React 19 + TypeScript (strict) + Tailwind v4, React Router, TanStack Query,
  sidebar layout (responsive drawer on mobile), reusable UI components, typed API client with error
  mapping, System status page backed by the live API, 404 page. ESLint, Prettier, Vitest.
- Frontend Dockerfile (static build on unprivileged nginx, SPA fallback, security headers, asset caching).

**Verification (actual results)**
- Backend: `ruff check` clean, `ruff format --check` clean, `mypy --strict` clean (13 files), `pytest` 18 passed.
- Frontend: ESLint clean, Prettier clean, `tsc` clean, Vitest 7 passed, `vite build` succeeded.
- `npm audit`: 0 vulnerabilities (after overriding `minimatch` to ^11.0.5 for a dev-only ReDoS advisory in the ESLint toolchain).
- Runtime: API (`:8080`) and worker (`:8081`) started with `uv run`; Vite (`:5173`) served the app and
  proxied `/api/v1/health` to the API; the System status page rendered "Healthy" in a browser.
- Containers: all three images built and ran (non-root, `PORT` honored, nginx headers present).

**Known issues / compromises**
- Docker buildx and Compose are not installed on the dev machine, so images were built with the
  legacy builder from copies of the Dockerfiles without the BuildKit `--mount=type=cache` flags, and
  `docker compose up` itself was not run. CI (Phase 12) builds with BuildKit.
- Sidebar lists only implemented pages; remaining pages arrive in Phase 8.

**Next:** Phase 2 — Gemini extraction engine.
