import { STATUS_INFO } from '@/lib/format';
import type { DocumentStatus } from '@/lib/types';
import { Badge } from './Badge';

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const info = STATUS_INFO[status] ?? { label: status, tone: 'neutral' as const };
  return <Badge tone={info.tone}>{info.label}</Badge>;
}
