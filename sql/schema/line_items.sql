-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.
-- Regenerate with: make sql-schema
CREATE TABLE IF NOT EXISTS `{{dataset}}.line_items` (
  document_id STRING NOT NULL,
  user_id STRING NOT NULL,
  line_number INT64 NOT NULL,
  description STRING,
  quantity NUMERIC,
  unit_price NUMERIC,
  total_price NUMERIC,
  currency STRING,
  document_date DATE NOT NULL,
  loaded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE_TRUNC(document_date, MONTH)
CLUSTER BY user_id, document_id
OPTIONS(description='Line items of approved transactions, linked by document_id.');
