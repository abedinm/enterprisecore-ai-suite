import { FormEvent, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { KeyRound, LogIn, Mail, ShieldCheck, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/auth';
import { oidcLoginUrl, samlLoginUrl, ssoApi } from '../../lib/sso';
import { LocaleSwitcher } from '../../components/LocaleSwitcher';

type AltMode = null | 'sso' | 'magic';

export function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const redirect = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/';
  const [email, setEmail] = useState('admin@local');
  const [password, setPassword] = useState('ChangeMe123!');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Alt sign-in modes
  const [altMode, setAltMode] = useState<AltMode>(null);
  const [ssoSlug, setSsoSlug] = useState('');
  const [ssoProto, setSsoProto] = useState<'oidc' | 'saml'>('oidc');
  const [magicEmail, setMagicEmail] = useState('');
  const [magicSubmitting, setMagicSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await login(email, password);
      navigate(redirect, { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || t('auth.loginError'));
    } finally {
      setSubmitting(false);
    }
  }

  function startSso(event: FormEvent) {
    event.preventDefault();
    if (!ssoSlug.trim()) {
      toast.error('Enter your organization slug');
      return;
    }
    const url = ssoProto === 'oidc' ? oidcLoginUrl(ssoSlug.trim(), redirect) : samlLoginUrl(ssoSlug.trim(), redirect);
    window.location.href = url;
  }

  async function requestMagicLink(event: FormEvent) {
    event.preventDefault();
    if (!magicEmail.trim()) return;
    setMagicSubmitting(true);
    try {
      await ssoApi.requestMagicLink({ email: magicEmail.trim().toLowerCase(), purpose: 'login' });
      navigate('/auth/magic-link/sent', { state: { email: magicEmail.trim().toLowerCase() } });
    } catch {
      toast.error('Could not send link. Try again shortly.');
    } finally {
      setMagicSubmitting(false);
    }
  }

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-surface px-4 py-10 text-ink">
      {/* Aurora floating blobs — non-interactive background. */}
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
        <div className="ec-blob ec-blob-1 -left-[10vw] top-[10vh]" />
        <div className="ec-blob ec-blob-2 right-[5vw] top-[40vh]" />
        <div className="ec-blob ec-blob-3 left-[30vw] -bottom-[10vh]" />
        <div className="absolute inset-0 bg-grid bg-grid-md opacity-[0.05]" />
      </div>
      <div className="w-full max-w-md animate-fade-in-up">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="relative grid h-11 w-11 place-items-center overflow-hidden rounded-xl bg-gradient-aurora text-white shadow-md">
              <Sparkles size={22} className="relative z-10 animate-float" />
              <div className="absolute inset-0 animate-gradient-x bg-[length:200%_200%] bg-gradient-aurora" />
            </div>
            <div>
              <p className="text-lg font-semibold">{t('app.title')}</p>
              <p className="text-xs text-ink-muted">{t('app.tagline')}</p>
            </div>
          </div>
          <LocaleSwitcher compact />
        </div>

        <p className="mb-3 text-center text-xs text-ink-muted">
          {t('auth.dontHaveAccount')}{' '}
          <Link to="/signup" className="text-brand-600 hover:underline" data-testid="login-signup-link">
            {t('auth.signUp')}
          </Link>
        </p>

        <form onSubmit={onSubmit} className="ec-card space-y-4 p-6">
          <div>
            <h1 className="text-xl font-semibold">{t('auth.signIn')}</h1>
            <p className="mt-1 text-sm text-ink-muted">{t('auth.welcome')}. {t('auth.welcomeSub')}</p>
          </div>
          <div>
            <label className="ec-label" htmlFor="email">{t('auth.email')}</label>
            <input
              id="email"
              className="ec-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              data-testid="login-email"
            />
          </div>
          <div>
            <label className="ec-label" htmlFor="password">{t('auth.password')}</label>
            <input
              id="password"
              className="ec-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              data-testid="login-password"
            />
          </div>
          {error ? (
            <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300">
              {error}
            </p>
          ) : null}
          <button className="ec-btn-primary w-full" disabled={submitting} type="submit" data-testid="login-submit">
            <LogIn size={16} />
            {submitting ? t('auth.signingIn') : t('auth.signIn')}
          </button>
        </form>

        {/* Alt sign-in panel */}
        <div className="mt-3 ec-card p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs text-ink-subtle">
            <span className="h-px flex-1 bg-border" />
            <span>or</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          {altMode === null ? (
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setAltMode('sso')}
                data-testid="login-sso"
              >
                <ShieldCheck size={16} /> SSO
              </button>
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setAltMode('magic')}
                data-testid="login-magic"
              >
                <Mail size={16} /> Email a link
              </button>
            </div>
          ) : altMode === 'sso' ? (
            <form onSubmit={startSso} className="space-y-3">
              <div>
                <label className="ec-label" htmlFor="sso-slug">Organization slug</label>
                <input
                  id="sso-slug"
                  className="ec-input"
                  value={ssoSlug}
                  onChange={(e) => setSsoSlug(e.target.value.toLowerCase())}
                  placeholder="acme"
                  required
                  data-testid="sso-slug"
                />
              </div>
              <div>
                <label className="ec-label">Provider</label>
                <div className="flex gap-2">
                  <label className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-surface-muted/30 px-3 py-2 text-sm">
                    <input
                      type="radio"
                      name="ssoProto"
                      checked={ssoProto === 'oidc'}
                      onChange={() => setSsoProto('oidc')}
                    />
                    OIDC
                  </label>
                  <label className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-surface-muted/30 px-3 py-2 text-sm">
                    <input
                      type="radio"
                      name="ssoProto"
                      checked={ssoProto === 'saml'}
                      onChange={() => setSsoProto('saml')}
                    />
                    SAML
                  </label>
                </div>
              </div>
              <div className="flex gap-2">
                <button type="button" className="ec-btn-secondary" onClick={() => setAltMode(null)}>
                  Back
                </button>
                <button type="submit" className="ec-btn-primary flex-1" data-testid="sso-continue">
                  <KeyRound size={16} /> Continue with SSO
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={requestMagicLink} className="space-y-3">
              <div>
                <label className="ec-label" htmlFor="magic-email">Your email</label>
                <input
                  id="magic-email"
                  className="ec-input"
                  type="email"
                  value={magicEmail}
                  onChange={(e) => setMagicEmail(e.target.value)}
                  required
                  data-testid="magic-email"
                />
              </div>
              <div className="flex gap-2">
                <button type="button" className="ec-btn-secondary" onClick={() => setAltMode(null)}>
                  Back
                </button>
                <button
                  type="submit"
                  className="ec-btn-primary flex-1"
                  disabled={magicSubmitting}
                  data-testid="magic-submit"
                >
                  <Mail size={16} /> {magicSubmitting ? 'Sending…' : 'Email me a link'}
                </button>
              </div>
            </form>
          )}
        </div>

        <p className="mt-4 text-center text-[11px] text-ink-subtle">
          Default admin: <span className="font-mono">admin@local</span> / <span className="font-mono">ChangeMe123!</span>
        </p>
      </div>
    </div>
  );
}
