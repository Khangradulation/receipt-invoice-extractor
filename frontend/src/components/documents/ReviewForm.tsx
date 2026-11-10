import { Plus, Trash2 } from 'lucide-react';
import { Button, SelectField, TextField } from '@/components/ui';
import { FIELD_LABELS } from '@/lib/format';
import { CATEGORIES, PAYMENT_METHODS, type FormLineItem } from '@/lib/reviewForm';

interface Props {
  values: Record<string, string>;
  items: FormLineItem[];
  failed: string[];
  disabled: boolean;
  onChange: (field: string, value: string) => void;
  onItemsChange: (items: FormLineItem[]) => void;
}

export function ReviewForm({ values, items, failed, disabled, onChange, onItemsChange }: Props) {
  const text = (field: string, type = 'text', extra: Record<string, unknown> = {}) => (
    <TextField
      label={FIELD_LABELS[field] ?? field}
      type={type}
      value={values[field] ?? ''}
      invalid={failed.includes(field)}
      disabled={disabled}
      onChange={(e) => onChange(field, e.target.value)}
      {...extra}
    />
  );
  const money = (field: string) =>
    text(field, 'text', { inputMode: 'decimal', placeholder: '0.00' });
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Document type"
          value={values.document_type ?? ''}
          invalid={failed.includes('document_type')}
          disabled={disabled}
          onChange={(e) => onChange('document_type', e.target.value)}
        >
          <option value="">—</option>
          <option value="receipt">Receipt</option>
          <option value="invoice">Invoice</option>
          <option value="other">Other</option>
        </SelectField>
        {text('merchant_name')}
        <div className="sm:col-span-2">{text('merchant_address')}</div>
        {text('document_number')}
        {text('currency', 'text', { maxLength: 3, placeholder: 'USD', className: 'uppercase' })}
        {text('document_date', 'date')}
        {text('due_date', 'date')}
        {money('subtotal')}
        {money('tax_amount')}
        {money('discount_amount')}
        {money('total_amount')}
        <SelectField
          label="Payment method"
          value={values.payment_method ?? ''}
          disabled={disabled}
          onChange={(e) => onChange('payment_method', e.target.value)}
        >
          <option value="">—</option>
          {PAYMENT_METHODS.map((m) => (
            <option key={m} value={m}>
              {m.replace(/_/g, ' ')}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Category"
          value={values.expense_category ?? ''}
          disabled={disabled}
          onChange={(e) => onChange('expense_category', e.target.value)}
        >
          <option value="">—</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace(/_/g, ' ')}
            </option>
          ))}
        </SelectField>
      </div>

      <fieldset disabled={disabled}>
        <legend
          className={
            failed.includes('line_items')
              ? 'text-sm font-medium text-red-700'
              : 'text-sm font-medium text-slate-700'
          }
        >
          Line items
        </legend>
        <div className="mt-2 space-y-2">
          {items.map((item, i) => (
            <div key={i} className="grid grid-cols-12 items-end gap-2">
              {(['description', 'quantity', 'unit_price', 'total_price'] as const).map((k) => (
                <div key={k} className={k === 'description' ? 'col-span-5' : 'col-span-2'}>
                  <TextField
                    label={
                      k === 'description'
                        ? `Item ${i + 1}`
                        : k === 'unit_price'
                          ? 'Unit price'
                          : k === 'total_price'
                            ? 'Line total'
                            : 'Qty'
                    }
                    value={item[k]}
                    inputMode={k === 'description' ? undefined : 'decimal'}
                    onChange={(e) =>
                      onItemsChange(
                        items.map((it, j) => (j === i ? { ...it, [k]: e.target.value } : it)),
                      )
                    }
                  />
                </div>
              ))}
              <div className="col-span-1 pb-1">
                <button
                  type="button"
                  aria-label={`Remove item ${i + 1}`}
                  className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                  onClick={() => onItemsChange(items.filter((_, j) => j !== i))}
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          ))}
          <Button
            variant="secondary"
            onClick={() =>
              onItemsChange([
                ...items,
                { description: '', quantity: '', unit_price: '', total_price: '' },
              ])
            }
          >
            <Plus className="size-4" aria-hidden="true" /> Add line item
          </Button>
        </div>
      </fieldset>
    </div>
  );
}
