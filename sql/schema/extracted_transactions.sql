-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.
-- Regenerate with: make sql-schema
CREATE TABLE IF NOT EXISTS `{{dataset}}.extracted_transactions` (
  document_id STRING NOT NULL,
  user_id STRING NOT NULL,
  document_type STRING NOT NULL,
  merchant_name STRING NOT NULL,
  merchant_address STRING,
  document_date DATE NOT NULL,
  due_date DATE,
  document_number STRING,
  currency STRING NOT NULL,
  subtotal NUMERIC,
  tax_amount NUMERIC,
  discount_amount NUMERIC,
  total_amount NUMERIC NOT NULL,
  expense_category STRING,
  payment_method STRING,
  processing_status STRING NOT NULL,
  record_source STRING NOT NULL OPTIONS(description='AI (validated automatically) or REVIEWED'),
  model_version STRING,
  approved_by STRING,
  approved_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  loaded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE_TRUNC(document_date, MONTH)
CLUSTER BY user_id, expense_category
OPTIONS(description='Approved transactions only (VALID, or APPROVED after review).');
