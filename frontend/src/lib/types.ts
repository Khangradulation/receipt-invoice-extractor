/** Types mirroring the API response models (backend/api/src/receipt_api/schemas.py). */

export type DocumentStatus =
  | 'AWAITING_UPLOAD'
  | 'UPLOADED'
  | 'PROCESSING'
  | 'EXTRACTED'
  | 'VALIDATING'
  | 'VALID'
  | 'REVIEW_REQUIRED'
  | 'APPROVED'
  | 'REJECTED'
  | 'DUPLICATE'
  | 'FAILED';

export const FINAL_STATUSES: DocumentStatus[] = [
  'VALID',
  'REVIEW_REQUIRED',
  'APPROVED',
  'REJECTED',
  'DUPLICATE',
  'FAILED',
];

export interface ErrorInfo {
  code: string;
  message: string;
}

export interface LineItem {
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  total_price: string | null;
}

export interface ExtractedDocument {
  document_type: string | null;
  document_number: string | null;
  document_date: string | null;
  due_date: string | null;
  currency: string | null;
  merchant_name: string | null;
  merchant_address: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  discount_amount: string | null;
  total_amount: string | null;
  payment_method: string | null;
  line_items: LineItem[];
  expense_category: string | null;
  missing_fields: string[];
  extraction_notes: string | null;
}

export interface ValidationIssue {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  fields: string[];
}

export interface ValidationResult {
  is_valid: boolean;
  validation_status: 'VALID' | 'REVIEW_REQUIRED' | 'PROCESSING_FAILED' | 'DUPLICATE';
  validation_errors: ValidationIssue[];
  validation_warnings: ValidationIssue[];
  failed_fields: string[];
  duplicate_status: 'NOT_DUPLICATE' | 'POSSIBLE_DUPLICATE' | 'DUPLICATE';
  duplicate_of: string[];
  rules_version: string;
}

export interface DocumentSummary {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  content_type: string;
  document_type: string | null;
  merchant_name: string | null;
  document_date: string | null;
  total_amount: string | null;
  currency: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error: ErrorInfo | null;
}

export interface DocumentPage {
  items: DocumentSummary[];
  next_cursor: string | null;
}

export interface HistoryEntry {
  status: string;
  at: string;
  detail: string | null;
}

export interface ReviewSummary {
  decision: {
    action: 'APPROVED' | 'REJECTED';
    by: string;
    at: string;
    reason: string | null;
  } | null;
  corrections: Correction[];
}

export interface DocumentDetail extends DocumentSummary {
  size_bytes: number;
  page_count: number | null;
  processing_attempts: number;
  model_version: string | null;
  uploaded_at: string | null;
  processing_started_at: string | null;
  extracted_at: string | null;
  processing_duration_ms: number | null;
  extraction: ExtractedDocument | null;
  corrected: ExtractedDocument | null;
  validation: ValidationResult | null;
  history: HistoryEntry[];
  review: ReviewSummary | null;
}

export interface DocumentStatusResponse {
  document_id: string;
  status: DocumentStatus;
  processing_attempts: number;
  updated_at: string;
  completed_at: string | null;
  error: ErrorInfo | null;
}

export interface UploadUrlResponse {
  document_id: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_at: string;
  status: DocumentStatus;
}

export interface FileUrlResponse {
  url: string;
  expires_at: string;
  content_type: string;
}

export interface Correction {
  review_id: string;
  field_name: string;
  original_value: string | null;
  previous_value: string | null;
  corrected_value: string | null;
  reviewer_id: string;
  reviewed_at: string;
}

export interface ReviewDetail {
  document: DocumentDetail;
  original: ExtractedDocument | null;
  current: ExtractedDocument | null;
  validation: ValidationResult | null;
  failed_fields: string[];
  corrections: Correction[];
  duplicate_acknowledged: boolean;
  can_approve: boolean;
}

export type Row = Record<string, string | number | boolean | null>;

export interface AnalyticsOverview {
  start_date: string;
  end_date: string;
  total_spending: Row[];
  average_transaction_value: Row[];
  document_type_counts: Row[];
  processing_success_rate: Row;
  manual_review_rate: Row;
}

export interface AnalyticsRows {
  start_date: string;
  end_date: string;
  rows: Row[];
}

export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  environment: string;
  timestamp: string;
}
