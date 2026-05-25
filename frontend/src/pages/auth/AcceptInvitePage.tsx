import { FormEvent, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, MailCheck, UserPlus } from 'lucide-react';
import toast from 'react-hot-toast';
import { tenantApi, passwordStrength } from '../../lib/tenant';
import { useAuthStore } from '../../store/auth';

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const strength = passwordStrength(password);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (password !== confirmPw) {
      setError('Passwords do not match.');
      return;
    }
    if (strength.score < 2) {
      setError('Choose a stronger password (10+ chars, mix of cases, digits).');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await tenantApi.acceptInvite({
        token,
        password,
        full_name: fullName.trim(),
      });
      await setSession(resp.access_token, resp.refresh_token, resp.tenant);
      toast.success(`Welcome to ${resp.tenant.name}`);
      navigate('/', { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not accept this invite.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="grid min-h-screen place-items-center bg-surface px-4 text-ink">
        <div className="w-full max-w-md">
          <div className="ec-card space-y-4 p-6 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-rose-500/10 text-rose-600">
              <AlertTriangle size={22} />
            </div>
            <h1 className="text-xl font-semibold">Missing invite token</h1>
            <p className="text-sm text-ink-muted">This invite link is incomplete.</p>
            <Link to="/login" className="ec-btn-primary w-full justify-center">Go to sign-in</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 text-ink">
      <div className="w-full max-w-md">
        <div className="ec-card space-y-4 p-6">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
              <MailCheck size={22} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">You&apos;re invited</h1>
              <p className="text-xs text-ink-muted">Set up your account to join the team.</p>
            </div>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="ec-label" htmlFor="invite-name">Full name</label>
              <input
                id="invite-name"
                className="ec-input"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoFocus
                data-testid="invite-full-name"
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="invite-password">Password</label>
              <input
                id="invite-password"
                className="ec-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={10}
                data-testid="invite-password"
              />
              <div className="mt-2 flex items-center gap-2">
                <div className="flex gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <span
                      key={i}
                      className={`h-1.5 w-8 rounded ${i < strength.score ? 'bg-brand-600' : 'bg-surface-muted'}`}
                    />
                  ))}
                </div>
                <span className="text-[11px] text-ink-subtle">{strength.label}</span>
              </div>
            </div>
            <div>
              <label className="ec-label" htmlFor="invite-password-confirm">Confirm password</label>
              <input
                id="invite-password-confirm"
                className="ec-input"
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                required
                data-testid="invite-password-confirm"
              />
            </div>
            {error ? (
              <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600">{error}</p>
            ) : null}
            <button className="ec-btn-primary w-full" type="submit" disabled={submitting} data-testid="invite-submit">
              <UserPlus size={16} /> {submitting ? 'Activating…' : 'Activate account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
