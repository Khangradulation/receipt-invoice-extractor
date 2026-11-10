/**
 * TEST FIXTURES ONLY — never imported by application code.
 * Shapes mirror the API responses (src/lib/types.ts).
 */
import type {
  DocumentDetail,
  DocumentSummary,
  ExtractedDocument,
  ReviewDetail,
  ValidationResult,
} from '@/lib/types';

export function extracted(overrides: Partial<ExtractedDocument> = {}): ExtractedDocument {
  return {
    document_type: 'receipt',
    document_number: 'R-1',
    document_date: '2026-03-14',
    due_date: null,
    currency: 'CAD',
    merchant_name: 'Maple Leaf Cafe',
    merchant_address: '42 Harbour St',
    subtotal: '23.20',
    tax_amount: '3.48',
    discount_amount: null,
    total_amount: '26.68',
    payment_method: 'credit_card',
    line_items: [{ description: 'Latte', quantity: '2', unit_price: '5.25', total_price: '10.50' }],
    expense_category: 'meals',
    missing_fields: ['due_date', 'discount_amount'],
    extraction_notes: null,
    ...overrides,
  };
}

export function validation(overrides: Partial<ValidationResult> = {}): ValidationResult {
  return {
    is_valid: true,
    validation_status: 'VALID',
    validation_errors: [],
    validation_warnings: [],
    failed_fields: [],
    duplicate_status: 'NOT_DUPLICATE',
    duplicate_of: [],
    rules_version: 'r1',
    ...overrides,
  };
}

export const INVALID: ValidationResult = validation({
  is_valid: false,
  validation_status: 'REVIEW_REQUIRED',
  validation_errors: [
    {
      code: 'TOTAL_MISMATCH',
      severity: 'error',
      message:
        'Amounts do not add up: subtotal 22.49 CAD + tax 3.37 CAD = 25.86 CAD, but the total is 28.86 CAD.',
      fields: ['subtotal', 'tax_amount', 'total_amount'],
    },
  ],
  failed_fields: ['subtotal', 'tax_amount', 'total_amount'],
});

export function summary(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    document_id: 'doc1',
    filename: 'receipt_cafe.pdf',
    status: 'VALID',
    content_type: 'application/pdf',
    document_type: 'receipt',
    merchant_name: 'Maple Leaf Cafe',
    document_date: '2026-03-14',
    total_amount: '26.68',
    currency: 'CAD',
    created_at: '2026-11-09T12:00:00Z',
    updated_at: '2026-11-09T12:00:05Z',
    completed_at: '2026-11-09T12:00:05Z',
    error: null,
    ...overrides,
  };
}

export function detail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    ...summary(),
    size_bytes: 53370,
    page_count: 1,
    processing_attempts: 1,
    model_version: 'gemini-3.8-flash',
    uploaded_at: '2026-11-09T12:00:01Z',
    processing_started_at: '2026-11-09T12:00:01Z',
    extracted_at: '2026-11-09T12:00:04Z',
    processing_duration_ms: 5400,
    extraction: extracted(),
    corrected: null,
    validation: validation(),
    history: [
      { status: 'UPLOADED', at: '2026-11-09T12:00:01Z', detail: null },
      { status: 'VALID', at: '2026-11-09T12:00:05Z', detail: null },
    ],
    ...overrides,
  };
}

export function reviewDetail(overrides: Partial<ReviewDetail> = {}): ReviewDetail {
  const original = extracted({
    merchant_name: 'Harbour Books',
    subtotal: '22.49',
    tax_amount: '3.37',
    total_amount: '28.86',
  });
  return {
    document: detail({
      document_id: 'rev1',
      filename: 'mismatch.pdf',
      status: 'REVIEW_REQUIRED',
      extraction: original,
      validation: INVALID,
    }),
    original,
    current: original,
    validation: INVALID,
    failed_fields: INVALID.failed_fields,
    corrections: [],
    duplicate_acknowledged: false,
    can_approve: false,
    ...overrides,
  };
}
