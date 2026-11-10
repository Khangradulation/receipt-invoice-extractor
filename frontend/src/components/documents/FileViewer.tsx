import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { ErrorState, LoadingState } from '@/components/ui';
import { api } from '@/lib/api';

/** Shows the original upload via a short-lived signed URL (PDF in an iframe, images inline). */
export function FileViewer({ documentId, filename }: { documentId: string; filename: string }) {
  const file = useQuery({
    queryKey: ['file-url', documentId],
    queryFn: () => api.documentFile(documentId),
    staleTime: 5 * 60_000, // URLs are valid for 15 minutes
  });
  if (file.isPending) return <LoadingState label="Loading document…" />;
  if (file.isError) return <ErrorState error={file.error} onRetry={() => void file.refetch()} />;
  const { url, content_type } = file.data;
  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="truncate text-slate-500" title={filename}>
          {filename}
        </span>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-500"
        >
          Open <ExternalLink className="size-4" aria-hidden="true" />
        </a>
      </div>
      {content_type === 'application/pdf' ? (
        <iframe
          title={`Document ${filename}`}
          src={url}
          className="min-h-[70vh] w-full flex-1 rounded-lg border border-slate-200 bg-white"
        />
      ) : (
        <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
          <img src={url} alt={`Uploaded document ${filename}`} className="mx-auto max-w-full" />
        </div>
      )}
    </div>
  );
}
