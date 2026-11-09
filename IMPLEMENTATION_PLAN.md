# Implementation Plan

AI-Powered Receipt & Invoice Extractor — phased build plan and status tracker.

Each phase ends with: what was implemented, files changed, commands run, tests and
their **actual** results, known issues, required configuration, and the next phase.
A phase is only marked done after its deliverable has been verified.

## Status

| # | Phase | Status |
|---|-------|--------|
| 1 | Project initialization | Done — see Phase log |
| 2 | Gemini extraction engine | Done — verified live on Vertex AI (see Phase log) |
| 3 | Validation engine | Done — see Phase log |
| 4 | Cloud Storage integration | Done — verified live (see Phase log) |
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
- CLI: `uv run receipt-extract path/to/receipt.pdf` for local testing against Vertex AI.
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

### Phase 2 — Gemini extraction engine (2026-11-08)

**Implemented** (details: [docs/extraction.md](docs/extraction.md))
- `receipt_shared.models.extraction`: Gemini-independent domain models (`ExtractedDocument`,
  `LineItem`, `ExtractionMetadata`, `ExtractionResult`, expense-category and payment-method enums).
- `receipt_shared.extraction` (installed via the `[extraction]` extra; the worker depends on it, the API does not):
  - `documents.py`: magic-byte type detection, size / page / pixel limits, extension and declared
    content-type mismatch rejection, encrypted/corrupt PDF and image detection, SHA-256.
  - `prompt.py`: versioned system instruction covering accuracy and prompt-injection rules.
  - `schema.py`: `GeminiExtraction` response schema plus `to_domain()` (exact `Decimal` money,
    ISO dates, invalid values → null with warnings, `missing_fields` derived from nulls, output caps).
  - `gemini.py`: Vertex AI client via `google-genai` 3.0 with per-attempt timeout, retries with
    exponential backoff, full jitter and `Retry-After`, error classification, structured logs and
    model/version/token metadata.
  - `cli.py`: `receipt-extract` (`--inspect-only`, `--model`, `--location`).
- `evaluation/samples/generate_samples.py`: synthetic receipts and invoices (PNG, JPEG, single- and
  two-page PDF, prompt-injection case) with ground-truth JSON.
- Settings: retry delays, output-token cap, optional thinking budget, image pixel limit.
  `MAX_UPLOAD_BYTES` default lowered to 15 MiB to stay under Vertex AI's ~20 MB inline request limit.

**Verification (actual results)**
- `make check` exits 0: ruff and format clean, mypy strict clean (21 files), pytest 71 passed
  (6 live integration tests deselected by default), frontend unchanged and passing.
- Confirmed the SDK converts `GeminiExtraction` into a Vertex schema (nullable enums and numbers).
- `receipt-extract --inspect-only` accepted all 7 generated samples (the invoice is correctly
  detected as 2 pages); without `GCP_PROJECT_ID` the CLI exits 1 with a `configuration_error`.
- Worker image built and imports the engine; the API image does not contain `google-genai`.

**Live verification (2026-11-09)**
- GCP project `receipt-extractor-lkmljr` created, with billing linked and Vertex AI enabled.
- `gemini-2.5-flash` returned 404 (no longer available to new projects). The available models
  were listed and probed: Gemini 3.x models return 404 in `us-central1` but work in the `global`
  location. Defaults changed to `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_LOCATION=global`.
- `make test-gemini-live`: **6 passed** against `gemini-3.8-flash`. Covered: the café receipt as
  PNG, JPEG and PDF; the discount receipt; the 2-page EUR invoice (all 7 line items across pages,
  exact subtotal/tax/total); and the prompt-injection receipt (real merchant and total extracted,
  instruction not echoed).
- Observed latency 5–10 s per document, about 3–4k tokens.
- API errors now include Google's reason, e.g. `[BILLING_DISABLED] …`.

**Known issues**
- On the invoice, `payment_method` was set to `bank_transfer` from the payment *terms* line;
  ground truth is null. To be measured in Phase 10 and possibly tightened in the prompt.
- Extracted decimals keep the model's float form (`5809.0`, `1.0`); numerically exact, and
  normalised for display/storage in later phases.

**Cost guardrail** (`ops/budget-kill-switch/`)
- $10 USD/month budget on the project (credits excluded, alerts at 50/90/100%). It publishes to
  Pub/Sub, where a Cloud Run function detaches billing when cost ≥ budget. Least-privilege service
  account, internal-only ingress. Verified in dry-run mode ($12 → "would disable") and armed
  ($3 → "no action"). See the README there for recovery steps.

**Next:** Phase 3 — validation engine.

### Phase 3 — Validation engine (2026-11-09)

**Implemented** (details: [docs/validation.md](docs/validation.md))
- `receipt_shared.models.validation`: `ValidationResult` (`is_valid`, `validation_status`,
  `validation_errors`, `validation_warnings`, `failed_fields`, `duplicate_status`, `duplicate_of`,
  `rules_version`), `ValidationIssue` (stable code, severity, message, fields),
  `DocumentFingerprint`, and `ValidationResult.processing_failed()`.
