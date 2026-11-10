import type { ExtractedDocument, LineItem } from '@/lib/types';

export const CATEGORIES = [
  'meals',
  'groceries',
  'travel',
  'lodging',
  'transportation',
  'fuel',
  'office_supplies',
  'software',
  'equipment',
  'utilities',
  'telecommunications',
  'professional_services',
  'rent',
  'insurance',
  'shipping',
  'entertainment',
  'healthcare',
  'other',
];
export const PAYMENT_METHODS = [
  'cash',
  'credit_card',
  'debit_card',
  'bank_transfer',
  'check',
  'mobile_payment',
  'other',
];

/** Editable values: everything is a string in the form ('' = empty / null). */
export type FormValues = Record<string, string> & { line_items?: never };
export type FormLineItem = Record<keyof LineItem, string>;

export const SCALAR_FIELDS = [
  'document_type',
  'merchant_name',
  'merchant_address',
  'document_number',
  'document_date',
  'due_date',
  'currency',
  'subtotal',
  'tax_amount',
  'discount_amount',
  'total_amount',
  'payment_method',
  'expense_category',
] as const;

export function toForm(doc: ExtractedDocument): {
  values: Record<string, string>;
  items: FormLineItem[];
} {
  const values: Record<string, string> = {};
  for (const f of SCALAR_FIELDS) values[f] = (doc[f] as string | null) ?? '';
  const items = doc.line_items.map((li) => ({
    description: li.description ?? '',
    quantity: li.quantity ?? '',
    unit_price: li.unit_price ?? '',
    total_price: li.total_price ?? '',
  }));
  return { values, items };
}

const nullIfEmpty = (v: string) => (v.trim() === '' ? null : v.trim());

/** Only the fields that differ from `base`, in API form (null for cleared values). */
export function changedFields(
  base: ExtractedDocument,
  values: Record<string, string>,
  items: FormLineItem[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of SCALAR_FIELDS) {
    const raw = nullIfEmpty(values[f] ?? '');
    const next = f === 'currency' && raw ? raw.toUpperCase() : raw;
    const prev = (base[f] as string | null) ?? null;
    const same =
      next === prev ||
      (next !== null &&
        prev !== null &&
        Number.isFinite(Number(next)) &&
        ['subtotal', 'tax_amount', 'discount_amount', 'total_amount'].includes(f) &&
        Number(next) === Number(prev));
    if (!same) out[f] = next;
  }
  const nextItems = items.map((i) => ({
    description: nullIfEmpty(i.description),
    quantity: nullIfEmpty(i.quantity),
    unit_price: nullIfEmpty(i.unit_price),
    total_price: nullIfEmpty(i.total_price),
  }));
  if (JSON.stringify(nextItems) !== JSON.stringify(base.line_items)) out.line_items = nextItems;
  return out;
}
