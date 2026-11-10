import type { BadgeTone } from '@/components/ui';
import type { DocumentStatus } from './types';

export function formatMoney(
  amount: string | number | null | undefined,
  currency?: string | null,
): string {
  if (amount === null || amount === undefined || amount === '') return '—';
  const value = typeof amount === 'number' ? amount : Number(amount);
  if (!Number.isFinite(value)) return String(amount);
  if (!currency) return value.toLocaleString(undefined, { minimumFractionDigits: 2 });
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  // Plain ISO dates (YYYY-MM-DD) are calendar dates: don't shift them through a time zone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split('-').map(Number);
    return new Date(y!, m! - 1, d!).toLocaleDateString(undefined, { dateStyle: 'medium' });
  }
  return new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatPercent(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '—';
}

export function humanize(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export const STATUS_INFO: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  AWAITING_UPLOAD: { label: 'Awaiting upload', tone: 'neutral' },
  UPLOADED: { label: 'Uploaded', tone: 'info' },
  PROCESSING: { label: 'Processing', tone: 'info' },
  EXTRACTED: { label: 'Extracted', tone: 'info' },
  VALIDATING: { label: 'Validating', tone: 'info' },
  VALID: { label: 'Valid', tone: 'success' },
  REVIEW_REQUIRED: { label: 'Needs review', tone: 'warning' },
  APPROVED: { label: 'Approved', tone: 'success' },
  REJECTED: { label: 'Rejected', tone: 'neutral' },
  DUPLICATE: { label: 'Duplicate', tone: 'neutral' },
  FAILED: { label: 'Failed', tone: 'danger' },
};

export const FIELD_LABELS: Record<string, string> = {
  document_type: 'Document type',
  document_number: 'Document number',
  document_date: 'Date',
  due_date: 'Due date',
  currency: 'Currency',
  merchant_name: 'Merchant',
  merchant_address: 'Merchant address',
  subtotal: 'Subtotal',
  tax_amount: 'Tax',
  discount_amount: 'Discount',
  total_amount: 'Total',
  payment_method: 'Payment method',
  expense_category: 'Category',
  line_items: 'Line items',
};
