import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '@/components/layout/PageHeader';
import { Alert, Badge, Button, Card, Spinner } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { config } from '@/lib/config';

export function SystemStatusPage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    retry: false,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="System status"
        description="Live connectivity check between this app and the backend API."
        actions={
          <Button
            variant="secondary"
            onClick={() => void health.refetch()}
            disabled={health.isFetching}
          >
            Refresh
          </Button>
        }
      />
      <Card title="API" description={config.apiBaseUrl || 'Same origin (/api)'}>
        {health.isPending ? (
          <Spinner label="Checking API…" />
        ) : health.isError ? (
          <Alert tone="error" title="API unreachable">
            {health.error instanceof ApiError ? health.error.message : 'Unexpected error.'}
          </Alert>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd className="mt-1">
                <Badge tone="success">Healthy</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Version</dt>
              <dd className="mt-1 font-medium">{health.data.version}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Environment</dt>
              <dd className="mt-1 font-medium">{health.data.environment}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Checked at</dt>
              <dd className="mt-1 font-medium">
                {new Date(health.data.timestamp).toLocaleTimeString()}
              </dd>
            </div>
          </dl>
        )}
      </Card>
    </>
  );
}
