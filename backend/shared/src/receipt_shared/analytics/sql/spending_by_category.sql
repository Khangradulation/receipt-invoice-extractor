-- Spending per expense category and currency.
-- Params: @user_id STRING, @start_date DATE, @end_date DATE
SELECT
  IFNULL(expense_category, 'uncategorized') AS expense_category,
  currency,
  SUM(total_amount) AS total_amount,
  COUNT(*) AS transaction_count
FROM `{{dataset}}.extracted_transactions`
WHERE user_id = @user_id
  AND document_date BETWEEN @start_date AND @end_date
GROUP BY expense_category, currency
ORDER BY total_amount DESC;
