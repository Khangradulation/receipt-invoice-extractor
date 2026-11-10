import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileUp } from 'lucide-react';
import { useCallback, useRef, useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from '@/components/layout/PageHeader';
import { Alert, Card, StatusBadge } from '@/components/ui';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { formatBytes } from '@/lib/format';
import { FINAL_STATUSES } from '@/lib/types';
import { putWithProgress, sha256Hex, validateFile } from '@/lib/upload';

type Stage = 'hashing' | 'requesting' | 'uploading' | 'processing' | 'error';

interface UploadItem {
  key: string;
  file: File;
  stage: Stage;
  progress: number;
  documentId?: string;
  error?: string;
}

function ProcessingStatus({ documentId }: { documentId: string }) {
  const status = useQuery({
    queryKey: ['status', documentId],
    queryFn: () => api.documentStatus(documentId),
    refetchInterval: (q) =>
      q.state.data && FINAL_STATUSES.includes(q.state.data.status) ? false : 2000,
  });
  if (!status.data) return <span className="text-xs text-slate-500">Waiting for processing…</span>;
  const done = FINAL_STATUSES.includes(status.data.status);
  return (
    <span className="flex items-center gap-2">
      <StatusBadge status={status.data.status} />
      {done && (
        <Link
          to={
            status.data.status === 'REVIEW_REQUIRED'
              ? `/review/${documentId}`
              : `/documents/${documentId}`
          }
          className="text-xs font-medium text-indigo-600 hover:text-indigo-500"
        >
          {status.data.status === 'REVIEW_REQUIRED' ? 'Review now' : 'View'}
        </Link>
      )}
      {status.data.error && (
        <span className="text-xs text-red-600">{status.data.error.message}</span>
      )}
    </span>
  );
}

export function UploadPage() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);

  const update = (key: string, patch: Partial<UploadItem>) =>
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  const uploadOne = useCallback(
    async (item: UploadItem) => {
      try {
        const sha256 = await sha256Hex(item.file);
        update(item.key, { stage: 'requesting' });
        const issued = await api.uploadUrl({
          filename: item.file.name,
          content_type: item.file.type === 'image/jpg' ? 'image/jpeg' : item.file.type,
          size_bytes: item.file.size,
          sha256,
        });
        update(item.key, { stage: 'uploading', documentId: issued.document_id });
        await putWithProgress(issued.upload_url, item.file, issued.headers, (p) =>
          update(item.key, { progress: p }),
        );
        update(item.key, { stage: 'processing', progress: 1 });
        void queryClient.invalidateQueries({ queryKey: ['documents'] });
      } catch (err) {
        update(item.key, {
          stage: 'error',
          error: err instanceof Error ? err.message : 'Upload failed.',
        });
      }
    },
    [queryClient],
  );

  function addFiles(files: FileList | File[]) {
    const accepted: UploadItem[] = [];
    const errors: string[] = [];
    for (const file of Array.from(files)) {
      const problem = validateFile(file);
      if (problem) errors.push(`${file.name}: ${problem}`);
      else
        accepted.push({
          key: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
          file,
          stage: 'hashing',
          progress: 0,
        });
    }
    setRejected(errors);
    setItems((prev) => [...accepted, ...prev]);
    accepted.forEach((it) => void uploadOne(it));
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  return (
    <>
      <PageHeader
        title="Upload documents"
        description="PDF, PNG or JPEG receipts and invoices, up to 15 MB each."
      />
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload files: drop files here or press Enter to choose"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors',
          dragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-slate-300 bg-white hover:border-indigo-400',
        )}
      >
        <FileUp className="size-10 text-indigo-500" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-slate-900">
          Drag and drop files here, or click to choose
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Each file is checked, uploaded securely and processed automatically.
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          className="sr-only"
          data-testid="file-input"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {rejected.length > 0 && (
        <div className="mt-4">
          <Alert tone="error" title="Some files were not uploaded">
            <ul className="list-disc pl-4">
              {rejected.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Alert>
        </div>
      )}

      {items.length > 0 && (
        <Card title="Uploads" className="mt-6">
          <ul className="divide-y divide-slate-100">
            {items.map((it) => (
              <li key={it.key} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{it.file.name}</p>
                  <p className="text-xs text-slate-500">{formatBytes(it.file.size)}</p>
                </div>
                <div className="flex items-center gap-3">
                  {it.stage === 'error' && <span className="text-sm text-red-600">{it.error}</span>}
                  {(it.stage === 'hashing' || it.stage === 'requesting') && (
                    <span className="text-xs text-slate-500">Preparing…</span>
                  )}
                  {it.stage === 'uploading' && (
                    <div className="flex items-center gap-2">
                      <div
                        className="h-2 w-32 overflow-hidden rounded-full bg-slate-200"
                        role="progressbar"
                        aria-valuenow={Math.round(it.progress * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Uploading ${it.file.name}`}
                      >
                        <div
                          className="h-full bg-indigo-600 transition-all"
                          style={{ width: `${it.progress * 100}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-xs text-slate-500 tabular-nums">
                        {Math.round(it.progress * 100)}%
                      </span>
                    </div>
                  )}
                  {it.stage === 'processing' && it.documentId && (
                    <ProcessingStatus documentId={it.documentId} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
