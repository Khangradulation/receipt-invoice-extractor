import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { CorrectionHistory } from '@/components/documents/CorrectionHistory';
import { FileViewer } from '@/components/documents/FileViewer';
import { ReviewForm } from '@/components/documents/ReviewForm';
import { ValidationPanel } from '@/components/documents/ValidationPanel';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  Alert,
  Button,
  Card,
  ErrorState,
  LoadingState,
  Modal,
  StatusBadge,
  TextAreaField,
} from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { formatDateTime } from '@/lib/format';
import { changedFields, toForm, type FormLineItem } from '@/lib/reviewForm';
import type { ReviewDetail } from '@/lib/types';
import { NotFoundPage } from './NotFoundPage';

type Message = { tone: 'success' | 'error'; text: string } | null;

export function ReviewEditorPage() {
  const { documentId = '' } = useParams();
  const review = useQuery({
    queryKey: ['review', documentId],
    queryFn: () => api.review(documentId),
  });
  const [message, setMessage] = useState<Message>(null);

  if (review.isPending) return <LoadingState label="Loading review…" />;
  if (review.isError) {
    if (review.error instanceof ApiError && review.error.status === 404) return <NotFoundPage />;
    return <ErrorState error={review.error} onRetry={() => void review.refetch()} />;
  }
  // Re-mount the editor whenever the server's version changes, so the form starts from it.
  const r = review.data;
  const version = `${r.document.updated_at}:${r.corrections.length}:${r.document.status}`;
  return (
    <ReviewEditor
      key={version}
      documentId={documentId}
      review={r}
      message={message}
      setMessage={setMessage}
    />
  );
}

function ReviewEditor({
  documentId,
  review: r,
  message,
  setMessage,
}: {
  documentId: string;
  review: ReviewDetail;
  message: Message;
  setMessage: (m: Message) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const current = r.current;
  const initial = useMemo(() => (current ? toForm(current) : { values: {}, items: [] }), [current]);
  const [values, setValues] = useState<Record<string, string>>(initial.values);
  const [items, setItems] = useState<FormLineItem[]>(initial.items);
  const [ack, setAck] = useState(r.duplicate_acknowledged);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');

  const pending = useMemo(
    () => (current ? changedFields(current, values, items) : {}),
    [current, values, items],
  );
  const dirty = Object.keys(pending).length > 0 || ack !== r.duplicate_acknowledged;

  // Warn before closing or reloading the tab with unsaved corrections.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const onSuccess = (data: ReviewDetail, text: string) => {
    queryClient.setQueryData(['review', documentId], data);
    void queryClient.invalidateQueries({ queryKey: ['documents'] });
    void queryClient.invalidateQueries({ queryKey: ['review-queue'] });
    void queryClient.invalidateQueries({ queryKey: ['document', documentId] });
    setMessage({ tone: 'success', text });
  };
  const onError = (err: unknown) => {
    setMessage({ tone: 'error', text: errorMessage(err) });
    if (err instanceof ApiError && err.status === 409 && !err.validation) {
      // Changed elsewhere: load the latest version (the server message explains why).
      void queryClient.invalidateQueries({ queryKey: ['review', documentId] });
    }
  };

  const save = useMutation({
    mutationFn: () => api.saveCorrections(documentId, pending, ack),
    onSuccess: (d) =>
      onSuccess(
        d,
        d.can_approve
          ? 'Saved. All checks pass — you can approve.'
          : 'Saved. Some checks still fail.',
      ),
    onError,
  });
  const approve = useMutation({
    mutationFn: () => api.approve(documentId),
    onSuccess: (d) => {
      onSuccess(d, 'Approved and saved to analytics.');
      navigate('/review');
    },
    onError: (err) => {
      if (err instanceof ApiError && err.validation) {
        queryClient.setQueryData<ReviewDetail>(
          ['review', documentId],
          (old) => old && { ...old, validation: err.validation, can_approve: false },
        );
      }
      onError(err);
    },
  });
  const reject = useMutation({
    mutationFn: () => api.reject(documentId, reason.trim()),
    onSuccess: (d) => {
      setRejectOpen(false);
      onSuccess(d, 'Rejected.');
      navigate('/review');
    },
    onError,
  });

  const editable = r.document.status === 'REVIEW_REQUIRED';
  const rejectable = editable || r.document.status === 'DUPLICATE';
  const busy = save.isPending || approve.isPending || reject.isPending;
  const possibleDuplicate = r.validation?.duplicate_status === 'POSSIBLE_DUPLICATE';

  return (
    <>
      <PageHeader
        title={`Review: ${r.document.filename}`}
        description={
          <span className="flex items-center gap-2">
            <StatusBadge status={r.document.status} /> Uploaded{' '}
            {formatDateTime(r.document.created_at)}
          </span>
        }
        actions={
          <Link
            to={`/documents/${documentId}`}
            className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
          >
            Document details
          </Link>
        }
      />
      {message && (
        <div className="mb-4">
          <Alert tone={message.tone}>{message.text}</Alert>
        </div>
      )}
      {!editable && (
        <div className="mb-4">
          <Alert tone="info">
            This document is {r.document.status.toLowerCase().replace('_', ' ')} and can no longer
            be edited.
          </Alert>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Original document" className="xl:sticky xl:top-6 xl:self-start">
          <FileViewer documentId={documentId} filename={r.document.filename} />
        </Card>
        <div className="space-y-6">
          <Card title="Validation">
            <ValidationPanel validation={r.validation} />
            {possibleDuplicate && editable && (
              <label className="mt-3 flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                />
                This is a separate transaction, not a duplicate.
              </label>
            )}
          </Card>
          <Card
            title="Extracted values"
            description="Fields with problems are highlighted. The original AI output is kept unchanged."
          >
            {r.current ? (
              <ReviewForm
                values={values}
                items={items}
                failed={r.failed_fields}
                disabled={!editable || busy}
                onChange={(f, v) => setValues((prev) => ({ ...prev, [f]: v }))}
                onItemsChange={setItems}
              />
            ) : (
              <p className="text-sm text-slate-500">No extracted data.</p>
            )}
            <div className="mt-6 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
              <Button
                variant="danger"
                onClick={() => setRejectOpen(true)}
                disabled={!rejectable || busy}
              >
                Reject
              </Button>
              <Button
                variant="secondary"
                onClick={() => save.mutate()}
                disabled={!editable || !dirty || busy}
              >
                {save.isPending ? 'Saving…' : 'Save corrections'}
              </Button>
              <Button
                onClick={() => approve.mutate()}
                disabled={!editable || dirty || !r.can_approve || busy}
                title={
                  dirty
                    ? 'Save your corrections first'
                    : !r.can_approve
                      ? 'Fix the remaining problems first'
                      : undefined
                }
              >
                {approve.isPending ? 'Approving…' : 'Approve'}
              </Button>
            </div>
          </Card>
          <Card title="Correction history">
            <CorrectionHistory corrections={r.corrections} />
          </Card>
        </div>
      </div>

      <Modal
        open={rejectOpen}
        title="Reject document"
        onClose={() => setRejectOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejectOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => reject.mutate()}
              disabled={reason.trim().length < 3 || reject.isPending}
            >
              Reject
            </Button>
          </>
        }
      >
        <TextAreaField
          label="Reason"
          rows={3}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          hint="Required (3–500 characters). Kept in the audit trail."
        />
      </Modal>
    </>
  );
}
