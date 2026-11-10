import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';
import { reviewDetail, summary, validation } from '@/test/fixtures';
import { renderApp } from '@/test/render';

function mockFile() {
  vi.spyOn(api, 'documentFile').mockResolvedValue({
    url: 'https://storage.test/get',
    expires_at: '',
    content_type: 'application/pdf',
  });
}

describe('review queue', () => {
  it('lists documents needing review and links to the editor', async () => {
    vi.spyOn(api, 'reviewQueue').mockResolvedValue({
      items: [
        summary({ document_id: 'rev1', filename: 'mismatch.pdf', status: 'REVIEW_REQUIRED' }),
      ],
      next_cursor: null,
    });
    renderApp('/review');
    expect(await screen.findByRole('link', { name: 'mismatch.pdf' })).toHaveAttribute(
      'href',
      '/review/rev1',
    );
  });

  it('shows an empty state', async () => {
    vi.spyOn(api, 'reviewQueue').mockResolvedValue({ items: [], next_cursor: null });
    renderApp('/review');
    expect(await screen.findByText('Nothing to review')).toBeInTheDocument();
  });
});

describe('review editor', () => {
  it('highlights failed fields and blocks approval until fixed', async () => {
    mockFile();
    vi.spyOn(api, 'review').mockResolvedValue(reviewDetail());
    renderApp('/review/rev1');
    const total = await screen.findByLabelText('Total');
    expect(total).toHaveValue('28.86');
    expect(total).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Merchant')).not.toHaveAttribute('aria-invalid');
    expect(screen.getByText(/Amounts do not add up/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save corrections' })).toBeDisabled();
  });

  it('saves only changed fields, then approves', async () => {
    mockFile();
    const fixed = reviewDetail({
      current: { ...reviewDetail().original!, total_amount: '25.86' },
      validation: validation(),
      failed_fields: [],
      can_approve: true,
      corrections: [
        {
          review_id: 'rev1:c1',
          field_name: 'total_amount',
          original_value: '28.86',
          previous_value: '28.86',
          corrected_value: '25.86',
          reviewer_id: 'user_A',
          reviewed_at: '2026-11-09T12:05:00Z',
        },
      ],
    });
    vi.spyOn(api, 'review').mockResolvedValue(reviewDetail());
    const save = vi.spyOn(api, 'saveCorrections').mockResolvedValue(fixed);
    const approve = vi
      .spyOn(api, 'approve')
      .mockResolvedValue({ ...fixed, document: { ...fixed.document, status: 'APPROVED' } });
    vi.spyOn(api, 'reviewQueue').mockResolvedValue({ items: [], next_cursor: null });

    renderApp('/review/rev1');
    const total = await screen.findByLabelText('Total');
    await userEvent.clear(total);
    await userEvent.type(total, '25.86');
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled(); // unsaved changes
    await userEvent.click(screen.getByRole('button', { name: 'Save corrections' }));

    expect(save).toHaveBeenCalledWith('rev1', { total_amount: '25.86' }, false);
    expect(
      await screen.findByText('Saved. All checks pass — you can approve.'),
    ).toBeInTheDocument();
    expect(screen.getByText('All required checks passed.')).toBeInTheDocument();
    expect(screen.getByText(/AI value: 28.86/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(approve).toHaveBeenCalledWith('rev1'));
    expect(await screen.findByRole('heading', { name: 'Review queue' })).toBeInTheDocument();
  });

  it('shows the server reason when approval is refused', async () => {
    mockFile();
    vi.spyOn(api, 'review').mockResolvedValue(
      reviewDetail({ can_approve: true, validation: validation(), failed_fields: [] }),
    );
    vi.spyOn(api, 'approve').mockRejectedValue(
      new ApiError(409, 'conflict', 'Fix the remaining validation errors before approving.'),
    );
    renderApp('/review/rev1');
    await userEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    expect(
      await screen.findByText('Fix the remaining validation errors before approving.'),
    ).toBeInTheDocument();
  });

  it('requires a reason to reject', async () => {
    mockFile();
    vi.spyOn(api, 'review').mockResolvedValue(reviewDetail());
    const reject = vi.spyOn(api, 'reject').mockResolvedValue(reviewDetail());
    vi.spyOn(api, 'reviewQueue').mockResolvedValue({ items: [], next_cursor: null });
    renderApp('/review/rev1');
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    const dialog = screen.getByRole('dialog', { name: 'Reject document' });
    const confirm = screen.getAllByRole('button', { name: 'Reject' }).at(-1)!;
    expect(dialog).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Reason'), 'Personal expense');
    await userEvent.click(confirm);
    await waitFor(() => expect(reject).toHaveBeenCalledWith('rev1', 'Personal expense'));
  });
});

describe('review conflicts', () => {
  it('reloads the latest version when the document changed elsewhere', async () => {
    mockFile();
    const review = vi.spyOn(api, 'review').mockResolvedValue(reviewDetail());
    vi.spyOn(api, 'saveCorrections').mockRejectedValue(
      new ApiError(
        409,
        'conflict',
        'This document was changed in another window or request. Reload to see the latest version.',
      ),
    );
    renderApp('/review/rev1');
    const total = await screen.findByLabelText('Total');
    await userEvent.clear(total);
    await userEvent.type(total, '25.86');
    await userEvent.click(screen.getByRole('button', { name: 'Save corrections' }));
    expect(await screen.findByText(/changed in another window/)).toBeInTheDocument();
    await waitFor(() => expect(review).toHaveBeenCalledTimes(2)); // refetched
  });
});
