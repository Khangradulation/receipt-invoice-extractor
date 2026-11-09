-- Total spending per currency (amounts in different currencies are never added together).
-- Params: @user_id STRING, @start_date DATE, @end_date DATE
SELECT
  currency,
  SUM(total_amount) AS total_amount,
  SUM(IFNULL(tax_amount, 0)) AS total_tax,
  COUNT(*) AS transaction_count
FROM `{{dataset}}.extracted_transactions`
WHERE user_id = @user_id
  AND document_date BETWEEN @start_date AND @end_date
GROUP BY currency
ORDER BY total_amount DESC;
