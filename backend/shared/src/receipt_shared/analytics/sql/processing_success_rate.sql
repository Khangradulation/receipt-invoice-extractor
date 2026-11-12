-- Share of uploaded documents that were processed without a processing failure.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE, @time_zone STRING (IANA, for the day boundaries) (on upload date)
SELECT
  COUNT(*) AS processed_documents,
  COUNTIF(processing_status != 'FAILED') AS succeeded,
  COUNTIF(processing_status = 'FAILED') AS failed,
  COUNTIF(processing_status = 'DUPLICATE') AS duplicates,
  SAFE_DIVIDE(COUNTIF(processing_status != 'FAILED'), COUNT(*)) AS success_rate,
  ROUND(AVG(processing_duration_ms), 1) AS avg_processing_ms,
  APPROX_QUANTILES(processing_duration_ms, 100)[SAFE_OFFSET(95)] AS p95_processing_ms
FROM `{{dataset}}.documents`
WHERE user_id = @user_id
  AND DATE(created_at, @time_zone) BETWEEN @start_date AND @end_date;
