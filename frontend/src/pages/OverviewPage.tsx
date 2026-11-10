import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { DocumentTable } from '@/components/documents/DocumentTable';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatCard } from '@/components/ui';
import { api } from '@/lib/api';
import { defaultRange } from '@/lib/dates';
import { formatMoney, formatPercent } from '@/lib/format';

export function OverviewPage() {
  const range = defaultRange();
  const overview = useQuery({ queryKey: ['overview', range], queryFn: () => api.overview(range) });
  const recent = useQuery({
    queryKey: ['documents', 'recent'],
    queryFn: () => api.documents({ limit: 5 }),
  });
  const queue = useQuery({
    queryKey: ['review-queue', 'count'],
    queryFn: () => api.reviewQueue({ limit: 100 }),
  });

  const spending = overview.data?.total_spending ?? [];
  const primary = spending[0];
  const reviewCount = queue.data?.items.length ?? 0;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Your last 12 months at a glance."
        actions={
          <Link to="/upload">
            <Button>Upload documents</Button>
          </Link>
        }
      />
      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total spending"
            value={
              overview.isPending
                ? '…'
                : primary
                  ? formatMoney(primary.total_amount as string, primary.currency as string)
                  : formatMoney(0)
            }
            hint={
              spending.length > 1
                ? `+ ${spending.length - 1} other currenc${spending.length > 2 ? 'ies' : 'y'}`
                : 'Approved transactions'
            }
          />
          <StatCard
            label="Transactions"
            value={
              overview.isPending
                ? '…'
                : spending.reduce((n, r) => n + Number(r.transaction_count ?? 0), 0)
            }
          />
          <StatCard
            label="Processing success"
            value={
              overview.isPending
                ? '…'
                : formatPercent(overview.data?.processing_success_rate.success_rate as number)
            }
          />
          <StatCard
            label="Needs review"
            value={queue.isPending ? '…' : reviewCount}
            hint={
              <Link to="/review" className="text-indigo-600 hover:text-indigo-500">
                Open review queue
              </Link>
            }
          />
        </div>
      )}
      <Card
        title="Recent documents"
        className="mt-6"
        actions={
          <Link
            to="/documents"
            className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
          >
            View all
          </Link>
        }
      >
        {recent.isPending ? (
          <LoadingState />
        ) : recent.isError ? (
          <ErrorState error={recent.error} onRetry={() => void recent.refetch()} />
        ) : recent.data.items.length === 0 ? (
          <EmptyState
            title="No documents yet"
            description="Upload a receipt or invoice to see it here."
            action={
              <Link to="/upload">
                <Button>Upload</Button>
              </Link>
            }
          />
        ) : (
          <DocumentTable items={recent.data.items} />
        )}
      </Card>
    </>
  );
}
