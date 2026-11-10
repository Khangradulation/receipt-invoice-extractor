import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import type { ValidationIssue, ValidationResult } from '@/lib/types';

function Issue({ issue }: { issue: ValidationIssue }) {
  const error = issue.severity === 'error';
  const Icon = error ? XCircle : AlertTriangle;
  return (
    <li className="flex gap-2 text-sm">
      <Icon
        className={
          error ? 'mt-0.5 size-4 shrink-0 text-red-600' : 'mt-0.5 size-4 shrink-0 text-amber-500'
        }
        aria-hidden="true"
      />
      <span>
        <span className="sr-only">{error ? 'Error: ' : 'Warning: '}</span>
        {issue.message}
      </span>
    </li>
  );
}

export function ValidationPanel({ validation }: { validation: ValidationResult | null }) {
  if (!validation) return <p className="text-sm text-slate-500">Not validated yet.</p>;
  const { validation_errors: errors, validation_warnings: warnings } = validation;
  return (
    <div className="space-y-3">
      {validation.is_valid ? (
        <p className="flex items-center gap-2 text-sm font-medium text-emerald-700">
          <CheckCircle2 className="size-4" aria-hidden="true" /> All required checks passed.
        </p>
      ) : (
        <p className="text-sm font-medium text-red-700">
          {errors.length} problem{errors.length === 1 ? '' : 's'} must be fixed before approval.
        </p>
      )}
      {errors.length > 0 && (
        <ul className="space-y-1.5">
          {errors.map((e, i) => (
            <Issue key={`e${i}`} issue={e} />
          ))}
        </ul>
      )}
      {warnings.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-600">
            {warnings.length} warning{warnings.length === 1 ? '' : 's'}
          </summary>
          <ul className="mt-2 space-y-1.5">
            {warnings.map((w, i) => (
              <Issue key={`w${i}`} issue={w} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
