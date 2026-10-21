import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { errorOf, filesApi } from '../api/client';
import {
  ConfirmDialog, EmptyState, ErrorAlert, PageHeader, Spinner, SuccessAlert,
} from '../components/ui';
import { fileExtension, formatBytes, formatDate } from '../utils/format';

export default function MyFiles() {
  const [files, setFiles] = useState([]);
  const [meta, setMeta] = useState({ total: 0, storage_used_bytes: 0, storage_quota_bytes: 0 });
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [order, setOrder] = useState('desc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await filesApi.list({
        q: search.trim() || undefined,
        sort_by: sortBy,
        order,
      });
      setFiles(data.items);
      setMeta(data);
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setLoading(false);
    }
  }, [search, sortBy, order]);

  // Debounce the search box so typing does not spam the controller.
  useEffect(() => {
    const id = setTimeout(load, 300);
    return () => clearTimeout(id);
  }, [load]);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setError(null);
    try {
      await filesApi.remove(pendingDelete.id);
      setNotice(`"${pendingDelete.original_name}" was deleted from HDFS and the database.`);
      setPendingDelete(null);
      await load();
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setDeleting(false);
    }
  };

  const download = async (file) => {
    setDownloadingId(file.id);
    setError(null);
    try {
      await filesApi.download(file.id, file.original_name);
      setNotice(`Downloaded "${file.original_name}".`);
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setDownloadingId(null);
    }
  };

  const summary = useMemo(
    () => `${meta.total} file${meta.total === 1 ? '' : 's'} · ${formatBytes(meta.storage_used_bytes)} of ${formatBytes(meta.storage_quota_bytes)} used`,
    [meta]
  );

  return (
    <div>
      <PageHeader title="My Files" subtitle={summary}
        actions={<Link to="/upload" className="btn-primary">Upload file</Link>} />

      <div className="mb-4 space-y-3">
        {error && <ErrorAlert error={error} onDismiss={() => setError(null)} />}
        {notice && <SuccessAlert message={notice} onDismiss={() => setNotice(null)} />}
      </div>

      <div className="card mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="flex-1">
          <label className="label" htmlFor="search">Search by filename</label>
          <input id="search" className="input" placeholder="e.g. report"
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="sort">Sort by</label>
          <select id="sort" className="input" value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}>
            <option value="date">Upload date</option>
            <option value="name">Filename</option>
            <option value="size">Size</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="order">Order</label>
          <select id="order" className="input" value={order}
            onChange={(e) => setOrder(e.target.value)}>
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </div>
      </div>

      {loading ? (
        <Spinner label="Loading files from the controller…" />
      ) : files.length === 0 ? (
        <EmptyState
          title={search ? 'No files match your search' : 'You have no files yet'}
          hint={search
            ? 'Try a different filename or clear the search box.'
            : 'Files you upload are stored in HDFS inside your private directory.'}
          action={!search && <Link to="/upload" className="btn-primary mt-3">Upload file</Link>}
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Filename</th>
                  <th className="hidden px-4 py-3 sm:table-cell">Type</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="hidden px-4 py-3 md:table-cell">Uploaded</th>
                  <th className="hidden px-4 py-3 lg:table-cell">SHA-256</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {files.map((file) => (
                  <tr key={file.id} className="hover:bg-slate-50">
                    <td className="max-w-[16rem] truncate px-4 py-3 font-medium text-slate-700"
                      title={file.original_name}>{file.original_name}</td>
                    <td className="hidden px-4 py-3 sm:table-cell">
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                        {fileExtension(file.original_name)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{formatBytes(file.size_bytes)}</td>
                    <td className="hidden px-4 py-3 text-slate-500 md:table-cell">
                      {formatDate(file.created_at)}
                    </td>
                    <td className="hidden px-4 py-3 lg:table-cell font-mono text-xs text-slate-400"
                      title={file.sha256}>{file.sha256.slice(0, 12)}…</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button type="button" className="btn-secondary !py-1.5"
                          onClick={() => download(file)} disabled={downloadingId === file.id}>
                          {downloadingId === file.id ? 'Downloading…' : 'Download'}
                        </button>
                        <button type="button" className="btn-danger !py-1.5"
                          onClick={() => setPendingDelete(file)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this file?"
        message={pendingDelete
          ? `"${pendingDelete.original_name}" will be removed from HDFS and its metadata deleted. This cannot be undone.`
          : ''}
        confirmLabel="Delete file"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
