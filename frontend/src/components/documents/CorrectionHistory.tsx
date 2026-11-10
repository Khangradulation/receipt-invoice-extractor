import { useAuth } from '@/auth/context';
import { FIELD_LABELS, formatDateTime } from '@/lib/format';
import type { Correction } from '@/lib/types';

/** Audit trail of reviewer corrections: field, before → after, original AI value, who, when. */
export function CorrectionHistory({ corrections }: { corrections: Correction[] }) {
  const { user } = useAuth();
  if (corrections.length === 0) return <p className="text-sm text-slate-500">No corrections.</p>;
  return (
    <ul className="space-y-2 text-sm">
      {corrections.map((c) => (
        <li key={c.review_id}>
          <span className="font-medium">{FIELD_LABELS[c.field_name] ?? c.field_name}</span>:{' '}
          <span className="text-slate-500 line-through">{c.previous_value ?? 'empty'}</span> →{' '}
          <span>{c.corrected_value ?? 'empty'}</span>
          <span className="block text-xs text-slate-500">
            AI value: {c.original_value ?? 'empty'} ·{' '}
            {c.reviewer_id === user?.uid ? 'you' : c.reviewer_id} · {formatDateTime(c.reviewed_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}
