-- Receipts vs. invoices: all processed documents, and how many became approved transactions.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE, @time_zone STRING (IANA, for the day boundaries) (on upload date)
SELECT
  IFNULL(d.document_type, 'unknown') AS document_type,
  COUNT(*) AS processed_count,
  COUNTIF(d.processing_status IN ('VALID', 'APPROVED')) AS approved_count
FROM `{{dataset}}.documents` AS d
WHERE d.user_id = @user_id
  AND DATE(d.created_at, @time_zone) BETWEEN @start_date AND @end_date
GROUP BY document_type
ORDER BY processed_count DESC;
