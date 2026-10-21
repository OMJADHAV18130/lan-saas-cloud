import { useEffect } from 'react';

export function Spinner({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-3 py-10 text-slate-500 ${className}`}>
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-slate-700">{title}</h3>
      {hint && <p className="max-w-md text-sm text-slate-500">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorAlert({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <div>
        <p className="font-medium">Request failed</p>
        <p className="mt-0.5">{error.message}</p>
        {Array.isArray(error.details) && error.details.length > 0 && (
          <ul className="mt-1 list-inside list-disc text-rose-700">
            {error.details.map((d, i) => (
              <li key={i}>{d.field ? `${d.field}: ${d.message}` : d.message}</li>
            ))}
          </ul>
        )}
      </div>
      {onDismiss && (
        <button type="button" onClick={onDismiss}
          className="rounded p-1 text-rose-500 hover:bg-rose-100" aria-label="Dismiss">
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd" />
          </svg>
        </button>
      )}
    </div>
  );
}

export function SuccessAlert({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
      <p>{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss}
          className="rounded p-1 text-emerald-600 hover:bg-emerald-100" aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  );
}

export function StatCard({ label, value, hint, accent = 'brand' }) {
  const accents = {
    brand: 'bg-brand-50 text-brand-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    slate: 'bg-slate-100 text-slate-700',
  };
  return (
    <div className="card p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${accents[accent] || accents.brand}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function ProgressBar({ percent, label }) {
  const safe = Math.max(0, Math.min(100, percent || 0));
  return (
    <div>
      {label && (
        <div className="mb-1 flex justify-between text-xs text-slate-500">
          <span>{label}</span>
          <span>{safe}%</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-brand-600 transition-all"
          style={{ width: `${safe}%` }} />
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open, title, message, confirmLabel = 'Confirm', busy = false,
  onConfirm, onCancel,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog" aria-modal="true">
      <div className="card w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        <p className="mt-2 text-sm text-slate-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}
