-- Top merchants by spend, per currency.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE, @limit INT64
SELECT
  merchant_name,
  currency,
  SUM(total_amount) AS total_amount,
  COUNT(*) AS transaction_count,
  MAX(document_date) AS last_transaction_date
FROM `{{dataset}}.extracted_transactions`
WHERE user_id = @user_id
  AND document_date BETWEEN @start_date AND @end_date
GROUP BY merchant_name, currency
ORDER BY total_amount DESC
LIMIT @limit;
