# Validation engine

`backend/shared/src/receipt_shared/validation/` checks an `ExtractedDocument` and decides what
happens to it. It is pure Python: no Gemini, no Google Cloud, and every threshold comes from
configuration.

```python
from receipt_shared.validation import DocumentValidator

result = DocumentValidator().validate(
    extracted.document,
    document_id="...", user_id="...", file_sha256="...",
    extraction_warnings=extracted.warnings,
    duplicate_index=firestore_index,     # Phase 5; InMemoryDuplicateIndex for tests
)
```

## Outcomes

| `validation_status` | When | Next step (later phases) |
|---|---|---|
| `VALID` | No errors (warnings allowed) | Loaded into BigQuery |
| `REVIEW_REQUIRED` | Any error | Manual review queue |
| `DUPLICATE` | The exact same file (SHA-256) was uploaded earlier by the same user | Kept and shown as a duplicate; never silently deleted |
| `PROCESSING_FAILED` | Extraction failed permanently (`ValidationResult.processing_failed(...)`) | Kept with the reason |

`ValidationResult` also has `is_valid`, `validation_errors`, `validation_warnings`,
`failed_fields` (fields named by errors, for highlighting in the review editor),
`duplicate_status`, `duplicate_of` and `rules_version`. Each issue has a stable `code`, a
`severity`, a plain-English `message` and the `fields` it concerns. Results are JSON-serialisable
and are persisted with the document, so users can see why a record needs review.

> Issue messages can contain amounts. They are shown to the document's owner but must never be
> written to application logs.

## Rules

| Rule | Errors (→ review) | Warnings (record can still be VALID) |
|------|-------------------|--------------------------------------|
| Required fields | `merchant_name`, `document_date`, `total_amount`, `currency` or `document_type` missing | — |
| Optional fields | — | `document_number`, `merchant_address`, `subtotal`, `tax_amount`, `payment_method`, `expense_category`, line items; `due_date` on invoices |
| Document type | Not `receipt` or `invoice` | — |
| Currency | Not in `SUPPORTED_CURRENCIES` | — |
| Dates | More than `FUTURE_DATE_TOLERANCE_DAYS` in the future | Older than `MAX_DOCUMENT_AGE_DAYS`; due date before document date |
| Amounts | Negative subtotal, tax or total | Negative discount (treated as a reduction), zero total, above `MAX_REASONABLE_AMOUNT`, more decimals than the currency uses |
| Totals | No accepted layout matches within tolerance | No subtotal (cannot verify); tax appears included in the subtotal |
| Line items | — | Sum doesn't match the totals; quantity × unit price ≠ line total |
| Invoice number | — | Invoice without a number |
| Duplicates | Possible duplicate (same merchant + number, or same merchant + date + total + currency) | Possible duplicate confirmed by a reviewer |
| Extraction | — | Normalisation warnings from extraction (e.g. an impossible date set to null) |

### Totals

These layouts are accepted, within `max(MONEY_TOLERANCE, currency minor unit)`:

1. `total = subtotal − discount + tax` (standard)
2. `total = subtotal − discount` (prices include tax, as with European VAT, or there is no tax).
   If a positive tax is shown, a warning notes that it appears to be included.
3. `total = subtotal + tax` (the discount is already reflected in the subtotal)

A missing tax is **never assumed to be zero**. If the totals don't reconcile without it, the
document goes to review, with a message saying the difference may be unread tax, a tip or a fee.
The tolerance is never smaller than one minor unit of the currency (1 for JPY, 0.001 for KWD).

### Line items

The sum of line totals is compared with the subtotal, the subtotal minus discount, the total, and
the total minus tax (with or without the discount), within `LINE_ITEM_TOLERANCE`. A mismatch is a
**warning**, not an error: line items are the least reliable part of extraction, and the
document-level totals have already been checked. If any line total is missing, the sum is skipped.

### Duplicates

| Situation | Result |
|-----------|--------|
| Same file bytes as an earlier upload | `DUPLICATE` |
| Same merchant and same document number | `POSSIBLE_DUPLICATE` → review |
| No document number: same merchant, date, total and currency | `POSSIBLE_DUPLICATE` → review |
| Different document numbers | Not a duplicate |
| Another user's document, or a REJECTED/FAILED document | Ignored |
| Uploaded *after* the current document | Ignored; simultaneous uploads are ordered by `(created_at, document_id)` |

Matching is case-, accent- and punctuation-insensitive for merchants (`Café Nero, Ltd.` =
`cafe nero ltd`). For document numbers, separators, case and leading zeros are ignored
(`INV-0042` = `inv 42`). A reviewer can confirm that a possible duplicate is a separate
transaction (`duplicate_acknowledged=True`); an exact-file duplicate can't be overridden that way.

## Configuration

| Variable | Default |
|----------|---------|
| `MONEY_TOLERANCE` | `0.02` |
| `LINE_ITEM_TOLERANCE` | `0.05` |
| `SUPPORTED_CURRENCIES` | `USD,CAD,EUR,GBP,AUD,INR,JPY,CHF,MXN,NZD,SGD` |
| `FUTURE_DATE_TOLERANCE_DAYS` | `1` |
| `MAX_DOCUMENT_AGE_DAYS` | `3650` |
| `MAX_REASONABLE_AMOUNT` | `1000000` |

`RULES_VERSION` is stored with every result; bump it when rules change.
