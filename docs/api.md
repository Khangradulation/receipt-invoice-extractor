# REST API

Base path `/api/v1`. Interactive docs: `/api/v1/docs` (Swagger UI), `/api/v1/redoc`, schema
`/api/v1/openapi.json`.

Every endpoint except `/health` needs `Authorization: Bearer <Firebase ID token>`. The user is
taken **only** from the verified token. A document that belongs to someone else returns the same
`404` as one that doesn't exist.

## Endpoints

| Method | Path | Purpose | Rate limit (per user, per instance) |
|--------|------|---------|-------------------------------------|
| GET | `/health` | Liveness (no auth) | — |
| POST | `/documents/upload-url` | Create a document and get a signed upload URL ([storage.md](storage.md)) | 30/min |
| GET | `/documents` | Your documents, newest first. `?status=VALID&status=…`, `?limit=1–100`, `?cursor=` | 300/min |
| GET | `/documents/{id}` | Details: original extraction, corrected values, validation, history | 300/min |
| GET | `/documents/{id}/status` | Status, attempts, error (cheap to poll) | 300/min |
| GET | `/documents/{id}/extraction` | Original Gemini output plus model metadata (404 until extracted) | 300/min |
| GET | `/documents/{id}/file` | Short-lived signed URL to view the original file | 300/min |
| GET | `/review` | Your review queue (REVIEW_REQUIRED), paginated | 300/min |
| GET | `/review/{id}` | Original vs. current values, validation, failed fields, corrections, `can_approve` | 300/min |
| PATCH | `/review/{id}` | Save corrections `{"fields": {...}, "acknowledge_duplicate": false}`; revalidates; never approves | 60/min |
| POST | `/review/{id}/approve` | Approve. Allowed only when validation passes; loads the corrected record into BigQuery | 60/min |
| POST | `/review/{id}/reject` | Reject `{"reason": "..."}` (REVIEW_REQUIRED or DUPLICATE) | 60/min |
| GET | `/analytics/overview` | Totals, average, receipt/invoice counts, success rate, review rate | 60/min |
| GET | `/analytics/monthly-spending` | Spend per month and currency | 60/min |
| GET | `/analytics/categories` | Spend per category | 60/min |
| GET | `/analytics/merchants` | Top merchants (`?limit=1–50`) | 60/min |

Analytics take `?start_date=&end_date=` (ISO dates; default is the last 365 days; at most 5
years). Results are cached for 60 s per user and instance.

## Pagination

List endpoints return `{"items": [...], "next_cursor": "..."}`. Pass `next_cursor` back as
`cursor` for the next page; it is `null` on the last page. Ordering is `created_at DESC,
document_id DESC`, backed by Firestore composite indexes
(`ops/gcp/bootstrap-firestore-indexes.sh`).

## Errors

```json
{"error": {"code": "not_found", "message": "Document not found.", "request_id": "…"}}
```

| Status | `code` |
|--------|--------|
| 400 | `bad_request` (bad cursor, bad date range) |
| 401 | `unauthorized` (missing/invalid/expired token; `WWW-Authenticate: Bearer`) |
| 404 | `not_found` |
| 409 | `conflict`: wrong status for the action, or approval blocked. A blocked approval also returns `"validation": {...}` with the remaining errors |
| 413 / 415 | `file_too_large` / `unsupported_file_type` |
| 422 | `validation_error` (request body) or `invalid_correction` (bad field name or value) |
| 429 | `rate_limited` (`Retry-After` header) |
| 503 | `service_unavailable` (BigQuery or storage unavailable; safe to retry) |

## Review semantics

- **Corrections never change the original AI output.** They're stored in `review.corrected`, and
  each changed field appends an audit entry: field, original AI value, previous value, corrected
  value, reviewer and timestamp.
- **Approve** re-runs every validation rule on the corrected data and is refused (409) while
  errors remain. It writes BigQuery first, atomically: the approved transaction (`record_source =
  REVIEWED`), its line items, the document row, and all corrections plus the APPROVE action in
  `review_records`. Only then does Firestore change to `APPROVED`. If BigQuery is down, the request
  fails with 503 and nothing changes.
- **Reject** needs a reason (3–500 characters) and removes the document from approved analytics.
- A possible duplicate can be confirmed as a separate transaction with
  `"acknowledge_duplicate": true`. Exact-file duplicates can only be rejected.
