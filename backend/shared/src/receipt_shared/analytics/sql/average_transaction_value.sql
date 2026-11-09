-- Average, smallest and largest transaction per currency.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE
SELECT
  currency,
  ROUND(AVG(total_amount), 2) AS average_amount,
  MIN(total_amount) AS min_amount,
  MAX(total_amount) AS max_amount,
  COUNT(*) AS transaction_count
FROM `{{dataset}}.extracted_transactions`
WHERE user_id = @user_id
  AND document_date BETWEEN @start_date AND @end_date
GROUP BY currency
ORDER BY transaction_count DESC;
