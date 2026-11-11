# Extraction evaluation

A reproducible benchmark that measures how accurately Gemini extracts receipts and invoices,
using **synthetic, fictional** documents with ground-truth labels. No real financial data is used.

```bash
make dataset                                   # 150 documents + ground truth (free, about 3 s)
make evaluate ARGS="--limit 5"                 # smoke test (billable, under a cent)
make evaluate                                  # full run (billable, about $0.25–$1)
make evaluate ARGS="--run-id <id>"             # resume an interrupted run
make evaluate ARGS="--to-bigquery"             # also log per-document metrics to BigQuery
make evaluate ARGS="--model gemini-3.7-flash"  # compare another model
make evaluate ARGS="--document-type invoice"   # only receipts or only invoices
```

Each run writes `evaluation/reports/<run_id>/`:
- `results.jsonl`: per document, the prediction, metadata, validation outcome and field scores;
- `report.json`: the aggregate metrics;
- `report.md`: the human-readable summary (sections described in
  [`evaluation/REPORT_TEMPLATE.md`](../evaluation/REPORT_TEMPLATE.md)).

## Dataset (`evaluation/synthetic/`)

`generate.py` is deterministic for a given `--seed` (default `20261110`). Everything is fictional
(`catalog.py`).

| Dimension | Values |
|-----------|--------|
| Types | 90 receipts, 60 invoices |
| Layouts | thermal (narrow till receipt), classic receipt, invoice |
| Formats | PDF (incl. 18 multi-page invoices), PNG, JPEG |
| Currencies | USD, CAD, EUR, GBP, AUD, INR, JPY (0 decimals), PKR |
| Date styles | ISO, US `MM/DD/YYYY`, European `DD.MM.YYYY`, `Mon DD, YYYY` |
| Scenarios | VAT included in prices, two taxes (GST+PST, CGST+SGST), discounts, no tax printed, quantity not printed, photo-like (rotated, blurred, JPEG artefacts) |
| Traps | 5 prompt-injection documents; 5 documents whose printed total does not add up |

**Ground truth = what is printed.** A printed total that doesn't add up stays as printed (the
validator should send it to review). A value that isn't printed is `null` (returning one counts as
a hallucination).

The built-in font only covers ASCII, so non-dollar currencies are printed as ISO codes (`EUR`,
`GBP`, `PKR`, …). Dollar currencies print `$`, and the address country disambiguates them. The
generator refuses non-ASCII text so a missing glyph can never silently corrupt a document.

## Scoring (`evaluation/benchmark/scoring.py`)

Each of 13 fields is **correct**, **wrong**, **missed** (printed, but returned null) or
**hallucinated** (not printed, but a value was returned).

| Field kind | Comparison |
|------------|------------|
| Money (subtotal, tax, discount, total) | `Decimal`, within one minor unit of the currency (configurable) |
| Text (merchant, address) | Case, punctuation and spacing ignored; `&` = `and`; similarity ≥ 0.92 |
| Document number | Separators and case ignored |
| Dates, currency, type, payment method, category | Exact (currency case-insensitive) |

Line items are matched one to one on description similarity (≥ 0.8) **and** line total within
tolerance, which gives precision, recall and F1. Quantity and unit price are scored on matched
items where printed.

| Metric | Definition |
|--------|------------|
| Exact required-field accuracy | Share of documents with merchant, date, total, currency **and** type all correct |
| Core document accuracy | Required fields plus number, subtotal, tax, discount and due date all correct |
| Fully correct documents | Core fields correct **and** every line item exact |
| Monetary accuracy | Correct money fields / (documents × 4) |
| Hallucination rate | Hallucinated fields / fields that are not printed |
| Review rate | Share sent to REVIEW_REQUIRED by the real validator (`false_review_rate`: among documents that should pass) |
| Prompt-injection resisted | Injection documents with the correct merchant **and** total |

Failed extractions count as missed (they're never excluded). Address, payment method and category
are reported, but excluded from the "core" metrics because they're partly interpretive.

## Results

Reports are committed in `evaluation/reports/<run_id>/report.md`: `full-150-20261110` (all
documents, prompt `2026-11-08.1`), and `invoices-60-prompt-20261111` plus
`receipts-90-prompt-20261111` (all documents across the two runs, prompt `2026-11-11.1`). See the phase log in `IMPLEMENTATION_PLAN.md` for a summary. Results describe this synthetic dataset and model
configuration only. They aren't a claim about real-world documents.

## BigQuery

With `--to-bigquery`, each document becomes an `extraction_metrics` row with `evaluation_run_id`,
`fields_compared` and `fields_correct` (idempotent MERGE). The `extraction_accuracy_evaluation`
analytics query aggregates runs over time, per model and prompt version.
