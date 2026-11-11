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
| 5 | Eventarc + Cloud Run processing | Done — verified live (see Phase log) |
| 6 | BigQuery data warehouse | Done — verified live (see Phase log) |
| 7 | FastAPI backend | Done — verified live in-process; not yet deployed (see Phase log) |
| 8 | React frontend | Done — verified end to end in the browser (see Phase log) |
| 9 | Manual review workflow | Done — verified live (see Phase log) |
| 10 | Extraction evaluation framework | Done — full run complete (see Phase log) |
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

### Phase 5 — Eventarc + Cloud Run processing (2026-11-09)

**Implemented** (details: [docs/processing.md](docs/processing.md))
- Worker (`receipt_worker`):
  - `events.py`: CloudEvents parser (binary and structured mode).
  - `pipeline.py`: `DocumentProcessor`, which claims, verifies, extracts, validates and persists,
    with permanent vs. transient error handling.
  - `POST /events/storage`.
- Repository: `decide_claim` (pure) plus transactional `claim` (Firestore) keyed by document id +
  object generation with a lease; `update` with history; `find_duplicate_candidates`; and
  `RepositoryDuplicateIndex` for the validator.
- Statuses: added `DUPLICATE`; re-claim transitions for crashed attempts.
- The original Gemini output is written once. A retry after a crash reuses it (no second call, no
  overwrite).
- Settings: `WORKER_LEASE_SECONDS`, `MAX_PROCESSING_ATTEMPTS`.
- GCP (`ops/gcp/bootstrap-worker.sh`, `ops/gcp/deploy-worker.sh`, `ops/gcp/cloudbuild-image.yaml`):
  - service accounts `receipt-worker`, `receipt-eventarc` and `receipt-build` (least privilege);
  - Artifact Registry `receipt-extractor` with cleanup policies;
  - Cloud Build (BuildKit) image build;
  - Cloud Run `receipt-worker` (internal ingress, IAM-only, max 3 instances);
  - Eventarc trigger on `object.finalized` for the documents bucket;
  - subscription ack deadline 600 s with 10–600 s retry backoff.
- Sample generator: added `receipt_total_mismatch` (printed total ≠ subtotal + tax).

**Verification (actual results)**
- Unit tests: 275 passed in total (35 worker tests covering events, the pipeline and the endpoint:
  replays, an in-flight lease → 429, crash recovery, reuse of stored extraction, transient →
  retry → success, giving up after max attempts, permanent failures, integrity failures, ignored
  events).
- Deploy: image built in 31 s, `receipt-worker-00001` serving; trigger, IAM and subscription
  settings verified.
- **Live end-to-end** (`make test-pipeline-live`): 3/3 passed with real upload → Eventarc → worker
  → Gemini (`gemini-3.8-flash`) → Firestore:
  - valid café receipt → VALID (history UPLOADED → PROCESSING → EXTRACTED → VALIDATING → VALID,
    one attempt, 5.4 s);
  - inconsistent receipt → REVIEW_REQUIRED (TOTAL_MISMATCH, 12.0 s);
  - same file again → DUPLICATE, linked to the first (5.3 s).
- Worker logs: no errors, no redeliveries, no document contents. Test data cleaned up.

**Not verified / known gaps**
- An event replay was not sent to the *deployed* worker (internal ingress blocks direct calls from
  outside). Replays, in-flight duplicates and crash recovery are covered by unit tests.
- BigQuery loading of VALID records is Phase 6 (the `ValidSink` hook exists but has no sink yet).
- Expiring records stuck in `AWAITING_UPLOAD` is still open (Phase 13).
- The API isn't deployed yet (Phase 7/11). Its signing permissions are already in place.

**Next:** Phase 6 — BigQuery data warehouse.

### Phase 6 — BigQuery data warehouse (2026-11-10)

**Implemented** (details: [docs/analytics.md](docs/analytics.md))
- `receipt_shared.analytics`:
  - `schema.py`: single source of truth for the 5 tables. `sql/schema/*.sql` is generated from it
    (`make sql-schema`), with a drift test.
  - `rows.py`: pure row builders (approved-only transactions; exact decimals).
  - `bigquery.py`: one multi-statement transaction per document (MERGE + replace line items,
    rollback on error, retryable error classification).
  - `queries.py` + `sql/*.sql`: 10 analytics queries.
- Worker: a BigQuery sink records every outcome. The write happens before the final Firestore
  status (retried on failure); FAILED documents are recorded best effort. New
  `analytics_loaded_at` field.
- GCP: `ops/gcp/bootstrap-bigquery.sh` creates dataset `receipt_analytics` (US), the 5 partitioned
  and clustered tables, dataset access entries (worker WRITER, API READER) and `bigquery.jobUser`
  for both. Worker redeployed as `receipt-worker-00002`.