- `receipt_shared.validation`:
  - `rules.py`: required and optional fields, document type, currency, dates, amounts, totals
    reconciliation (standard, tax-inclusive, discount-in-subtotal), line-item arithmetic and sums,
    invoice number.
  - `duplicates.py`: exact file hash → DUPLICATE; merchant + number, or merchant + date + total +
    currency → POSSIBLE_DUPLICATE (review). Per-user, earlier documents only, rejected/failed
    ignored, normalised keys.
  - `engine.py`: `DocumentValidator` runs the rules, carries over extraction warnings, applies
    duplicate checks (with reviewer acknowledgement), and decides VALID / REVIEW_REQUIRED /
    DUPLICATE.
  - `config.py`: `ValidationConfig` from settings; tolerance never below the currency's minor unit.
- New settings: `LINE_ITEM_TOLERANCE`, `FUTURE_DATE_TOLERANCE_DAYS`, `MAX_DOCUMENT_AGE_DAYS`,
  `MAX_REASONABLE_AMOUNT`.

**Verification (actual results)**
- 105 validation unit tests, covering every rule, tolerance edges, JPY/KWD minor units, each
  duplicate scenario (including simultaneous uploads and other users' files), and JSON round-trips.
- `make check` exits 0 (backend 177 passed, kill switch 7 passed, frontend unchanged).
- Ran the validator on the synthetic samples' ground truth: all 4 documents VALID. A re-photographed
  café receipt (different file, same receipt) was flagged POSSIBLE_DUPLICATE and sent to review.

**Design decisions**
- Line-item mismatches are warnings, not errors, so line-item noise doesn't flood the review queue
  (document totals are already checked as errors).
- Possible duplicates go to review rather than being rejected, as the spec requires.

**Not yet done (by design, later phases)**
- Persisting results to Firestore and the Firestore-backed `DuplicateIndex` (Phase 5).
- Revalidation of reviewer corrections (Phase 9) reuses `DocumentValidator` with
  `duplicate_acknowledged`.

**Next:** Phase 4 — Cloud Storage integration.

### Phase 4 — Cloud Storage integration (2026-11-09)

**Implemented** (details: [docs/storage.md](docs/storage.md))
- GCP (via `ops/gcp/bootstrap-storage.sh`, idempotent): private bucket
  `receipt-extractor-lkmljr-documents` (us-central1, public access prevention enforced, uniform
  access, versioning, lifecycle, CORS, labels); Firestore `(default)` Native database in
  us-central1; `receipt-api` service account with bucket-scoped object create/view,
  `datastore.user`, and Token Creator on itself; the developer has Token Creator for local signing.
- `receipt_shared.files`: supported types and MIME normalisation (shared by the API and extraction).
- `receipt_shared.storage`: object paths and filename sanitisation, `DocumentStorage` (V4 signed
  PUT/GET via IAM signBlob, size-capped CRC32C-checked reads), and `storage.verify.verify_upload`
  (size, magic bytes, integrity, limits, optional SHA-256).
- `receipt_shared.repository`: `DocumentRecord` plus Firestore and in-memory repositories.
- New `AWAITING_UPLOAD` status (→ UPLOADED / FAILED).
- API: Firebase ID-token auth dependency (`receipt_api.auth`), lazily-built clients
  (`receipt_api.deps`), `POST /api/v1/documents/upload-url`. The error handler now keeps
  `WWW-Authenticate` and uses named error codes.

**Verification (actual results)**
- Unit tests: 242 passed in total (paths, signing, integrity, repository, endpoint auth/validation,
  Firebase verifier).
- **Live** (`make test-storage-live`): 4/4 passed against the real bucket and Firestore. Covered:
  upload via signed URL, record contents, read-back and integrity verification, signed download,
  anonymous access denied, wrong content type → 403, wrong size → 400, URL reused for another path
  → 403. Test data cleaned up; leftovers from two earlier failed runs were found and removed.
- Bugs found by the live run and fixed: google-cloud-storage 3.x removed the `generation` argument
  from `download_as_bytes()` and `Blob.delete()`. The unit-test fake now uses the real signature.
- The API Docker image builds and runs (352 MB, up from 261 MB because of firebase-admin and the
  GCP libraries); an unauthenticated upload-url request returns 401.

**Not verified / known gaps**
- **Real Firebase sign-in has not been exercised.** Firebase Auth isn't enabled on the project yet,
  and the local emulator needs Java, which isn't installed. Token verification is unit-tested with
  firebase-admin's error types; live sign-in comes with the login page (Phase 7/8).
- Records left in `AWAITING_UPLOAD` when an upload never happens need expiring (Phase 5/13).
- Bucket CORS only allows `http://localhost:5173`; the deployed frontend origin is added in Phase 11.
- Resources were created with gcloud; Phase 11 imports them into Terraform.

**Next:** Phase 5 — Eventarc and Cloud Run processing.
