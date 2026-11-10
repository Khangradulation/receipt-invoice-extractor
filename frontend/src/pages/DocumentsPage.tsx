import { useInfiniteQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { DocumentTable } from '@/components/documents/DocumentTable';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button, Card, EmptyState, ErrorState, LoadingState, SelectField } from '@/components/ui';
import { api } from '@/lib/api';
import { STATUS_INFO } from '@/lib/format';
import type { DocumentStatus } from '@/lib/types';

const FILTERS: DocumentStatus[] = [
  'VALID',
  'REVIEW_REQUIRED',
  'APPROVED',
  'REJECTED',
  'DUPLICATE',
  'FAILED',
  'PROCESSING',
];

export function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const status = (params.get('status') as DocumentStatus | null) ?? null;
  const docs = useInfiniteQuery({
    queryKey: ['documents', status],
    queryFn: ({ pageParam }) =>
      api.documents({ status: status ? [status] : undefined, limit: 25, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const items = docs.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader
        title="Documents"
        description="Everything you have uploaded, newest first."
        actions={
          <Link to="/upload">
            <Button>Upload</Button>
          </Link>
        }
      />
      <Card>
        <div className="mb-4 max-w-xs">
          <SelectField
            label="Status"
            value={status ?? ''}
            onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}
          >
            <option value="">All statuses</option>
            {FILTERS.map((s) => (
              <option key={s} value={s}>
                {STATUS_INFO[s].label}
              </option>
            ))}
          </SelectField>
        </div>
        {docs.isPending ? (
          <LoadingState label="Loading documents…" />
        ) : docs.isError ? (
          <ErrorState error={docs.error} onRetry={() => void docs.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            title={status ? 'No documents with this status' : 'No documents yet'}
            description={
              status
                ? 'Try another filter.'
                : 'Upload your first receipt or invoice to get started.'
            }
            action={
              !status && (
                <Link to="/upload">
                  <Button>Upload documents</Button>
                </Link>
              )
            }
          />
        ) : (
          <>
            <DocumentTable items={items} />
            {docs.hasNextPage && (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="secondary"
                  onClick={() => void docs.fetchNextPage()}
                  disabled={docs.isFetchingNextPage}
                >
                  {docs.isFetchingNextPage ? 'Loading…' : 'Load more'}
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
