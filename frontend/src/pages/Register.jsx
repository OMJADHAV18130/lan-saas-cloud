import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { errorOf } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ErrorAlert } from '../components/ui';
import { AuthShell } from './Login';

const RULES = [
  { test: (v) => v.length >= 8, label: 'At least 8 characters' },
  { test: (v) => /[A-Za-z]/.test(v) && /\d/.test(v), label: 'Contains a letter and a digit' },
  { test: (v) => /^[A-Za-z0-9_.-]{3,32}$/.test(v), label: 'Username: 3–32 letters, digits, _ . -' },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', password: '', confirm: '' });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const usernameOk = RULES[2].test(form.username);
  const passwordOk = RULES[0].test(form.password) && RULES[1].test(form.password);
  const match = form.password === form.confirm && form.password.length > 0;

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (!usernameOk) {
      setError({ message: 'Username must be 3–32 characters using letters, digits, _ . -' });
      return;
    }
    if (!passwordOk) {
      setError({ message: 'Password must be at least 8 characters and contain a letter and a digit.' });
      return;
    }
    if (!match) {
      setError({ message: 'The two passwords do not match.' });
      return;
    }
    setBusy(true);
    try {
      await register(form.username.trim(), form.password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorOf(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="You get a private folder inside the cluster"
      footer={<>Already registered? <Link className="font-medium text-brand-600 hover:underline"
        to="/login">Sign in</Link></>}
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
            autoComplete="new-password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="confirm">Confirm password</label>
          <input id="confirm" type="password" className="input"
            autoComplete="new-password" value={form.confirm}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
        </div>
        <ul className="space-y-1 text-xs">
          {RULES.slice(0, 2).map((rule) => (
            <li key={rule.label}
              className={rule.test(form.password) ? 'text-emerald-600' : 'text-slate-500'}>
              {rule.test(form.password) ? '✓' : '•'} {rule.label}
            </li>
          ))}
          {form.confirm && (
            <li className={match ? 'text-emerald-600' : 'text-rose-600'}>
              {match ? '✓ Passwords match' : '• Passwords do not match'}
            </li>
          )}
        </ul>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  );
}
