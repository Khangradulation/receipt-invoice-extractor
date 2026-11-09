# SQL

- `schema/` — BigQuery DDL for the five `receipt_analytics` tables. **Generated** from
  `backend/shared/src/receipt_shared/analytics/schema.py`; run `make sql-schema` after changing
  the specs. `{{dataset}}` is replaced by `ops/gcp/bootstrap-bigquery.sh`.
- Analytics queries live in
  [`backend/shared/src/receipt_shared/analytics/sql/`](../backend/shared/src/receipt_shared/analytics/sql/)
  so they are packaged with the API. See [docs/analytics.md](../docs/analytics.md).
