import { useCallback, useEffect, useState } from 'react';
import { healthApi } from '../api/client';

const POLL_MS = 30000;

/**
 * Storage indicator shown in the sidebar.
 * Values come from GET /api/storage/status - nothing is simulated:
 *   green  -> WebHDFS adapter + NameNode reachable
 *   amber  -> mock adapter active (local disk, NOT HDFS) or degraded health
 *   red    -> storage unreachable / errors
 *   grey   -> not checked yet
 */
export default function StorageStatusBadge() {
  const [state, setState] = useState({ phase: 'loading', message: 'Checking storage…' });

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await healthApi.storageStatus();
      if (data.adapter === 'mock') {
        setState({ phase: 'mock', message: data.message });
      } else if (data.healthy === true) {
        setState({ phase: 'ok', message: data.message });
      } else {
        setState({ phase: 'down', message: data.message || 'Storage is unavailable.' });
      }
    } catch (error) {
      const message = error?.normalised?.message || 'Storage status could not be fetched.';
      setState({ phase: 'down', message });
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const styles = {
    loading: { dot: 'bg-slate-300', text: 'Checking storage…', box: 'bg-slate-50 text-slate-500' },
    ok: { dot: 'bg-emerald-500', text: 'HDFS connected', box: 'bg-emerald-50 text-emerald-700' },
    mock: { dot: 'bg-amber-500', text: 'Mock storage (no HDFS)', box: 'bg-amber-50 text-amber-700' },
    down: { dot: 'bg-rose-500', text: 'Storage unavailable', box: 'bg-rose-50 text-rose-700' },
  }[state.phase];

  return (
    <div
      title={state.message}
      className={`mx-4 mb-4 rounded-lg px-3 py-2 text-xs font-medium ${styles.box}`}
    >
      <span className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${styles.dot}
          ${state.phase === 'loading' ? 'animate-pulse' : ''}`} />
        {styles.text}
      </span>
      <span className="mt-1 block leading-snug opacity-80">{state.message}</span>
    </div>
  );
}
