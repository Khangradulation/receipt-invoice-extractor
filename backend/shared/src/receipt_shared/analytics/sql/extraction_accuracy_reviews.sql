-- Production accuracy signal: how often reviewers had to correct Gemini, per model version.
-- field_correction_rate = corrected fields / (reviewed documents x 13 extractable fields).
-- Params: @user_id STRING, @start_date DATE, @end_date DATE (on review date)
WITH reviewed AS (
  SELECT
    model_version,
    document_id,
    COUNTIF(action = 'CORRECTION') AS corrections
  FROM `{{dataset}}.review_records`
  WHERE user_id = @user_id
    AND DATE(reviewed_at) BETWEEN @start_date AND @end_date
  GROUP BY model_version, document_id
)
SELECT
  IFNULL(model_version, 'unknown') AS model_version,
  COUNT(*) AS reviewed_documents,
  SUM(corrections) AS corrected_fields,
  COUNTIF(corrections = 0) AS documents_without_corrections,
  SAFE_DIVIDE(SUM(corrections), COUNT(*) * 13) AS field_correction_rate
FROM reviewed
GROUP BY model_version
ORDER BY reviewed_documents DESC;
