-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.
-- Regenerate with: make sql-schema
CREATE TABLE IF NOT EXISTS `{{dataset}}.extraction_metrics` (
  metric_id STRING NOT NULL OPTIONS(description='document_id:generation, or run_id:document_id'),
  document_id STRING NOT NULL,
  user_id STRING,
  evaluation_run_id STRING OPTIONS(description='Set for benchmark runs (Phase 10)'),
  model STRING,
  model_version STRING,
  prompt_version STRING,
  location STRING,
  mime_type STRING,
  page_count INT64,
  latency_ms FLOAT64,
  gemini_attempts INT64,
  prompt_tokens INT64,
  output_tokens INT64,
  thoughts_tokens INT64,
  total_tokens INT64,
  outcome STRING OPTIONS(description='Status after validation'),
  missing_field_count INT64,
  extraction_warning_count INT64,
  fields_compared INT64 OPTIONS(description='Evaluation only'),
  fields_correct INT64 OPTIONS(description='Evaluation only'),
  processed_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(processed_at)
CLUSTER BY model_version
OPTIONS(description='Per-extraction performance metrics (production and evaluation runs).');
