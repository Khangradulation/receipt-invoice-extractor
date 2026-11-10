import { useInfiniteQuery } from '@tanstack/react-query';
import { DocumentTable } from '@/components/documents/DocumentTable';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '@/components/ui';
import { api } from '@/lib/api';

export function ReviewQueuePage() {
  const queue = useInfiniteQuery({
    queryKey: ['review-queue'],
    queryFn: ({ pageParam }) => api.reviewQueue({ limit: 25, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const items = queue.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHeader
        title="Review queue"
        description="Documents that failed a check and need a person to confirm or correct them."
      />
      <Card>
        {queue.isPending ? (
          <LoadingState />
        ) : queue.isError ? (
          <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            title="Nothing to review"
            description="Every processed document passed its checks."
          />
        ) : (
          <>
            <DocumentTable items={items} linkTo={(d) => `/review/${d.document_id}`} />
            {queue.hasNextPage && (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="secondary"
                  onClick={() => void queue.fetchNextPage()}
                  disabled={queue.isFetchingNextPage}
                >
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
