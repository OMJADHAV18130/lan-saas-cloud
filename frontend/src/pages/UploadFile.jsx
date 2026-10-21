import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { errorOf, filesApi, healthApi } from '../api/client';
import {
  ErrorAlert, PageHeader, ProgressBar, SuccessAlert,
} from '../components/ui';
import { formatBytes } from '../utils/format';

export default function UploadFile() {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [selected, setSelected] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [maxBytes, setMaxBytes] = useState(null);

  useEffect(() => {
    healthApi.health()
      .then(({ data }) => setMaxBytes(data.max_upload_bytes))
      .catch(() => setMaxBytes(null));
  }, []);

  const choose = useCallback((file) => {
    setError(null);
    setNotice(null);
    setProgress(0);
    if (!file) {
      setSelected(null);
      return;
    }
    if (file.size === 0) {
      setError({ message: 'Empty files are not accepted.' });
      return;
    }
    if (maxBytes && file.size > maxBytes) {
      setError({
        message: `"${file.name}" is ${formatBytes(file.size)} but the server limit is ${formatBytes(maxBytes)} per file.`,
      });
      return;
    }
    setSelected(file);
  }, [maxBytes]);

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) choose(file);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!selected) {
      setError({ message: 'Choose a file first.' });
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    const form = new FormData();
    form.append('file', selected, selected.name);
    try {
      const { data } = await filesApi.upload(form, setProgress);
      setNotice(`"${data.file.original_name}" (${formatBytes(data.file.size_bytes)}) is stored in HDFS.`);
      setSelected(null);
      if (inputRef.current) inputRef.current.value = '';
      setTimeout(() => navigate('/files'), 1200);
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title="Upload File"
        subtitle="The controller streams the file to HDFS; only metadata is kept in SQLite." />

      <div className="mb-4 space-y-3">
        {error && <ErrorAlert error={error} onDismiss={() => setError(null)} />}
        {notice && <SuccessAlert message={notice} onDismiss={() => setNotice(null)} />}
      </div>

      <form onSubmit={submit} className="card p-6">
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
            dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50 hover:border-brand-400'
          }`}
        >
          <svg className="h-8 w-8 text-brand-500" fill="none" viewBox="0 0 24 24"
            stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
          </svg>
          <p className="text-sm font-medium text-slate-700">
            Drag a file here, or click to browse
          </p>
          <p className="text-xs text-slate-500">
            {maxBytes ? `Maximum ${formatBytes(maxBytes)} per file` : 'Server limit is applied when the upload starts'}
          </p>
          <input ref={inputRef} type="file" className="hidden"
            onChange={(e) => choose(e.target.files?.[0])} />
        </div>

        {selected && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3">
            <p className="text-sm font-medium text-slate-700">{selected.name}</p>
            <p className="mt-0.5 text-xs text-slate-500">
              {formatBytes(selected.size)} · {selected.type || 'unknown type'}
            </p>
          </div>
        )}

        {busy && (
          <div className="mt-4">
            <ProgressBar percent={progress} label="Uploading to HDFS…" />
            <p className="mt-1 text-xs text-slate-500">
              The controller is writing the object to a DataNode. Do not close this page.
            </p>
          </div>
        )}

        <div className="mt-6 flex items-center justify-between">
          <Link to="/files" className="btn-secondary">Cancel</Link>
          <button type="submit" className="btn-primary" disabled={busy || !selected}>
            {busy ? 'Uploading…' : 'Upload to HDFS'}
          </button>
        </div>
      </form>
    </div>
  );
}
