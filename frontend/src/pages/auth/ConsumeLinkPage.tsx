import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Mail } from 'lucide-react';
import { ssoApi } from '../../lib/sso';
import { useAuthStore } from '../../store/auth';

/**
 * Lands at /auth/consume?token=... — the magic-link email link target.
 * Exchanges the token for an access/refresh pair, drops them into the
 * auth store, then sends the user to the dashboard.
 */
export function ConsumeLinkPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [state, setState] = useState<'consuming' | 'ok' | 'error'>('consuming');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!token) {
        setState('error');
        setErrorMsg('No token provided.');
        return;
      }
      try {
        const resp = await ssoApi.consumeMagicLink(token);
        if (cancelled) return;
        if (resp.access_token && resp.refresh_token) {
          await setSession(resp.access_token, resp.refresh_token);
          setState('ok');
          navigate('/', { replace: true });
        } else if (resp.reset_token) {
          // Password-reset flow — out of scope for the SPA today.
          navigate(`/login?reset=${encodeURIComponent(resp.reset_token)}`, { replace: true });
        } else {
          setState('error');
          setErrorMsg('Unexpected response from server.');
        }
      } catch (err: any) {
        if (cancelled) return;
        setState('error');
        setErrorMsg(err?.response?.data?.detail ?? 'Link expired or already used.');
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [token, setSession, navigate]);

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 text-ink">
      <div className="w-full max-w-md">
        <div className="ec-card space-y-4 p-6 text-center">
          {state === 'consuming' ? (
            <>
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
                <Mail size={22} />
              </div>
              <h1 className="text-xl font-semibold">Signing you in…</h1>
              <p className="text-sm text-ink-muted">Hang tight while we verify your link.</p>
            </>
          ) : state === 'ok' ? (
            <>
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600">
                <CheckCircle2 size={22} />
              </div>
              <h1 className="text-xl font-semibold">Success</h1>
              <p className="text-sm text-ink-muted">Redirecting to your dashboard…</p>
            </>
          ) : (
            <>
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-rose-500/10 text-rose-600">
                <AlertTriangle size={22} />
              </div>
              <h1 className="text-xl font-semibold">Couldn&apos;t sign you in</h1>
              <p className="text-sm text-ink-muted">{errorMsg}</p>
              <Link to="/login" className="ec-btn-primary w-full justify-center">
                Request a new link
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