- New sample-independent live tests: `make test-bigquery-live`; `make test-pipeline-live` now also
  checks BigQuery.

**Verification (actual results)**
- Unit tests: 323 passed (schema drift, row building, script structure, error classification,
  query parameters, worker analytics retry/best-effort).
- **Live BigQuery** (`make test-bigquery-live`): 12/12 passed. A write replayed twice leaves 1 row
  in each table (2 line items); re-writing as REVIEW_REQUIRED removes the transaction and line
  items; amounts come back exact (`26.68`, `3.48`); all 10 queries run on real data.
- **Live end-to-end** (`make test-pipeline-live`): 3/3 passed on the redeployed worker:
  - VALID → `documents` 1, `extracted_transactions` 1, `line_items` 3, `extraction_metrics` 1;
  - REVIEW_REQUIRED → `documents` only;
  - DUPLICATE → no transaction.
- Worker logs: no warnings or errors. Test rows deleted afterwards.

**Known issues**
- The BigQuery write takes about 10 s per document (multi-statement transaction), raising total
  processing time from about 5 s to about 18 s. It's asynchronous, so users don't wait on it.
  Batching or the Storage Write API with a periodic MERGE could cut this later.
- `bq add-iam-policy-binding` on datasets needs allowlisting, and the `bq` CLI mis-parses
  hyphenated project ids; the bootstrap uses dataset access entries via the Python client instead.
- No currency conversion: totals are reported per currency.

**Next:** Phase 7 — FastAPI backend.

### Phase 7 — FastAPI backend (2026-11-10)

**Implemented** (details: [docs/api.md](docs/api.md))
- All endpoints from the spec, plus `GET /documents/{id}/file`: documents (list, detail, status,
  extraction, file URL), review (queue, detail, PATCH corrections, approve, reject), analytics
  (overview, monthly spending, categories, merchants), and health.
- Authorization: `owned_record()` gives the same 404 for missing and foreign documents; the user
  comes only from the Firebase token.
- `ReviewService`:
  - corrections are stored separately from the original AI output, with a per-field audit trail;
  - every save revalidates (with optional duplicate acknowledgement);
  - approval is refused while errors remain;
  - approve/reject write BigQuery atomically (transaction plus `review_records`) before Firestore.
- Cursor pagination (`list_for_user` for Firestore and in-memory), status filter, response
  schemas, OpenAPI docs.
- Per-user token-bucket rate limits (upload 30, review writes 60, analytics 60, reads 300 per
  minute per instance) with `Retry-After`; 60 s analytics cache; date-range validation.
- Error model additions: `rate_limited`, `conflict` (with `validation`), `invalid_correction`,
  `service_unavailable`.
- GCP: Firestore composite indexes (`ops/gcp/bootstrap-firestore-indexes.sh`); API access to
  BigQuery raised from READER to WRITER on the dataset (approvals load data).

**Verification (actual results)**
- Unit tests: 379 backend tests passed, including 86 API tests: auth on every endpoint, cross-user
  access → 404 for read and write, pagination, filters, corrections and audit, original
  preserved, approval blocked/allowed, BigQuery failure → 503 with no state change, rejection,
  analytics caching per user, rate limits.
- **Live** (`make test-api-live`): 1/1 passed (110 s) with real Firestore, Cloud Storage,
  BigQuery and the deployed worker:
  - two uploads processed (VALID, REVIEW_REQUIRED);
  - paging over the composite index; status filter;
  - details, extraction and file download (bytes match);
  - a second user gets 404 everywhere;
  - approval blocked → corrected 28.86 → 25.86 → approved;
  - BigQuery holds the transaction (25.86, REVIEWED) and the audit (CORRECTION 28.86 → 25.86,
    APPROVE);
  - analytics total CAD 52.54 and review rate 0.5.
- All test data removed (verified 0 objects, records and BigQuery rows).

**Not verified / known gaps**
- **The API is not deployed to Cloud Run yet** (Phase 11/12). Live tests ran the API in-process
  against real cloud services.
- **Real Firebase sign-in is still untested.** Firebase Auth gets enabled with the login page in
  Phase 8, where the user registers their own account.
- Rate limits and the analytics cache are per instance; a shared limiter (e.g. Redis or API
  Gateway) would be needed for strict global limits.

**Next:** Phase 8 — React frontend.

### Phase 8 — React frontend (2026-11-10)

**Implemented** (details: [docs/frontend.md](docs/frontend.md))
- Firebase: added to the GCP project, web app created, Auth initialised (Identity Platform),
  email/password enabled, `localhost` authorised. Config written to `.env` (public values).
- Nine pages: login/registration, overview, upload, documents, document details, review queue,
  review editor, analytics, settings. Sidebar layout, responsive drawer, loading/empty/error states.
