import { Link } from 'react-router-dom';
import { StatusBadge } from '@/components/ui';
import { formatDate, formatDateTime, formatMoney, humanize } from '@/lib/format';
import type { DocumentSummary } from '@/lib/types';

export function DocumentTable({
  items,
  linkTo = (d) => `/documents/${d.document_id}`,
}: {
  items: DocumentSummary[];
  linkTo?: (d: DocumentSummary) => string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
            <th className="py-2 pr-4 font-medium">Document</th>
            <th className="py-2 pr-4 font-medium">Merchant</th>
            <th className="py-2 pr-4 font-medium">Date</th>
            <th className="py-2 pr-4 text-right font-medium">Total</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 font-medium">Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.document_id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="max-w-56 py-2.5 pr-4">
                <Link
                  to={linkTo(d)}
                  className="block truncate font-medium text-indigo-600 hover:text-indigo-500"
                  title={d.filename}
                >
                  {d.filename}
                </Link>
                <span className="text-xs text-slate-500">{humanize(d.document_type)}</span>
              </td>
              <td className="py-2.5 pr-4">{d.merchant_name ?? '—'}</td>
              <td className="py-2.5 pr-4 whitespace-nowrap">{formatDate(d.document_date)}</td>
              <td className="py-2.5 pr-4 text-right whitespace-nowrap tabular-nums">
                {formatMoney(d.total_amount, d.currency)}
              </td>
              <td className="py-2.5 pr-4">
                <StatusBadge status={d.status} />
              </td>
              <td className="py-2.5 whitespace-nowrap text-slate-500">
                {formatDateTime(d.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
