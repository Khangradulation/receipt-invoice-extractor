import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { authErrorMessage, useAuth } from '@/auth/context';
import { PageHeader } from '@/components/layout/PageHeader';
import { Alert, Badge, Button, Card, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import { config } from '@/lib/config';

export function SettingsPage() {
  const { user, resetPassword, signOut } = useAuth();
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false });

  async function onReset() {
    if (!user?.email) return;
    try {
      await resetPassword(user.email);
      setNotice({ tone: 'success', text: `A password reset link was sent to ${user.email}.` });
    } catch (err) {
      setNotice({ tone: 'error', text: authErrorMessage(err) });
    }
  }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="space-y-6">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        <Card title="Account">
          <dl className="grid grid-cols-3 gap-y-3 text-sm">
            <dt className="text-slate-500">Email</dt>
            <dd className="col-span-2">{user?.email}</dd>
            <dt className="text-slate-500">User ID</dt>
            <dd className="col-span-2 font-mono text-xs">{user?.uid}</dd>
          </dl>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={() => void onReset()}>
              Send password reset email
            </Button>
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </Card>
        <Card title="Upload limits">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
            <li>PDF, PNG or JPEG, up to {config.maxUploadBytes / (1024 * 1024)} MB each.</li>
            <li>PDFs up to 10 pages. Password-protected PDFs are not supported.</li>
            <li>Files are stored privately; only you can view them.</li>
          </ul>
        </Card>
        <Card title="System status">
          {health.isPending ? (
            <Spinner label="Checking API…" />
          ) : health.isError ? (
            <Alert tone="error" title="API unreachable">
              The backend could not be reached.
            </Alert>
          ) : (
            <p className="flex items-center gap-2 text-sm">
              <Badge tone="success">API healthy</Badge>
              <span className="text-slate-500">
                v{health.data.version} · {health.data.environment}
              </span>
            </p>
          )}
        </Card>
      </div>
    </>
  );
}
