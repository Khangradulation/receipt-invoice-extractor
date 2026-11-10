import { FIELD_LABELS, formatDate, formatMoney, humanize } from '@/lib/format';
import { cn } from '@/lib/cn';
import type { ExtractedDocument } from '@/lib/types';

const MONEY = ['subtotal', 'tax_amount', 'discount_amount', 'total_amount'] as const;
const ROWS: (keyof ExtractedDocument)[] = [
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
];

function display(doc: ExtractedDocument, field: keyof ExtractedDocument): string {
  const value = doc[field];
  if (value === null || value === undefined || value === '') return '—';
  if ((MONEY as readonly string[]).includes(field))
    return formatMoney(value as string, doc.currency);
  if (field === 'document_date' || field === 'due_date') return formatDate(value as string);
  if (field === 'document_type' || field === 'payment_method' || field === 'expense_category') {
    return humanize(value as string);
  }
  return String(value);
}

export function ExtractedFields({
  doc,
  failedFields = [],
}: {
  doc: ExtractedDocument;
  failedFields?: string[];
}) {
  return (
    <div>
      <dl className="divide-y divide-slate-100 text-sm">
        {ROWS.map((field) => {
          const failed = failedFields.includes(field);
          return (
            <div
              key={field}
              className={cn('grid grid-cols-3 gap-4 px-1 py-2', failed && 'rounded bg-red-50')}
            >
              <dt className={cn('text-slate-500', failed && 'font-medium text-red-700')}>
                {FIELD_LABELS[field]}
              </dt>
              <dd className="col-span-2 break-words text-slate-900">{display(doc, field)}</dd>
            </div>
          );
        })}
      </dl>
      <LineItemsTable doc={doc} />
      {doc.extraction_notes && (
        <p className="mt-3 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <span className="font-medium">AI notes:</span> {doc.extraction_notes}
        </p>
      )}
    </div>
  );
}

export function LineItemsTable({ doc }: { doc: ExtractedDocument }) {
  if (!doc.line_items.length) {
    return <p className="mt-4 text-sm text-slate-500">No line items were found.</p>;
  }
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full text-sm">
        <caption className="mb-2 text-left text-sm font-medium text-slate-700">Line items</caption>
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
            <th className="py-2 pr-3 font-medium">Description</th>
            <th className="py-2 pr-3 text-right font-medium">Qty</th>
            <th className="py-2 pr-3 text-right font-medium">Unit price</th>
            <th className="py-2 text-right font-medium">Total</th>
          </tr>
        </thead>
        <tbody>
          {doc.line_items.map((item, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-2 pr-3">{item.description ?? '—'}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{item.quantity ?? '—'}</td>
              <td className="py-2 pr-3 text-right tabular-nums">
                {formatMoney(item.unit_price, doc.currency)}
              </td>
              <td className="py-2 text-right tabular-nums">
                {formatMoney(item.total_price, doc.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
