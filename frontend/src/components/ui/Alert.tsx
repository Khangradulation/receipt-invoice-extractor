import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

const tones = {
  error: 'border-red-200 bg-red-50 text-red-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  info: 'border-sky-200 bg-sky-50 text-sky-800',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
} as const;

interface AlertProps {
  tone?: keyof typeof tones;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}

export function Alert({ tone = 'info', title, children, action }: AlertProps) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex items-start justify-between gap-4 rounded-lg border px-4 py-3',
        tones[tone],
      )}
    >
      <div className="text-sm">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(Boolean(title) && 'mt-1')}>{children}</div>}
      </div>
      {action}
    </div>
  );
}
