# Extraction benchmark — invoices-60-prompt-20261111

- **Date:** 2026-11-11T07:13:25+00:00 (finished 2026-11-11T07:18:32+00:00)
- **Model:** `gemini-3.8-flash` (reported version `gemini-3.8-flash`), location `global`
- **Prompt version:** `2026-11-11.1` · **Validation rules:** `2026-11-09.1`
- **Dataset:** 150 synthetic documents, seed 20261110 (`evaluation/synthetic/generate.py`)
- **Documents:** 60 · succeeded 60 · errors 0
- **Command:** `uv run python ../evaluation/run_benchmark.py --document-type invoice --run-id invoices-60-prompt-20261111 --to-bigquery`

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
| Latency mean / p50 / p95 | 20159.9 / 10098.7 / 66341.4 ms |
| Tokens total / mean per document | 244,862 / 4081.0 |

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
| invoice | 60 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.3% | 20159.9 ms |

## By format

| Format | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| pdf | 38 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 2.6% | 17960.5 ms |
| png | 22 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.5% | 23959.0 ms |

## By layout

| Layout | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| invoice | 60 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3.3% | 20159.9 ms |

## By currency

| Currency | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| AUD | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 14.3% | 14861.2 ms |
| CAD | 13 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 28550.3 ms |
| EUR | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 22241.3 ms |
| GBP | 8 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 20576.9 ms |
| INR | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 14.3% | 25092.1 ms |
| JPY | 6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 18299.0 ms |
| PKR | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 14406.4 ms |
| USD | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 10265.9 ms |

## By scenario tag

| Scenario tag | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |
|---|---|---|---|---|---|---|---|---|
| discount | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 10.0% | 17619.2 ms |
| multi_page | 18 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 5.6% | 19743.4 ms |
| multi_tax | 11 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 9.1% | 28299.1 ms |
| photo_like | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 28858.7 ms |
| prompt_injection | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 25633.9 ms |
| tax_inclusive | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 21131.7 ms |
| total_mismatch | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 15978.3 ms |

## Errors

None.

## Documents with core-field differences (0)

None.

_Synthetic, fictional documents. Results describe this dataset and model configuration only._
