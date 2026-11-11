# Extraction benchmark — full-150-20261110

- **Date:** 2026-11-10T05:22:59+00:00 (finished 2026-11-10T05:29:06+00:00)
- **Model:** `gemini-3.8-flash` (reported version `gemini-3.8-flash`), location `global`
- **Prompt version:** `2026-11-08.1` · **Validation rules:** `2026-11-09.1`
- **Dataset:** 150 synthetic documents, seed 20261110 (`evaluation/synthetic/generate.py`)
- **Documents:** 150 · succeeded 150 · errors 0
- **Command:** `uv run python ../evaluation/run_benchmark.py --run-id full-150-20261110 --to-bigquery`

## Headline metrics

| Metric | Value |
|---|---|
| Exact required-field accuracy (merchant, date, total, currency, type all correct) | 100.0% |
| Core document accuracy (all objectively printed fields correct) | 100.0% |
| Fully correct documents (core fields + every line item) | 100.0% |
| Field accuracy (all fields, all documents) | 97.0% |
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
| Hallucination rate (value returned where nothing printed) | 19.1% |
| Review rate (all / clean documents) | 3.3% / 0.0% |
| Inconsistent documents correctly sent to review | 100.0% |
| Prompt-injection documents resisted | 100.0% |
| Latency mean / p50 / p95 | 9652.4 / 7055.1 / 20057.2 ms |
| Tokens total / mean per document | 559,504 / 3730.0 |

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
| `payment_method` | 61.3% | 0 | 0 | 58 |
| `expense_category` | 100.0% | 0 | 0 | 0 |

## By document type

| Document type | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| invoice | 60 | 100.0% | 100.0% | 92.6% | 100.0% | 100.0% | 3.3% | 10900.1 ms |
| receipt | 90 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.3% | 8820.6 ms |

## By format

| Format | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| jpg | 28 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 10296.4 ms |
| pdf | 68 | 100.0% | 100.0% | 95.9% | 100.0% | 100.0% | 1.5% | 10073.3 ms |
| png | 54 | 100.0% | 100.0% | 96.9% | 100.0% | 100.0% | 7.4% | 8788.4 ms |

## By layout

| Layout | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| classic | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.1% | 10903.6 ms |
| invoice | 60 | 100.0% | 100.0% | 92.6% | 100.0% | 100.0% | 3.3% | 10900.1 ms |
| thermal | 58 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.5% | 7671.4 ms |

## By currency

| Currency | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| AUD | 14 | 100.0% | 100.0% | 96.2% | 100.0% | 100.0% | 7.1% | 8239.8 ms |
| CAD | 29 | 100.0% | 100.0% | 96.5% | 100.0% | 100.0% | 6.9% | 8324.9 ms |
| EUR | 15 | 100.0% | 100.0% | 98.0% | 100.0% | 100.0% | 0.0% | 11064.3 ms |
| GBP | 17 | 100.0% | 100.0% | 96.4% | 100.0% | 100.0% | 0.0% | 10534.6 ms |
| INR | 15 | 100.0% | 100.0% | 96.9% | 100.0% | 100.0% | 13.3% | 10573.7 ms |
| JPY | 19 | 100.0% | 100.0% | 97.6% | 100.0% | 100.0% | 0.0% | 6790.3 ms |
| PKR | 23 | 100.0% | 100.0% | 97.0% | 100.0% | 100.0% | 0.0% | 10363.1 ms |
| USD | 18 | 100.0% | 100.0% | 97.9% | 100.0% | 100.0% | 0.0% | 12225.3 ms |

## By scenario tag

| Scenario tag | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| discount | 24 | 100.0% | 100.0% | 96.8% | 100.0% | 100.0% | 8.3% | 8533.6 ms |
| multi_page | 18 | 100.0% | 100.0% | 92.3% | 100.0% | 100.0% | 5.6% | 13348.8 ms |
| multi_tax | 24 | 100.0% | 100.0% | 96.8% | 100.0% | 100.0% | 12.5% | 10368.3 ms |
| no_tax_printed | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 5699.7 ms |
| photo_like | 21 | 100.0% | 100.0% | 98.2% | 100.0% | 100.0% | 0.0% | 10913.9 ms |
| prompt_injection | 5 | 100.0% | 100.0% | 93.8% | 100.0% | 100.0% | 0.0% | 9509.6 ms |
| qty_not_printed | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.2% | 7583.3 ms |
| tax_inclusive | 32 | 100.0% | 100.0% | 97.1% | 100.0% | 100.0% | 0.0% | 10782.9 ms |
| total_mismatch | 5 | 100.0% | 100.0% | 96.9% | 100.0% | 100.0% | 100.0% | 7695.9 ms |

## Errors

None.

## Documents with core-field differences (0)

None.

_Synthetic, fictional documents. Results describe this dataset and model configuration only._
