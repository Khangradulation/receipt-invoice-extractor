import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import type { AnalyticsOverview } from '@/lib/types';
import { summary } from '@/test/fixtures';
import { renderApp } from '@/test/render';

const OVERVIEW: AnalyticsOverview = {
  start_date: '2025-11-09',
  end_date: '2026-11-09',
  total_spending: [
    { currency: 'CAD', total_amount: '52.54', total_tax: '6.85', transaction_count: 2 },
  ],
  average_transaction_value: [
    {
      currency: 'CAD',
      average_amount: '26.27',
      min_amount: '25.86',
      max_amount: '26.68',
      transaction_count: 2,
    },
  ],
  document_type_counts: [{ document_type: 'receipt', processed_count: 3, approved_count: 2 }],
  processing_success_rate: { processed_documents: 3, success_rate: 1 },
  manual_review_rate: { review_required: 1, review_rate: 0.5 },
};

describe('overview dashboard', () => {
  it('renders spending, success rate, review count and recent documents', async () => {
    vi.spyOn(api, 'overview').mockResolvedValue(OVERVIEW);
    vi.spyOn(api, 'documents').mockResolvedValue({ items: [summary()], next_cursor: null });
    vi.spyOn(api, 'reviewQueue').mockResolvedValue({
      items: [summary({ status: 'REVIEW_REQUIRED' })],
      next_cursor: null,
    });
    renderApp('/');
    expect(await screen.findByText('CA$52.54')).toBeInTheDocument();
    expect(screen.getByText('100.0%')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'receipt_cafe.pdf' })).toBeInTheDocument();
    expect(screen.getByText('Needs review').nextSibling).toHaveTextContent('1');
  });
});

describe('analytics page', () => {
  it('renders cards, merchants and document type counts from the API', async () => {
    vi.spyOn(api, 'overview').mockResolvedValue(OVERVIEW);
    vi.spyOn(api, 'monthlySpending').mockResolvedValue({
      start_date: '',
      end_date: '',
      rows: [{ month: '2026-03-01', currency: 'CAD', total_amount: '52.54', transaction_count: 2 }],
    });
    vi.spyOn(api, 'categories').mockResolvedValue({
      start_date: '',
      end_date: '',
      rows: [
        { expense_category: 'meals', currency: 'CAD', total_amount: '26.68', transaction_count: 1 },
      ],
    });
    const merchants = vi.spyOn(api, 'merchants').mockResolvedValue({
      start_date: '',
      end_date: '',
      rows: [
        {
          merchant_name: 'Maple Leaf Cafe',
          currency: 'CAD',
          total_amount: '26.68',
          transaction_count: 1,
        },
      ],
    });
    renderApp('/analytics');
    expect(await screen.findByText('CA$52.54')).toBeInTheDocument();
    expect(screen.getByText('CA$26.27')).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
    expect(await screen.findByText('Maple Leaf Cafe')).toBeInTheDocument();
    expect(screen.getByText('Receipts')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Monthly spending chart' })).toBeInTheDocument();
    expect(merchants).toHaveBeenCalledWith(
      {
        start_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        end_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      },
      10,
    );
  });

  it('shows empty states when there is no data', async () => {
    vi.spyOn(api, 'overview').mockResolvedValue({
      ...OVERVIEW,
      total_spending: [],
      average_transaction_value: [],
      document_type_counts: [],
    });
    vi.spyOn(api, 'monthlySpending').mockResolvedValue({ start_date: '', end_date: '', rows: [] });
    vi.spyOn(api, 'categories').mockResolvedValue({ start_date: '', end_date: '', rows: [] });
    vi.spyOn(api, 'merchants').mockResolvedValue({ start_date: '', end_date: '', rows: [] });
    renderApp('/analytics');
    expect(await screen.findByText('No spending in this period')).toBeInTheDocument();
    expect(screen.getByText('No documents processed')).toBeInTheDocument();
  });
});
