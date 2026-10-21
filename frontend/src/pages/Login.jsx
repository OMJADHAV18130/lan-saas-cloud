import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { errorOf } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ErrorAlert } from '../components/ui';

export function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-base font-bold text-white">
            CS
          </div>
          <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
        </div>
        <div className="card p-6">{children}</div>
        {footer && <div className="mt-4 text-center text-sm text-slate-600">{footer}</div>}
      </div>
    </div>
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (!form.username.trim() || !form.password) {
      setError({ message: 'Enter your username and password.' });
      return;
    }
    setBusy(true);
    try {
      await login(form.username.trim(), form.password);
      navigate(location.state?.from || '/dashboard', { replace: true });
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Sign in to your cloud"
      subtitle="LAN-based SaaS cloud storage backed by Apache HDFS"
      footer={<>No account yet? <Link className="font-medium text-brand-600 hover:underline"
        to="/register">Create one</Link></>}
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <ErrorAlert error={error} onDismiss={() => setError(null)} />
        <div>
          <label className="label" htmlFor="username">Username</label>
          <input id="username" className="input" autoComplete="username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" className="input"
            autoComplete="current-password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="text-center text-xs text-slate-500">
          Credentials are sent to the Cloud Controller over HTTP. On a shared
          lab LAN, prefer the HTTPS setup described in the deployment guide.
        </p>
      </form>
    </AuthShell>
  );
}
