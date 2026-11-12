# Screenshots

Captured on 2026-11-11 from the real application. No mock-ups or edited images.

- **Backend:** the deployed dev API, worker, Firestore, BigQuery and Gemini.
- **Web app:** run locally (`make web`). Analytics and overview used a local API build containing
  the Phase 16 time-zone fix, against the same dev data.
- **Account:** a throwaway demo account, deleted afterwards along with its documents.
- **Documents:** the synthetic samples from `make samples`, processed by Gemini through the normal
  pipeline. No real receipts are shown.

## Overview

![Overview: totals, processing success, review count and recent documents](overview.jpg)

## Documents

![Documents list with statuses: four valid, one needs review](documents.jpg)

## Document details

![Document details: the uploaded receipt image next to the extracted fields and line items](document-detail.jpg)

This is the benchmark's synthetic **prompt-injection** receipt. It contains a printed instruction
addressed to the AI model. The extraction ignored it: the real merchant and the £5.95 total were
extracted, and validation passed.

## Review

![Review editor: the validation error explains the arithmetic mismatch, with editable fields](review.jpg)

The validator explains why the document needs review (subtotal + tax ≠ total). The original
document panel is blank only because the screenshot browser doesn't render PDFs inside a frame;
in Chrome, Edge, Firefox and Safari it shows the PDF.

## Analytics

![Analytics from BigQuery: spending, success and review rates, monthly and category charts](analytics.jpg)
