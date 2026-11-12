# Testing

Two tiers:

- **Automated tests** use fakes (in-memory repository, fake storage, fake Gemini, fake token
  verifier). They need no cloud access, cost nothing, and run on every PR.
- **Live tests** talk to real Google Cloud services. They are opt-in, may cost a few cents (Gemini
  calls), and clean up everything they create.

## Automated (free) — `make check`

`make check` runs everything CI runs: lint, format, types, the tests below, a coverage gate, the
Terraform checks, and the dependency and secret scans (in CI).

| Spec item | Where |
| --- | --- |
| Extraction response parsing | `shared/tests/extraction/test_gemini.py` (retries, blocked or truncated output, invalid JSON, schema mismatches), `test_schema.py`, `test_documents.py` (PDF/image loading and limits) |
| Pydantic models | `shared/tests/test_models.py`, `shared/tests/test_config.py` |
| Validation rules | `shared/tests/validation/test_field_rules.py`, `test_amount_rules.py`, `test_engine.py` |
| Duplicate detection | `shared/tests/validation/test_duplicates.py`, worker `test_pipeline.py` (same file, look-alike, other user's file) |
| Monetary calculations | `shared/tests/validation/test_arithmetic_rules.py` (subtotal + tax = total, line items, tolerances, Decimal precision), `analytics/test_rows.py` |
| API authorization | `api/tests/test_authorization.py`: every route in the OpenAPI spec must reject missing, forged and non-Bearer tokens, and every route taking a document ID must hide other users' documents. Plus per-feature tests in `test_documents_api.py`, `test_review_api.py`, `test_delete_api.py`. |
| Event processing (with fakes) | `worker/tests/test_pipeline.py` (idempotency, leases, retries, give-up, integrity failures), `test_events.py`, `test_endpoint.py` |
| BigQuery writes (with fakes) | `shared/tests/analytics/` (one transaction per document, parameters, error classification, delete) |
| Log privacy | `worker/tests/test_log_privacy.py` |
| Frontend: upload flow | `frontend/src/pages/upload.test.tsx` |
| Frontend: document listing and details, deletion | `frontend/src/pages/documents.test.tsx` |
| Frontend: review workflow | `frontend/src/pages/review.test.tsx`, `lib/reviewForm.test.ts` |
| Frontend: dashboard rendering | `frontend/src/pages/dashboard.test.tsx` |
| Frontend: auth, API client | `frontend/src/pages/auth.test.tsx`, `lib/api.test.ts` |

Backend coverage is measured on every run (`make coverage` prints it by file). The build fails
below **90%** (94% at Phase 15).

## Live (opt-in, billable)

Each needs Application Default Credentials (`gcloud auth application-default login`) and the root
`.env`. All delete what they create.

| Command | What it proves | Spec item |
| --- | --- | --- |
| `make test-storage-live` | Real signed upload URL → Cloud Storage → Firestore record; URLs reject the wrong type, size or path | Cloud Storage, Firestore persistence |
| `make test-gemini-live` | Real Gemini extraction of sample documents; prompt injection ignored | Gemini integration |
| `make test-bigquery-live` | Idempotent writes, exact NUMERIC money, every analytics query runs | BigQuery writes |
| `make test-pipeline-live` | Upload → Eventarc → **deployed** worker → Gemini → validation (valid, review, duplicate) | Event processing |
| `make test-api-live` | The API in-process against real services and the deployed worker: listing, paging, cross-user isolation, correction, approval, rejection, BigQuery audit | Integration of all of the above |
| `make test-e2e` | **The deployed system end to end** (see below) | End-to-end |
| `make smoke-test PROJECT_ID=… PROJECT_NUMBER=…` | Read-only health of a deployed environment (also run by every deploy) | — |

### End-to-end test (`make test-e2e`)

`shared/tests/integration/test_e2e_deployed.py` uses nothing fake. A throwaway Firebase user signs
in for real: a custom token is signed through IAM as the API's service account, so no key or
password exists. The test then calls the **deployed** API and follows the spec's ten steps:

1. Upload a receipt (signed URL from the deployed API, PUT to Cloud Storage).
2. Eventarc triggers the deployed worker.
3. Gemini extracts it.
4. The validator checks it: `VALID`.
5. The valid record is in BigQuery (`extracted_transactions`, `record_source = AI`).
6. Upload an invalid document (printed total doesn't match subtotal + tax).
7. Confirm it is in the review queue and can't be approved as is (409).
8. Correct the total.
9. Approve it.
10. Verify BigQuery: corrected total, `record_source = REVIEWED`, the correction and approval in
    `review_records`.

Then it deletes both documents through the API and checks that the file versions, the record and
every BigQuery row are gone. Finally it deletes the test user. It takes about 1–2 minutes and makes
2 Gemini calls.

Requirements: your ADC user needs Token Creator on the API service account (Terraform grants it to
`developer_members`). The API URL and Firebase web key come from `gcloud` and `.env`; override them
with `E2E_API_URL` and `FIREBASE_WEB_API_KEY`.

## Synthetic data

All tests and the benchmark use generated documents (`make samples`, `make dataset`). No real
receipts are stored in the repository or used in tests.
