import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';
import { detail, summary, validation } from '@/test/fixtures';
import { renderApp } from '@/test/render';

describe('documents list', () => {
  it('lists documents and loads more pages', async () => {
    const docs = vi
      .spyOn(api, 'documents')
      .mockResolvedValueOnce({ items: [summary()], next_cursor: 'c1' })
      .mockResolvedValueOnce({
        items: [summary({ document_id: 'doc2', filename: 'older.pdf', status: 'FAILED' })],
        next_cursor: null,
      });
    renderApp('/documents');
    expect(await screen.findByRole('link', { name: 'receipt_cafe.pdf' })).toHaveAttribute(
      'href',
      '/documents/doc1',
    );
    expect(screen.getByText('CA$26.68')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }));
    expect(await screen.findByRole('link', { name: 'older.pdf' })).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getByText('Failed')).toBeInTheDocument();
    expect(docs).toHaveBeenLastCalledWith({ status: undefined, limit: 25, cursor: 'c1' });
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('filters by status', async () => {
    const docs = vi.spyOn(api, 'documents').mockResolvedValue({ items: [], next_cursor: null });
    renderApp('/documents');
    await userEvent.selectOptions(await screen.findByLabelText('Status'), 'REVIEW_REQUIRED');
    expect(await screen.findByText('No documents with this status')).toBeInTheDocument();
    expect(docs).toHaveBeenLastCalledWith({ status: ['REVIEW_REQUIRED'], limit: 25, cursor: null });
  });

  it('shows an empty state with an upload link', async () => {
    vi.spyOn(api, 'documents').mockResolvedValue({ items: [], next_cursor: null });
    renderApp('/documents');
    expect(await screen.findByText('No documents yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload documents' })).toHaveAttribute(
      'href',
      '/upload',
    );
  });

  it('shows errors with a retry', async () => {
    vi.spyOn(api, 'documents').mockRejectedValue(
      new ApiError(503, 'service_unavailable', 'Try again later.'),
    );
    renderApp('/documents');
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again later.');
  });
});

describe('document details', () => {
  it('shows the original file, extracted data, validation and history', async () => {
    vi.spyOn(api, 'document').mockResolvedValue(
      detail({
        validation: validation({
          validation_warnings: [
            {
              code: 'MISSING_OPTIONAL_FIELD',
              severity: 'warning',
              message: 'Due date was not found.',
              fields: ['due_date'],
            },
          ],
        }),
      }),
    );
    vi.spyOn(api, 'documentFile').mockResolvedValue({
      url: 'https://storage.test/get',
      expires_at: '',
      content_type: 'application/pdf',
    });
    renderApp('/documents/doc1');
    expect(await screen.findByRole('heading', { name: 'receipt_cafe.pdf' })).toBeInTheDocument();
    expect(await screen.findByTitle('Document receipt_cafe.pdf')).toHaveAttribute(
      'src',
      'https://storage.test/get',
    );
    const fields = screen.getByText('Merchant').closest('dl')!;
    expect(within(fields).getByText('Maple Leaf Cafe')).toBeInTheDocument();
    expect(within(fields).getByText('CA$26.68')).toBeInTheDocument();
    expect(screen.getByText('All required checks passed.')).toBeInTheDocument();
    expect(screen.getByText('1 warning')).toBeInTheDocument();
    expect(screen.getByText('Latte')).toBeInTheDocument();
    expect(screen.getByText('Uploaded')).toBeInTheDocument();
  });

  it('shows not found for missing or foreign documents', async () => {
    vi.spyOn(api, 'document').mockRejectedValue(
      new ApiError(404, 'not_found', 'Document not found.'),
    );
    renderApp('/documents/nope');
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('explains processing failures', async () => {
    vi.spyOn(api, 'document').mockResolvedValue(
      detail({
        status: 'FAILED',
        extraction: null,
        validation: null,
        error: {
          code: 'integrity_check_failed',
          message: 'Uploaded file is 10 bytes; 20 bytes were declared.',
        },
      }),
    );
    vi.spyOn(api, 'documentFile').mockResolvedValue({
      url: 'u',
      expires_at: '',
      content_type: 'application/pdf',
    });
    renderApp('/documents/doc1');
    expect(await screen.findByText('Processing failed')).toBeInTheDocument();
    expect(screen.getByText(/20 bytes were declared/)).toBeInTheDocument();
  });
});
