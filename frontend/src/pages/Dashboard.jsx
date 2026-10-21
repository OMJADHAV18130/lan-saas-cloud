import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { dashboardApi, errorOf, healthApi } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { EmptyState, ErrorAlert, PageHeader, ProgressBar, Spinner, StatCard } from '../components/ui';
import { fileExtension, formatBytes, formatDate } from '../utils/format';

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsResponse, healthResponse] = await Promise.all([
        dashboardApi.stats(),
        healthApi.health(),
      ]);
      setStats(statsResponse.data);
      setHealth(healthResponse.data);
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const usedPercent = stats && stats.storage_quota_bytes
    ? (stats.storage_used_bytes / stats.storage_quota_bytes) * 100
    : 0;

  return (
    <div>
      <PageHeader
        title={`Welcome, ${user?.username}`}
        subtitle="Your private storage on the departmental HDFS cluster"
        actions={<Link to="/upload" className="btn-primary">Upload file</Link>}
      />

      {error && <div className="mb-4"><ErrorAlert error={error} onDismiss={() => setError(null)} /></div>}

      {health && health.status !== 'ok' && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p className="font-medium">Storage notice</p>
          <p className="mt-0.5">{health.storage.message}</p>
          {health.storage.adapter === 'mock' && (
            <p className="mt-1 text-xs">
              The controller is running without Hadoop (mock adapter). Start a
              real cluster and set <code>HDFS_ADAPTER=webhdfs</code> for the
              lab demonstration.
            </p>
          )}
        </div>
      )}

      {loading ? (
        <Spinner label="Loading your dashboard…" />
      ) : stats && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Files stored" value={stats.total_files}
              hint="Metadata records owned by you" />
            <StatCard label="Storage used" value={formatBytes(stats.storage_used_bytes)}
              hint="Measured from the database, not estimated" />
            <StatCard label="Quota" value={formatBytes(stats.storage_quota_bytes)}
              hint={`${formatBytes(Math.max(stats.storage_quota_bytes - stats.storage_used_bytes, 0))} free`}
              accent="emerald" />
            <StatCard label="Storage backend"
              value={health?.storage?.adapter === 'webhdfs' ? 'HDFS' : 'Mock'}
              hint={health?.storage?.mode_label} accent="slate" />
          </div>

          <div className="card mt-6 p-5">
            <h2 className="text-sm font-semibold text-slate-800">Quota usage</h2>
            <div className="mt-3">
              <ProgressBar percent={usedPercent}
                label={`${formatBytes(stats.storage_used_bytes)} of ${formatBytes(stats.storage_quota_bytes)}`} />
            </div>
          </div>

          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Recent uploads</h2>
              <Link to="/files" className="text-sm font-medium text-brand-600 hover:underline">
                View all files
              </Link>
            </div>
            {stats.recent_files.length === 0 ? (
              <EmptyState title="No files yet"
                hint="Upload your first file to see it stored in HDFS."
                action={<Link to="/upload" className="btn-primary mt-3">Upload file</Link>} />
            ) : (
              <div className="card overflow-hidden">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Size</th>
                      <th className="px-4 py-3">Uploaded</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {stats.recent_files.map((file) => (
                      <tr key={file.id}>
                        <td className="px-4 py-3 font-medium text-slate-700">{file.original_name}</td>
                        <td className="px-4 py-3 text-slate-500">{fileExtension(file.original_name)}</td>
                        <td className="px-4 py-3 text-slate-500">{formatBytes(file.size_bytes)}</td>
                        <td className="px-4 py-3 text-slate-500">{formatDate(file.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
