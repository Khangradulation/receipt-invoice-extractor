import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth/context';
import { CorrectionHistory } from '@/components/documents/CorrectionHistory';
import { ExtractedFields } from '@/components/documents/ExtractedFields';
import { FileViewer } from '@/components/documents/FileViewer';
import { HistoryTimeline } from '@/components/documents/HistoryTimeline';
import { ValidationPanel } from '@/components/documents/ValidationPanel';
import { PageHeader } from '@/components/layout/PageHeader';
import { Alert, Button, Card, ErrorState, LoadingState, StatusBadge } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { formatBytes, formatDateTime } from '@/lib/format';
import { FINAL_STATUSES } from '@/lib/types';
import { NotFoundPage } from './NotFoundPage';

export function DocumentDetailPage() {
  const { documentId = '' } = useParams();
  const { user } = useAuth();
  const doc = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => api.document(documentId),
    refetchInterval: (q) =>
      q.state.data && !FINAL_STATUSES.includes(q.state.data.status) ? 2000 : false,
  });
  if (doc.isPending) return <LoadingState label="Loading document…" />;
  if (doc.isError) {
    if (doc.error instanceof ApiError && doc.error.status === 404) return <NotFoundPage />;
    return <ErrorState error={doc.error} onRetry={() => void doc.refetch()} />;
  }
  const d = doc.data;
  const shown = d.corrected ?? d.extraction;
  return (
    <>
      <PageHeader
        title={d.filename}
        description={
          <span className="flex items-center gap-2">
            <StatusBadge status={d.status} /> Uploaded {formatDateTime(d.created_at)}
          </span>
        }
        actions={
          d.status === 'REVIEW_REQUIRED' && (
            <Link to={`/review/${d.document_id}`}>
              <Button>Review</Button>
            </Link>
          )
        }
      />
      {d.error && (
        <div className="mb-4">
          <Alert tone="error" title="Processing failed">
            {d.error.message}
          </Alert>
        </div>
      )}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Original document">
          <FileViewer documentId={d.document_id} filename={d.filename} />
        </Card>
        <div className="space-y-6">
          <Card
            title={d.corrected ? 'Extracted data (with your corrections)' : 'Extracted data'}
            description={d.model_version ? `Model ${d.model_version}` : undefined}
          >
            {shown ? (
              <ExtractedFields doc={shown} failedFields={d.validation?.failed_fields ?? []} />
            ) : (
              <p className="text-sm text-slate-500">Not extracted yet.</p>
            )}
          </Card>
          <Card title="Validation">
            <ValidationPanel validation={d.validation} />
          </Card>
          {d.review && (
            <Card title="Review & audit">
              {d.review.decision && (
                <p className="mb-3 text-sm">
                  <span className="font-medium">
                    {d.review.decision.action === 'APPROVED' ? 'Approved' : 'Rejected'}
                  </span>{' '}
                  {d.review.decision.by === user?.uid ? 'by you' : `by ${d.review.decision.by}`} on{' '}
                  {formatDateTime(d.review.decision.at)}
                  {d.review.decision.reason && (
                    <span className="block text-slate-600">Reason: {d.review.decision.reason}</span>
                  )}
                </p>
              )}
              <CorrectionHistory corrections={d.review.corrections} />
            </Card>
          )}
          <Card title="Processing history">
            <HistoryTimeline history={d.history} />
            <dl className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-500">
              <dt>Size</dt>
              <dd>
                {formatBytes(d.size_bytes)}
                {d.page_count ? ` · ${d.page_count} page${d.page_count > 1 ? 's' : ''}` : ''}
              </dd>
              <dt>Attempts</dt>
              <dd>{d.processing_attempts}</dd>
              <dt>Processing time</dt>
              <dd>
                {d.processing_duration_ms
                  ? `${(d.processing_duration_ms / 1000).toFixed(1)} s`
                  : '—'}
              </dd>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
