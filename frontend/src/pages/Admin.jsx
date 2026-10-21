import { useCallback, useEffect, useState } from 'react';
import { adminApi, errorOf } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import {
  ConfirmDialog, ErrorAlert, PageHeader, Spinner, StatCard, SuccessAlert,
} from '../components/ui';
import { formatBytes, formatDate } from '../utils/format';

function StatusPill({ value }) {
  if (value === true) {
    return <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">Reachable</span>;
  }
  if (value === false) {
    return <span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700">Unreachable</span>;
  }
  return <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">Unknown</span>;
}

export default function Admin() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [hdfs, setHdfs] = useState(null);
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [auditFilter, setAuditFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [roleTarget, setRoleTarget] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsResponse, hdfsResponse, usersResponse, auditResponse] = await Promise.all([
        adminApi.stats(),
        adminApi.hdfsStatus(),
        adminApi.users(),
        adminApi.audit({ limit: 50, event_type: auditFilter || undefined }),
      ]);
      setStats(statsResponse.data);
      setHdfs(hdfsResponse.data);
      setUsers(usersResponse.data.items);
      setAudit(auditResponse.data.items);
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setLoading(false);
    }
  }, [auditFilter]);

  useEffect(() => { load(); }, [load]);

  const applyRole = async () => {
    if (!roleTarget) return;
    setBusy(true);
    setError(null);
    try {
      const nextRole = roleTarget.role === 'admin' ? 'user' : 'admin';
      await adminApi.setRole(roleTarget.id, nextRole);
      setNotice(`${roleTarget.username} is now ${nextRole === 'admin' ? 'an administrator' : 'a standard user'}.`);
      setRoleTarget(null);
      await load();
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Admin Dashboard"
        subtitle="Aggregate usage, HDFS cluster health and audit trail"
        actions={<button type="button" className="btn-secondary" onClick={load}>Refresh</button>} />

      <div className="mb-4 space-y-3">
        {error && <ErrorAlert error={error} onDismiss={() => setError(null)} />}
        {notice && <SuccessAlert message={notice} onDismiss={() => setNotice(null)} />}
      </div>

      {loading && !stats ? <Spinner label="Loading cluster statistics…" /> : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Users" value={stats?.user_count ?? '—'}
              hint={`${stats?.admin_count ?? 0} administrator(s)`} />
            <StatCard label="Files" value={stats?.file_count ?? '—'}
              hint="Across all accounts" />
            <StatCard label="Metadata size total" value={formatBytes(stats?.storage_used_bytes)}
              hint="Sum of recorded file sizes" accent="emerald" />
            <StatCard label="Storage adapter" value={hdfs?.adapter || '—'}
              hint={hdfs?.mode_label} accent={hdfs?.adapter === 'mock' ? 'amber' : 'brand'} />
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">HDFS status</h2>
              <StatusPill value={hdfs?.healthy} />
            </div>
            <p className="mt-2 text-sm text-slate-600">{hdfs?.message}</p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">NameNode URL</dt>
                <dd className="mt-0.5 break-all font-medium text-slate-700">
                  {hdfs?.namenode_url || 'not applicable'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">HDFS root</dt>
                <dd className="mt-0.5 font-medium text-slate-700">{hdfs?.root || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">NameNode latency</dt>
                <dd className="mt-0.5 font-medium text-slate-700">
                  {hdfs?.latency_ms != null ? `${hdfs.latency_ms} ms` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">DataNodes (live / dead)</dt>
                <dd className="mt-0.5 font-medium text-slate-700">
                  {hdfs?.datanodes?.available
                    ? `${hdfs.datanodes.live ?? '?'} / ${hdfs.datanodes.dead ?? '?'}`
                    : 'unknown'}
                </dd>
              </div>
            </dl>
            {!hdfs?.datanodes?.available && hdfs?.datanodes?.reason && (
              <p className="mt-2 text-xs text-slate-500">{hdfs.datanodes.reason}</p>
            )}
          </div>

          <div className="card overflow-hidden">
            <div className="border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-800">Users</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Username</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Files</th>
                    <th className="px-4 py-3">Used</th>
                    <th className="hidden px-4 py-3 md:table-cell">Registered</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-700">
                        {item.username}
                        {item.id === user?.id && <span className="ml-2 text-xs text-slate-400">(you)</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={item.role === 'admin'
                          ? 'rounded bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700'
                          : 'rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600'}>
                          {item.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{item.file_count}</td>
                      <td className="px-4 py-3 text-slate-500">{formatBytes(item.storage_used_bytes)}</td>
                      <td className="hidden px-4 py-3 text-slate-500 md:table-cell">
                        {formatDate(item.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button type="button" className="btn-secondary !py-1.5"
                          disabled={item.id === user?.id}
                          title={item.id === user?.id ? 'You cannot change your own role' : undefined}
                          onClick={() => setRoleTarget(item)}>
                          {item.role === 'admin' ? 'Demote' : 'Promote'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Audit trail</h2>
              <select className="input sm:w-64" value={auditFilter}
                onChange={(e) => setAuditFilter(e.target.value)}>
                <option value="">All events</option>
                <option value="login">login</option>
                <option value="login_failed">login_failed</option>
                <option value="user_register">user_register</option>
                <option value="file_upload">file_upload</option>
                <option value="file_download">file_download</option>
                <option value="file_delete">file_delete</option>
                <option value="admin_role_change">admin_role_change</option>
              </select>
            </div>
            {audit.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">No audit events recorded for this filter.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">When</th>
                      <th className="px-4 py-3">Event</th>
                      <th className="px-4 py-3">Actor</th>
                      <th className="hidden px-4 py-3 sm:table-cell">Source</th>
                      <th className="px-4 py-3">Detail</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {audit.map((event) => (
                      <tr key={event.id}>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                          {formatDate(event.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={event.success
                            ? 'rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700'
                            : 'rounded bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700'}>
                            {event.event_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{event.actor_username || '—'}</td>
                        <td className="hidden px-4 py-3 text-slate-500 sm:table-cell">
                          {event.source_ip || '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-500">{event.detail || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(roleTarget)}
        title={roleTarget?.role === 'admin' ? 'Remove administrator access?' : 'Grant administrator access?'}
        message={roleTarget
          ? `${roleTarget.username} will ${roleTarget.role === 'admin' ? 'lose' : 'gain'} access to all administrative endpoints.`
          : ''}
        confirmLabel="Change role"
        busy={busy}
        onConfirm={applyRole}
        onCancel={() => setRoleTarget(null)}
      />
    </div>
  );
}
