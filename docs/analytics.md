# BigQuery analytics

Dataset `receipt_analytics` (location `US`). Table definitions live in one place,
`backend/shared/src/receipt_shared/analytics/schema.py`. `sql/schema/*.sql` is generated from it
(`make sql-schema`), and a unit test fails if the two drift apart.

## Tables

| Table | Rows | Key | Partition / cluster |
|-------|------|-----|---------------------|
| `documents` | Every processed document (any outcome) | `document_id` | `DATE(created_at)` / `user_id, processing_status` |
| `extracted_transactions` | **Approved only** (VALID, or APPROVED after review) | `document_id` | `MONTH(document_date)` / `user_id, expense_category` |
| `line_items` | Line items of approved transactions | `document_id, line_number` | `MONTH(document_date)` / `user_id, document_id` |
| `review_records` | Review audit trail (written in Phase 9) | `review_id` | `DATE(reviewed_at)` / `user_id, document_id` |
| `extraction_metrics` | Per-extraction latency, tokens, outcome (production and evaluation) | `metric_id` | `DATE(processed_at)` / `model_version` |

Money is `NUMERIC`, document dates are `DATE`, and processing times are `TIMESTAMP`. Values travel
to BigQuery as JSON strings and are cast in SQL, so amounts never pass through a float.

## Idempotent writes

The worker writes each document in **one multi-statement transaction**
(`analytics/bigquery.py`):

1. `MERGE documents` on `document_id`.
2. `MERGE extraction_metrics` on `document_id:generation`.
3. If VALID/APPROVED: `MERGE extracted_transactions`, then `DELETE` + `INSERT` that document's
   `line_items`. Otherwise: `DELETE` the document from both tables, so they never hold unvalidated
   data.
4. `COMMIT`; on any error the whole transaction is rolled back.

Replaying a write leaves exactly one row per key. DML is used instead of streaming inserts, because
streamed rows can't be updated or deleted for a while.

The BigQuery write happens **before** the document's final Firestore status. If it fails, the
document isn't finalised and the event is retried (`bigquery_write_failed`, bounded by
`MAX_PROCESSING_ATTEMPTS`), so Firestore and BigQuery can't drift. Writes for FAILED documents are
best effort. Concurrent-transaction aborts are classified as retryable.

## Analytics queries

Packaged in `backend/shared/src/receipt_shared/analytics/sql/` (so the API image ships them) and
run through `AnalyticsQueries.run(name, user_id=..., start_date=..., end_date=...)`. Every per-user
query filters on `@user_id`. Totals are grouped **by currency**, with no currency conversion.
Spending queries filter on `document_date`; upload and review counts filter on
`DATE(created_at, @time_zone)` / `DATE(reviewed_at, @time_zone)`, so days follow the user's time zone.

| Query | Answers |
|-------|---------|
| `total_spending` | Total spent and tax, per currency |
| `monthly_spending` | Spend per month and currency |
| `spending_by_merchant` | Top merchants (`@limit`) |
| `spending_by_category` | Spend per expense category |
| `average_transaction_value` | Average, min and max transaction |
| `document_type_counts` | Receipts vs. invoices (processed and approved) |
| `processing_success_rate` | Share not FAILED; average and p95 processing time |
| `manual_review_rate` | Share of extracted documents that needed review |
| `extraction_accuracy_reviews` | Reviewer field-correction rate per model version |
| `extraction_accuracy_evaluation` | Benchmark field accuracy per evaluation run (Phase 10) |

## Access

| Principal | Access |
|-----------|--------|
| `receipt-worker` | `WRITER` (dataEditor) on this dataset only; `bigquery.jobUser` |
| `receipt-api` | `READER` (dataViewer) on this dataset only; `bigquery.jobUser` |

Dataset-level IAM policy bindings need allowlisting, so the bootstrap uses dataset access entries,
which are equivalent and dataset-scoped.

## Setup and tests

```bash
PROJECT_ID=my-project ./ops/gcp/bootstrap-bigquery.sh   # dataset, tables, access
make test-bigquery-live      # idempotency + approved-only + every query, on real BigQuery
make test-pipeline-live      # upload → worker → Firestore + BigQuery
```
