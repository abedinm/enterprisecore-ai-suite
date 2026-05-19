import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, UserPlus } from 'lucide-react';
import { useAuthStore } from '../../store/auth';

export function RegisterPage() {
  const { register } = useAuthStore();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm: '',
    department: '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (form.password.length < 10) {
      setError('Password must be at least 10 characters long.');
      return;
    }
    if (form.password !== form.confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await register({
        email: form.email,
        full_name: form.full_name,
        password: form.password,
        department: form.department || null,
      });
      navigate('/', { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Could not register. The backend may be unreachable.');
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
            <p className="text-xs text-ink-muted">Create your account</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="ec-card space-y-4 p-6">
          <div>
            <h1 className="text-xl font-semibold">Create account</h1>
            <p className="mt-1 text-sm text-ink-muted">New accounts are created with the Employee role by default. Admins can promote roles later.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="ec-label" htmlFor="full_name">Full name</label>
              <input
                id="full_name"
                className="ec-input"
                autoComplete="name"
                required
                minLength={2}
                value={form.full_name}
                onChange={(e) => set('full_name', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="department">Department</label>
              <input
                id="department"
                className="ec-input"
                value={form.department}
                onChange={(e) => set('department', e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="ec-label" htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              className="ec-input"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="ec-label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={10}
                className="ec-input"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="confirm">Confirm password</label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                minLength={10}
                className="ec-input"
                value={form.confirm}
                onChange={(e) => set('confirm', e.target.value)}
              />
            </div>
          </div>
          {error && (
            <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300">{error}</p>
          )}
          <button type="submit" className="ec-btn-primary w-full" disabled={submitting}>
            <UserPlus size={16} />
            {submitting ? 'Creating...' : 'Create account'}
          </button>
          <p className="text-center text-xs text-ink-muted">
            Already have an account?{' '}
            <Link to="/login" className="text-brand-600 hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
