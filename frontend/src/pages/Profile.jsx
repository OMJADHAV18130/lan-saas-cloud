import { useCallback, useEffect, useState } from 'react';
import { authApi, dashboardApi, errorOf } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ErrorAlert, PageHeader, ProgressBar, Spinner } from '../components/ui';
import { formatBytes, formatDate } from '../utils/format';

export default function Profile() {
  const { user, refresh } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [me, statsResponse] = await Promise.all([
        authApi.me(),
        dashboardApi.stats(),
      ]);
      await refresh();
      setStats({ ...statsResponse.data, me: me.data });
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  useEffect(() => { load(); }, [load]);

  const account = stats?.me || user;
  const usedPercent = stats && stats.storage_quota_bytes
    ? (stats.storage_used_bytes / stats.storage_quota_bytes) * 100
    : 0;

  const rows = account ? [
    ['User ID', account.id],
    ['Username', account.username],
    ['Role', account.role === 'admin' ? 'Administrator' : 'Standard user'],
    ['Account status', account.is_active ? 'Active' : 'Disabled'],
    ['Member since', formatDate(account.created_at)],
    ['Storage quota', formatBytes(account.storage_quota_bytes)],
  ] : [];

  return (
    <div className="max-w-3xl">
      <PageHeader title="Profile" subtitle="Account information served by GET /api/auth/me" />

      {error && <div className="mb-4"><ErrorAlert error={error} onDismiss={() => setError(null)} /></div>}

      {loading ? <Spinner label="Loading profile…" /> : (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="text-sm font-semibold text-slate-800">Account details</h2>
            <dl className="mt-4 divide-y divide-slate-100">
              {rows.map(([label, value]) => (
                <div key={label} className="flex flex-col gap-1 py-3 sm:flex-row sm:justify-between">
                  <dt className="text-sm text-slate-500">{label}</dt>
                  <dd className="break-all text-sm font-medium text-slate-700 sm:text-right">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="card p-6">
            <h2 className="text-sm font-semibold text-slate-800">Storage summary</h2>
            {stats ? (
              <>
                <p className="mt-2 text-sm text-slate-600">
                  {stats.total_files} file{stats.total_files === 1 ? '' : 's'} ·{' '}
                  {formatBytes(stats.storage_used_bytes)} used of{' '}
                  {formatBytes(stats.storage_quota_bytes)}
                </p>
                <div className="mt-4">
                  <ProgressBar percent={usedPercent} label="Quota usage" />
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  Passwords are stored only as Argon2 hashes. The controller never
                  returns password material, and file contents are never stored in SQLite.
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-500">No statistics available.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
