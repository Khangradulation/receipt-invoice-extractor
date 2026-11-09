-- Spending per calendar month and currency.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE
SELECT
  DATE_TRUNC(document_date, MONTH) AS month,
  currency,
  SUM(total_amount) AS total_amount,
  COUNT(*) AS transaction_count
FROM `{{dataset}}.extracted_transactions`
WHERE user_id = @user_id
  AND document_date BETWEEN @start_date AND @end_date
GROUP BY month, currency
ORDER BY month, currency;
