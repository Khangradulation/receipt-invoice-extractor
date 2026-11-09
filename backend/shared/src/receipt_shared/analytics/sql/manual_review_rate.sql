-- Share of successfully extracted documents that needed human review (first validation).
-- Duplicates and failures are excluded from the denominator.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE (on upload date)
SELECT
  COUNTIF(processing_status NOT IN ('FAILED', 'DUPLICATE')) AS extracted_documents,
  COUNTIF(review_required) AS review_required,
  COUNTIF(processing_status = 'REVIEW_REQUIRED') AS awaiting_review,
  COUNTIF(processing_status = 'APPROVED') AS approved_after_review,
  COUNTIF(processing_status = 'REJECTED') AS rejected,
  SAFE_DIVIDE(
    COUNTIF(review_required),
    COUNTIF(processing_status NOT IN ('FAILED', 'DUPLICATE'))
  ) AS review_rate
FROM `{{dataset}}.documents`
WHERE user_id = @user_id
  AND DATE(created_at) BETWEEN @start_date AND @end_date;