- Typed API client with ID token, refresh-and-retry on 401, and an error model including
  `validation`. `AuthProvider` clears cached data on sign-out.
- Upload: client checks, SHA-256, signed-URL PUT with progress, live status polling, deep links
  to review.
- Review editor: file side by side with fields; failed fields highlighted (`aria-invalid`); only
  changed fields sent; approve gated on `can_approve` and no unsaved edits; reject reason modal;
  duplicate acknowledgement; correction history.
- Analytics: per-currency cards and charts (Recharts), date range.
- Code-split heavy pages: initial JS 249 KB → 91 KB gzip; Firebase in its own chunk.
- `@grpc/grpc-js` overridden to ^1.13.6 (high-severity advisory via firebase; not in the browser
  bundle). `npm audit`: 0 vulnerabilities.

**Verification (actual results)**
- Frontend: 36 tests passed (upload flow, document listing, details, review workflow, dashboard
  rendering, auth, API client). ESLint and Prettier clean, `tsc` clean, production build OK.
- Tests caught and fixed: lower-case currency counted as an edit; ambiguous "Total" label between
  the document total and line totals (accessibility).
- `make check` exits 0 (backend 379, kill switch 7, frontend 36).
- **Live, locally:** API (`uv run receipt-api`) and Vite against the real project. The user
  registered their own account; requests with the real Firebase ID token returned 200 for
  `/documents`, `/analytics/overview` and `/review`; a request without a token returned 401. This
  is the first live verification of Firebase token checking.

- **Real upload by the user:** an intentionally tricky PKR invoice uploaded through the UI was
  processed automatically (14.7 s), classified as an invoice in PKR, and correctly held as
  REVIEW_REQUIRED (`UNSUPPORTED_CURRENCY`). Follow-ups:
  - PKR added to the default `SUPPORTED_CURRENCIES` (code, `.env`, deploy script, live worker
    revision `receipt-worker-00003`);
  - `GET /review/{id}` now re-runs validation with the current rules (`ReviewService.live_state`),
    so the invoice became approvable without re-uploading (new test).
- **The user approved it in the browser:** `POST /review/{id}/approve` → 200. Firestore went
  REVIEW_REQUIRED → APPROVED; BigQuery has 1 transaction (PKR, invoice, `REVIEWED`), 6 line items
  and the APPROVE audit record. That's the full upload → AI → validation → review → approval →
  warehouse loop, verified through the real UI with real sign-in.

**Not verified / known gaps**
- The frontend isn't deployed yet (Phase 11/12). The production origin must be added to the
  bucket CORS and to Firebase authorised domains.
- Email verification isn't required at sign-up.

**Next:** Phase 9 — Manual review workflow (end-to-end verification through the UI).

### Phase 9 — Manual review workflow (2026-11-10)

Most of the workflow shipped in Phases 7–8 (review API, editor, audit trail, BigQuery export).
This phase closed the remaining gaps and verified everything end to end. Details:
[docs/review.md](docs/review.md).

**Implemented**
- Optimistic concurrency for review writes (`update_if_unchanged`, Firestore transaction on
  `updated_at`). Stale saves, approvals and rejections return 409 "reload". When a decision loses a
  race after writing BigQuery, BigQuery is resynced to the winning state (`ReviewService.rows_for`).
- Document details now include `review`: the decision (approved/rejected, by, at, reason) and the
  correction audit trail. A new *Review & audit* card on the document page shares the
  `CorrectionHistory` component with the editor.
- Editor: warns before closing with unsaved corrections; reloads automatically after a conflict.

**Verification (actual results)**
- Backend 385 tests (new: stale save refused without overwriting the other edit; approve racing
  reject leaves REJECTED in Firestore and resyncs BigQuery to REJECT; 409 message; audit on the
  document page; repository concurrency).
- Frontend 39 tests (new: audit card for approved/rejected; conflict → message and refetch).
- **Live** (`make test-api-live`): 2/2 passed against real services and the deployed worker:
  - approve path: correction 28.86 → 25.86, APPROVE audit, analytics totals;
  - reject path: same file → DUPLICATE → approve refused (409) → rejected with a reason → second
    reject refused (409) → decision on the document page → BigQuery `documents` REJECTED, no
    transaction, REJECT audit row with reason and reviewer.
- Earlier in the browser (Phase 8): a real user approved a real PKR invoice end to end.

**Known gaps**
- Corrections reach BigQuery `review_records` when the document is decided; until then they live
  only in Firestore (which is what the UI reads).

**Next:** Phase 10 — Extraction evaluation framework.

### Phase 10 — Extraction evaluation framework (2026-11-10)

