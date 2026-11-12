# Monitoring and observability

Everything is defined in [`terraform/modules/monitoring`](../terraform/modules/monitoring).

## Logs

The API and worker write one JSON object per line to stdout. Cloud Run sends it to Cloud Logging, where
`message` and every extra field become queryable `jsonPayload` fields
(`receipt_shared/logging.py`).

- **Always included:** `document_id` (and `request_id` / `trace_id` for API requests, `event_id` and
  `attempt` for worker events), statuses, counts, durations, error codes and error types.
- **Never included:** file contents, extracted fields (merchant, amounts, line items), filenames,
  signed URLs, query strings, tokens. `worker/tests/test_log_privacy.py` runs the worker through the
  valid, review and failure paths and fails if any of those values reach a log line.

Useful Logs Explorer queries:

```
resource.labels.service_name="receipt-worker" jsonPayload.document_id="<id>"   # one document's journey
resource.labels.service_name="receipt-api" jsonPayload.request_id="<id>"      # one API request
resource.labels.service_name="receipt-worker" severity>=ERROR                 # unexpected errors
jsonPayload.message="bigquery job failed"                                      # analytics write problems
```

## Metrics

Log-based metrics (`logging.googleapis.com/user/receipt/...`), plus Cloud Run's built-in request
metrics:

| Spec item | Metric | Source log event |
| --- | --- | --- |
| Document uploads | `receipt/upload_urls_issued` (by content type) | API `upload url issued` |
| Processing attempts | `receipt/processing_attempts` (by attempt number) | worker `processing started` |
| Processing duration | `receipt/processing_duration_ms` (distribution) | worker `processing completed` |
| Validation failures | `receipt/documents_processed` with `status=REVIEW_REQUIRED` (all outcomes by status) | worker `processing completed` |
| Processing failures | `receipt/processing_failures` (by error code) | worker `processing failed permanently` / `... will retry` |
| Event processing retries | `receipt/event_retries` (by reason) | worker `... will retry` / `event redelivered while processing` |
| Gemini latency | `receipt/gemini_latency_ms` (distribution) | worker `extraction stored` |
| Gemini errors | `receipt/gemini_errors` (by error code, every failed attempt) | `gemini attempt failed` / `gemini extraction failed` |
| BigQuery write failures | `receipt/bigquery_write_failures` (the log entry's `operation` says write or delete) | `bigquery job failed` |
| Manual review volume | `receipt/review_actions` (corrections, approvals, rejections) and `documents_processed{status=REVIEW_REQUIRED}` | API review events |
| API errors | `run.googleapis.com/request_count` by `response_code_class` | Cloud Run |
| Worker errors | `receipt/worker_errors` (severity ≥ ERROR) | worker |
| Deletions | `receipt/documents_deleted` | API `document deleted` |

## Dashboard

**Receipt extractor: pipeline** (Cloud Console → Monitoring → Dashboards) has one chart per metric
above, plus API latency, Cloud Run instance counts, and the review rate (share of documents needing
review, 1-hour window) with the alert threshold marked.

## Alerts

All alerts email the addresses in `alert_emails` (Terraform variable) and close automatically
once the condition clears.

| Alert | Fires when | Severity | First steps |
| --- | --- | --- | --- |
| High processing failure count | more than 5 worker failures in 15 min | Error | Dashboard → failures by error code; then the worker logs for that code. `integrity_check_failed` = bad uploads; `model_*` = Gemini; `internal_error` = a bug. |
| Repeated worker errors | 3 or more worker ERROR logs in 15 min | Error | `severity>=ERROR` in worker logs; each has `document_id` and a stack trace. |
| High Gemini latency | p95 above 60 s for 15 min | Warning | Vertex AI status page; `gemini_errors` for rate limiting (`rate_limited`). Documents still complete. |
| BigQuery write failures | any failed BigQuery job in 10 min | Error | Search `bigquery job failed`, check `error_type`. The worker retries; dashboards lag until it succeeds. |
| Unusually high review rate | over 50% of documents need review over 6 h, with at least 10 documents | Warning | Look at the review queue for a pattern (new layout, currency, merchant); run `make evaluate ARGS="--limit 20"` to check for a model or prompt regression. |
| API server errors | more than 5 HTTP 5xx in 10 min | Error | API logs: `unhandled error` entries carry the `request_id` the client saw. |

Thresholds suit dev volumes; adjust them in the module for production traffic (the review-rate
threshold is the `review_rate_threshold` variable).

## Cost

Log-based metrics, dashboards, alerting and email notifications are free at this volume. Cloud
Logging's free allotment (50 GiB/month) is far above what the app writes.
