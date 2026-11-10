import { formatDateTime, STATUS_INFO } from '@/lib/format';
import type { DocumentStatus, HistoryEntry } from '@/lib/types';

export function HistoryTimeline({ history }: { history: HistoryEntry[] }) {
  if (!history.length) return <p className="text-sm text-slate-500">No processing history yet.</p>;
  return (
    <ol className="relative space-y-3 border-l border-slate-200 pl-4">
      {history.map((h, i) => (
        <li key={i} className="text-sm">
          <span
            className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-white bg-indigo-500"
            aria-hidden="true"
          />
          <p className="font-medium text-slate-900">
            {STATUS_INFO[h.status as DocumentStatus]?.label ?? h.status}
            {h.detail && <span className="font-normal text-slate-500"> · {h.detail}</span>}
          </p>
          <p className="text-xs text-slate-500">{formatDateTime(h.at)}</p>
        </li>
      ))}
    </ol>
  );
}