**Implemented** (details: [docs/evaluation.md](docs/evaluation.md))
- `evaluation/synthetic/`: deterministic generator (seed 20261110) of 150 fictional documents with
  ground-truth JSON and a manifest:
  - 90 receipts and 60 invoices; thermal, classic and invoice layouts;
  - PDF (18 multi-page), PNG and JPEG; 8 currencies; 4 date styles;
  - VAT-inclusive prices, multiple taxes, discounts, no-tax, unprinted quantities, photo-like
    degradation;
  - 5 prompt-injection and 5 inconsistent-total documents.

  Ground truth records what is printed. ASCII-only guard.
- `evaluation/benchmark/`: field scoring (correct / wrong / missed / hallucinated; Decimal money
  within the currency's minor unit; normalised text; IDs), line-item matching
  (precision/recall/F1), aggregation (spec metrics, review metrics, injection resistance, latency,
  tokens, breakdowns), Markdown renderer. `evaluation/REPORT_TEMPLATE.md`.
- `evaluation/run_benchmark.py`: parallel, resumable runner using the production extractor and
  validator; writes `results.jsonl`, `report.json` and `report.md` stamped with model version,
  prompt version, rules version, date and command; `--to-bigquery` logs `extraction_metrics`
  rows.
- `make dataset`, `make evaluate`. Evaluation unit tests run in `make check`.

**Bugs caught before the paid run:** 7 image invoices would have lost page 2 (images now
single-page); tax tags were applied when no tax was printed; `&` vs "and" was scored as wrong.

**Results — run `full-150-20261110`** (`gemini-3.8-flash`, prompt `2026-11-08.1`; report
committed in `evaluation/reports/full-150-20261110/`):
- 150/150 succeeded, 0 errors.
- Exact required-field accuracy **100%**; core document accuracy **100%**; fully correct
  documents (core + every line item) **100%**; field accuracy **97.0%** (1,892/1,950).
- Merchant, date, subtotal, tax, total, currency and document type: **100%** each. Line items:
  precision, recall and F1 100%.
- **Weakness: `payment_method` 61.3%.** On 58 of 60 invoices the model returned `bank_transfer`
  from the payment *terms* line, although nothing was paid. This accounts for the whole
  hallucination rate (19.1% of unprinted fields).
- Review: 3.3% overall = exactly the 5 inconsistent documents (100% flagged); 0% false review on
  clean documents. Prompt injection resisted: 5/5.
- Latency mean 9.7 s, p50 7.1 s, p95 20.1 s (multi-page invoices slowest, 13.3 s mean); 559,504
  tokens (≈3.7k per document).
- BigQuery: 150 `extraction_metrics` rows; `extraction_accuracy_evaluation` returns the run
  (field accuracy 0.9703).

**Interpretation and limitations**
- **The dataset is saturated:** core accuracy is 100% across every format, layout, currency and
  scenario. These are clean, computer-rendered synthetic documents (with mild rotation/blur at
  most), so the scores say little about crumpled, faded, handwritten or photographed real
  receipts. A harder tier (heavy noise, low resolution, handwriting, skewed photos, real-world
  layouts under a suitable licence) is needed to discriminate between models or prompts.
- Expense category scored 100% partly because synthetic merchant names are unambiguous.

**Prompt fix and re-measure (2026-11-11)**
- Prompt `2026-11-11.1`: `payment_method` only when a completed payment is shown; payment terms
  and instructions mean null. Response-schema description updated to match. New
  `--document-type` benchmark option.
- Run `invoices-60-prompt-20261111` (`gemini-3.8-flash`, the same 60 invoices):
  `payment_method` **2/60 → 60/60**; invoice field accuracy **92.6% → 100%**; hallucination rate
  0%; core fields, line items, review flags and injection resistance unchanged at 100%; 0 errors.
- Latency: median 9.3 s → 10.1 s, but mean 10.9 s → 20.2 s and p95 66.3 s, from a handful of
  documents taking 60–75 s. All documents took one attempt and token counts were unchanged, so
  the prompt doesn't explain it; temporary service-side slowness is likely but not proven.

- Run `receipts-90-prompt-20261111` (the same 90 receipts): `payment_method` stayed **90/90**, field
  accuracy 100%, 0 errors, no regression in any field. Median latency 6.2 s → 6.8 s; mean
  8.8 s → 11.6 s, again from a slow tail with one attempt each.
- Combined on prompt `2026-11-11.1`: all 150 documents at 100% field accuracy (1,950/1,950).

**Not verified**
- Every synthetic receipt prints its payment as "Paid: ...". Receipts that show only "VISA ****1234"
  or "Debit card contactless", with no "Paid" wording, are not covered, so over-caution on those
  is not ruled out. Worth adding to a harder dataset tier.
- The deployed worker (`receipt-worker-00003`) still runs prompt `2026-11-08.1` until it is
  redeployed.

**Next:** merge Phase 10, redeploy the worker, then Phase 11 (Terraform).
