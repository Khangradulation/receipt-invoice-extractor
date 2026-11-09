-- Benchmark accuracy (Phase 10 evaluation runs): field accuracy per run and model version.
-- Params: @start_date DATE, @end_date DATE (on run date)
SELECT
  evaluation_run_id,
  model_version,
  prompt_version,
  MIN(processed_at) AS run_started_at,
  COUNT(*) AS documents,
  SUM(fields_correct) AS fields_correct,
  SUM(fields_compared) AS fields_compared,
  SAFE_DIVIDE(SUM(fields_correct), SUM(fields_compared)) AS field_accuracy,
  ROUND(AVG(latency_ms), 1) AS avg_latency_ms
FROM `{{dataset}}.extraction_metrics`
WHERE evaluation_run_id IS NOT NULL
  AND DATE(processed_at) BETWEEN @start_date AND @end_date
GROUP BY evaluation_run_id, model_version, prompt_version
ORDER BY run_started_at DESC;
