# Extraction benchmark — receipts-90-prompt-20261111

- **Date:** 2026-11-11T07:23:06+00:00 (finished 2026-11-11T07:27:42+00:00)
- **Model:** `gemini-3.8-flash` (reported version `gemini-3.8-flash`), location `global`
- **Prompt version:** `2026-11-11.1` · **Validation rules:** `2026-11-09.1`
- **Dataset:** 150 synthetic documents, seed 20261110 (`evaluation/synthetic/generate.py`)
- **Documents:** 90 · succeeded 90 · errors 0
- **Command:** `uv run python ../evaluation/run_benchmark.py --document-type receipt --run-id receipts-90-prompt-20261111 --to-bigquery`

## Headline metrics

| Metric | Value |
|---|---|
| Exact required-field accuracy (merchant, date, total, currency, type all correct) | 100.0% |
| Core document accuracy (all objectively printed fields correct) | 100.0% |
| Fully correct documents (core fields + every line item) | 100.0% |
| Field accuracy (all fields, all documents) | 100.0% |
| Merchant accuracy | 100.0% |
| Date accuracy | 100.0% |
| Subtotal accuracy | 100.0% |
| Tax accuracy | 100.0% |
| Total accuracy | 100.0% |
| Currency accuracy | 100.0% |
| Document type accuracy | 100.0% |
| Monetary accuracy (subtotal, tax, discount, total) | 100.0% |
| Line items precision / recall / F1 | 100.0% / 100.0% / 100.0% |
| Documents with every line item exact | 100.0% |
| Hallucination rate (value returned where nothing printed) | 0.0% |
| Review rate (all / clean documents) | 3.3% / 0.0% |
| Inconsistent documents correctly sent to review | 100.0% |
| Prompt-injection documents resisted | 100.0% |
| Latency mean / p50 / p95 | 11637.0 / 6782.4 / 31327.7 ms |
| Tokens total / mean per document | 326,881 / 3632.0 |

## Per field

| Field | Accuracy | Wrong | Missed | Hallucinated |
|---|---|---|---|---|
| `document_type` | 100.0% | 0 | 0 | 0 |
| `document_number` | 100.0% | 0 | 0 | 0 |
| `document_date` | 100.0% | 0 | 0 | 0 |
| `due_date` | 100.0% | 0 | 0 | 0 |
| `currency` | 100.0% | 0 | 0 | 0 |
| `merchant_name` | 100.0% | 0 | 0 | 0 |
| `merchant_address` | 100.0% | 0 | 0 | 0 |
| `subtotal` | 100.0% | 0 | 0 | 0 |
| `tax_amount` | 100.0% | 0 | 0 | 0 |
| `discount_amount` | 100.0% | 0 | 0 | 0 |
| `total_amount` | 100.0% | 0 | 0 | 0 |
| `payment_method` | 100.0% | 0 | 0 | 0 |
| `expense_category` | 100.0% | 0 | 0 | 0 |

## By document type

| Document type | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| receipt | 90 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.3% | 11637.0 ms |

## By format

| Format | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| jpg | 28 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 14292.1 ms |
| pdf | 30 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 8099.8 ms |
| png | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 9.4% | 12630.1 ms |

## By layout

| Layout | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| classic | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.1% | 11413.1 ms |
| thermal | 58 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.5% | 11760.6 ms |

## By currency

| Currency | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| AUD | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 4644.1 ms |
| CAD | 16 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 12.5% | 11015.2 ms |
| EUR | 11 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 12350.9 ms |
| GBP | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 15967.4 ms |
| INR | 8 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 12.5% | 9766.2 ms |
| JPY | 13 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 12666.7 ms |
| PKR | 13 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 11414.3 ms |
| USD | 13 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 12910.2 ms |

## By scenario tag

| Scenario tag | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| discount | 14 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 7.1% | 12811.2 ms |
| multi_tax | 13 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 15.4% | 9957.1 ms |
| no_tax_printed | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 10777.2 ms |
| photo_like | 16 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 13305.3 ms |
| prompt_injection | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 9702.9 ms |
| qty_not_printed | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.2% | 12022.1 ms |
| tax_inclusive | 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 13978.3 ms |
| total_mismatch | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 18378.6 ms |

## Errors

None.

## Documents with core-field differences (0)

None.

_Synthetic, fictional documents. Results describe this dataset and model configuration only._
