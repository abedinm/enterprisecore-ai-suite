import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, Mail, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { ssoApi } from '../../lib/sso';
import toast from 'react-hot-toast';

/**
 * Confirmation page shown after a user requests a magic-link email.
 * The email being targeted is passed via location state — falls back
 * to a generic message if the user navigated here directly.
 */
export function MagicLinkPage() {
  const location = useLocation();
  const state = location.state as { email?: string } | null;
  const email = state?.email ?? '';
  const [resending, setResending] = useState(false);

  async function resend() {
    if (!email) {
      toast.error('No email on file for this session. Use a different email.');
      return;
    }
    setResending(true);
    try {
      await ssoApi.requestMagicLink({ email, purpose: 'login' });
      toast.success('We sent another link');
    } catch {
      toast.error('Could not resend. Try again in a minute.');
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 text-ink">
      <div className="w-full max-w-md">
        <div className="ec-card space-y-4 p-6 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <Mail size={22} />
          </div>
          <h1 className="text-xl font-semibold">Check your email</h1>
          <p className="text-sm text-ink-muted">
            We&apos;ve sent a sign-in link {email ? <>to <strong className="text-ink">{email}</strong></> : 'to the address you provided'}.
            It expires in 15 minutes.
          </p>
          <div className="flex flex-col gap-2 pt-2">
            <button
              className="ec-btn-secondary w-full"
              onClick={resend}
              disabled={resending}
              data-testid="magic-link-resend"
            >
              <RefreshCw size={16} /> {resending ? 'Resending…' : 'Resend link'}
            </button>
            <Link to="/login" className="ec-btn-secondary w-full justify-center">
              <ArrowLeft size={16} /> Use a different email
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
