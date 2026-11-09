-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.
-- Regenerate with: make sql-schema
CREATE TABLE IF NOT EXISTS `{{dataset}}.review_records` (
  review_id STRING NOT NULL,
  document_id STRING NOT NULL,
  user_id STRING NOT NULL,
  action STRING NOT NULL OPTIONS(description='CORRECTION, APPROVE or REJECT'),
  field_name STRING,
  original_value STRING OPTIONS(description='Value extracted by Gemini'),
  corrected_value STRING,
  reason STRING,
  reviewer_id STRING NOT NULL,
  model_version STRING,
  reviewed_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(reviewed_at)
CLUSTER BY user_id, document_id
OPTIONS(description='Audit trail of manual review actions and field corrections.');
