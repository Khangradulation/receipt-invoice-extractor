import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SelectField,
  StatCard,
  TextField,
} from '@/components/ui';
import { api } from '@/lib/api';
import { defaultRange } from '@/lib/dates';
import { formatMoney, formatPercent, humanize } from '@/lib/format';
import type { Row } from '@/lib/types';

const num = (v: Row[string] | undefined) => Number(v ?? 0);

export function AnalyticsPage() {
  const [range, setRange] = useState(defaultRange);
  const valid = range.start_date <= range.end_date;
  const enabled = valid && Boolean(range.start_date && range.end_date);
  const overview = useQuery({
    queryKey: ['overview', range],
    queryFn: () => api.overview(range),
    enabled,
  });
  const monthly = useQuery({
    queryKey: ['monthly', range],
    queryFn: () => api.monthlySpending(range),
    enabled,
  });
  const categories = useQuery({
    queryKey: ['categories', range],
    queryFn: () => api.categories(range),
    enabled,
  });
  const merchants = useQuery({
    queryKey: ['merchants', range],
    queryFn: () => api.merchants(range, 10),
    enabled,
  });

  const currencies = useMemo(
    () => (overview.data?.total_spending ?? []).map((r) => String(r.currency)),
    [overview.data],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const currency = picked && currencies.includes(picked) ? picked : (currencies[0] ?? null);
  const inCurrency = (rows: Row[] = []) => rows.filter((r) => r.currency === currency);

  const total = overview.data?.total_spending.find((r) => r.currency === currency);
  const average = overview.data?.average_transaction_value.find((r) => r.currency === currency);
  const monthlyData = inCurrency(monthly.data?.rows).map((r) => ({
    month: String(r.month).slice(0, 7),
    total: num(r.total_amount),
  }));
  const categoryData = inCurrency(categories.data?.rows).map((r) => ({
    category: humanize(String(r.expense_category)),
    total: num(r.total_amount),
  }));

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Approved transactions from BigQuery. Amounts are never mixed across currencies."
      />
      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            label="From"
            type="date"
            value={range.start_date}
            max={range.end_date}
            onChange={(e) => setRange((r) => ({ ...r, start_date: e.target.value }))}
            error={!valid ? 'Start must be before end.' : undefined}
          />
          <TextField
            label="To"
            type="date"
            value={range.end_date}
            onChange={(e) => setRange((r) => ({ ...r, end_date: e.target.value }))}
          />
          <SelectField
            label="Currency"
            value={currency ?? ''}
            onChange={(e) => setPicked(e.target.value)}
            disabled={currencies.length < 2}
          >
            {currencies.length === 0 && <option value="">—</option>}
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </SelectField>
        </div>
      </Card>

      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
      ) : overview.isPending ? (
        <LoadingState label="Loading analytics…" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total spending"
              value={total ? formatMoney(total.total_amount as string, currency) : '—'}
              hint={total ? `${total.transaction_count} transactions` : undefined}
            />
            <StatCard
              label="Average transaction"
              value={average ? formatMoney(average.average_amount as string, currency) : '—'}
              hint={
                average
                  ? `Largest ${formatMoney(average.max_amount as string, currency)}`
                  : undefined
              }
            />
            <StatCard
              label="Processing success rate"
              value={formatPercent(overview.data.processing_success_rate.success_rate as number)}
              hint={`${overview.data.processing_success_rate.processed_documents ?? 0} documents processed`}
            />
            <StatCard
              label="Manual review rate"
              value={formatPercent(overview.data.manual_review_rate.review_rate as number)}
              hint={`${overview.data.manual_review_rate.review_required ?? 0} needed review`}
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card title="Monthly spending" description={currency ?? undefined}>
              {monthly.isPending ? (
                <LoadingState />
              ) : monthlyData.length === 0 ? (
                <EmptyState title="No spending in this period" />
              ) : (
                <div className="h-64" role="img" aria-label="Monthly spending chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={monthlyData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="month" fontSize={12} />
                      <YAxis fontSize={12} width={60} />
                      <Tooltip formatter={(v) => formatMoney(Number(v), currency)} />
                      <Bar dataKey="total" name="Spending" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card title="Spending by category" description={currency ?? undefined}>
              {categories.isPending ? (
                <LoadingState />
              ) : categoryData.length === 0 ? (
                <EmptyState title="No categories yet" />
              ) : (
                <div className="h-64" role="img" aria-label="Spending by category chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={categoryData} layout="vertical" margin={{ left: 24 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" fontSize={12} />
                      <YAxis type="category" dataKey="category" fontSize={12} width={120} />
                      <Tooltip formatter={(v) => formatMoney(Number(v), currency)} />
                      <Bar dataKey="total" name="Spending" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card title="Top merchants" description={currency ?? undefined}>
              {merchants.isPending ? (
                <LoadingState />
              ) : inCurrency(merchants.data?.rows).length === 0 ? (
                <EmptyState title="No merchants yet" />
              ) : (
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                      <th className="py-2 font-medium">Merchant</th>
                      <th className="py-2 text-right font-medium">Transactions</th>
                      <th className="py-2 text-right font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inCurrency(merchants.data?.rows).map((r) => (
                      <tr key={String(r.merchant_name)} className="border-b border-slate-100">
                        <td className="py-2">{String(r.merchant_name)}</td>
                        <td className="py-2 text-right tabular-nums">
                          {String(r.transaction_count)}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {formatMoney(r.total_amount as string, currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card title="Receipts vs. invoices" description="All processed documents">
              {overview.data.document_type_counts.length === 0 ? (
                <EmptyState title="No documents processed" />
              ) : (
                <dl className="grid grid-cols-2 gap-4">
                  {overview.data.document_type_counts.map((r) => (
                    <div key={String(r.document_type)} className="rounded-lg bg-slate-50 px-4 py-3">
                      <dt className="text-sm text-slate-500">
                        {humanize(String(r.document_type))}s
                      </dt>
                      <dd className="text-xl font-semibold">{String(r.processed_count)}</dd>
                      <dd className="text-xs text-slate-500">
                        {String(r.approved_count)} approved
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
