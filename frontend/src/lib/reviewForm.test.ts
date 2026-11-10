import { describe, expect, it } from 'vitest';
import { extracted } from '@/test/fixtures';
import { changedFields, toForm } from './reviewForm';

describe('review form helpers', () => {
  it('reports no changes for an untouched form', () => {
    const doc = extracted();
    const { values, items } = toForm(doc);
    expect(changedFields(doc, values, items)).toEqual({});
  });

  it('reports only edited fields, in API form', () => {
    const doc = extracted();
    const { values, items } = toForm(doc);
    const result = changedFields(
      doc,
      { ...values, total_amount: '25.86', merchant_address: '  ', currency: 'cad' },
      items,
    );
    expect(result).toEqual({ total_amount: '25.86', merchant_address: null });
  });

  it('treats numerically equal amounts as unchanged', () => {
    const doc = extracted();
    const { values, items } = toForm(doc);
    expect(changedFields(doc, { ...values, subtotal: '23.2' }, items)).toEqual({});
  });

  it('sends the full line item list when any item changes', () => {
    const doc = extracted();
    const { values, items } = toForm(doc);
    const edited = [
      ...items,
      { description: 'Muffin', quantity: '1', unit_price: '3.75', total_price: '3.75' },
    ];
    expect(changedFields(doc, values, edited).line_items).toEqual([
      { description: 'Latte', quantity: '2', unit_price: '5.25', total_price: '10.50' },
      { description: 'Muffin', quantity: '1', unit_price: '3.75', total_price: '3.75' },
    ]);
  });
});
