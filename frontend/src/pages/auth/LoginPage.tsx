import { FormEvent, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LogIn, Sparkles } from 'lucide-react';
import { useAuthStore } from '../../store/auth';

export function LoginPage() {
  const { login } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const redirect = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/';
  const [email, setEmail] = useState('admin@local');
  const [password, setPassword] = useState('ChangeMe123!');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await login(email, password);
      navigate(redirect, { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Could not sign in. Check the backend is running on http://127.0.0.1:8765.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 text-ink">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Sparkles size={22} />
          </div>
          <div>
            <p className="text-lg font-semibold">EnterpriseCore AI Suite</p>
            <p className="text-xs text-ink-muted">Offline-first business command center</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="ec-card space-y-4 p-6">
          <div>
            <h1 className="text-xl font-semibold">Sign in</h1>
            <p className="mt-1 text-sm text-ink-muted">Welcome back. Enter your credentials to continue.</p>
          </div>
          <div>
            <label className="ec-label" htmlFor="email">Email</label>
            <input
              id="email"
              className="ec-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="ec-label" htmlFor="password">Password</label>
            <input
              id="password"
              className="ec-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? (
            <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300">
              {error}
            </p>
          ) : null}
          <button className="ec-btn-primary w-full" disabled={submitting} type="submit">
            <LogIn size={16} />
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
          <p className="text-center text-xs text-ink-muted">
            No account?{' '}
            <Link to="/register" className="text-brand-600 hover:underline">
              Create one
            </Link>
          </p>
        </form>
        <p className="mt-4 text-center text-[11px] text-ink-subtle">
          Default admin: <span className="font-mono">admin@local</span> / <span className="font-mono">ChangeMe123!</span>
        </p>
      </div>
    </div>
  );
}
