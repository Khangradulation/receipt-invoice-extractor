-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.
-- Regenerate with: make sql-schema
CREATE TABLE IF NOT EXISTS `{{dataset}}.documents` (
  document_id STRING NOT NULL,
  user_id STRING NOT NULL,
  document_type STRING,
  processing_status STRING NOT NULL OPTIONS(description='Current status (VALID, REVIEW_REQUIRED, ...)'),
  validation_status STRING OPTIONS(description='Latest validation outcome'),
  review_required BOOL OPTIONS(description='Initial validation sent it to review'),
  duplicate_status STRING,
  error_count INT64,
  warning_count INT64,
  failed_fields ARRAY<STRING>,
  error_code STRING OPTIONS(description='Processing error code if FAILED'),
  content_type STRING,
  size_bytes INT64,
  page_count INT64,
  model_version STRING,
  prompt_version STRING,
  rules_version STRING,
  processing_attempts INT64,
  processing_duration_ms FLOAT64,
  created_at TIMESTAMP NOT NULL,
  uploaded_at TIMESTAMP,
  completed_at TIMESTAMP,
  loaded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY user_id, processing_status
OPTIONS(description='One row per processed document (all outcomes), for operational analytics.');
