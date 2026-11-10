import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import * as upload from '@/lib/upload';
import { renderApp } from '@/test/render';

function pdf(name = 'receipt.pdf', size = 1000) {
  return new File([new Uint8Array(size).fill(37)], name, { type: 'application/pdf' });
}

describe('validateFile', () => {
  it('accepts supported files and rejects others', () => {
    expect(upload.validateFile(pdf())).toBeNull();
    expect(upload.validateFile(new File(['x'], 'a.gif', { type: 'image/gif' }))).toMatch(
      /Unsupported/,
    );
    expect(upload.validateFile(new File(['x'], 'a.png', { type: 'application/pdf' }))).toMatch(
      /does not match/,
    );
    expect(upload.validateFile(new File([], 'a.pdf', { type: 'application/pdf' }))).toMatch(
      /empty/,
    );
    expect(upload.validateFile(pdf('big.pdf', 16 * 1024 * 1024))).toMatch(/too large/);
  });
});

describe('upload page', () => {
  it('uploads a file, shows progress, then the processing result', async () => {
    const uploadUrl = vi.spyOn(api, 'uploadUrl').mockResolvedValue({
      document_id: 'doc9',
      upload_url: 'https://storage.test/put',
      method: 'PUT',
      headers: { 'Content-Type': 'application/pdf', 'x-goog-content-length-range': '1000,1000' },
      expires_at: '2026-11-09T12:15:00Z',
      status: 'AWAITING_UPLOAD',
    });
    const put = vi
      .spyOn(upload, 'putWithProgress')
      .mockImplementation(async (_u, _f, _h, onProgress) => {
        onProgress(0.5);
        onProgress(1);
      });
    vi.spyOn(api, 'documentStatus').mockResolvedValue({
      document_id: 'doc9',
      status: 'VALID',
      processing_attempts: 1,
      updated_at: '2026-11-09T12:00:05Z',
      completed_at: '2026-11-09T12:00:05Z',
      error: null,
    });

    renderApp('/upload');
    fireEvent.change(await screen.findByTestId('file-input'), { target: { files: [pdf()] } });

    expect(await screen.findByText('Valid')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View' })).toHaveAttribute('href', '/documents/doc9');
    expect(uploadUrl).toHaveBeenCalledWith({
      filename: 'receipt.pdf',
      content_type: 'application/pdf',
      size_bytes: 1000,
      sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
    });
    expect(put).toHaveBeenCalledWith(
      'https://storage.test/put',
      expect.any(File),
      expect.objectContaining({ 'Content-Type': 'application/pdf' }),
      expect.any(Function),
    );
  });

  it('links straight to review when the document needs it', async () => {
    vi.spyOn(api, 'uploadUrl').mockResolvedValue({
      document_id: 'doc7',
      upload_url: 'u',
      method: 'PUT',
      headers: {},
      expires_at: '',
      status: 'AWAITING_UPLOAD',
    });
    vi.spyOn(upload, 'putWithProgress').mockResolvedValue();
    vi.spyOn(api, 'documentStatus').mockResolvedValue({
      document_id: 'doc7',
      status: 'REVIEW_REQUIRED',
      processing_attempts: 1,
      updated_at: '',
      completed_at: null,
      error: null,
    });
    renderApp('/upload');
    fireEvent.change(await screen.findByTestId('file-input'), { target: { files: [pdf()] } });
    expect(await screen.findByRole('link', { name: 'Review now' })).toHaveAttribute(
      'href',
      '/review/doc7',
    );
  });

  it('rejects invalid files without calling the API', async () => {
    const uploadUrl = vi.spyOn(api, 'uploadUrl');
    renderApp('/upload');
    fireEvent.change(await screen.findByTestId('file-input'), {
      target: { files: [new File(['x'], 'a.gif', { type: 'image/gif' })] },
    });
    expect(await screen.findByText(/a\.gif: Unsupported file type/)).toBeInTheDocument();
    expect(uploadUrl).not.toHaveBeenCalled();
  });

  it('shows upload errors', async () => {
    vi.spyOn(api, 'uploadUrl').mockRejectedValue(new Error('File is too large.'));
    renderApp('/upload');
    fireEvent.change(await screen.findByTestId('file-input'), { target: { files: [pdf()] } });
    await waitFor(() => expect(screen.getByText('File is too large.')).toBeInTheDocument());
  });
});
