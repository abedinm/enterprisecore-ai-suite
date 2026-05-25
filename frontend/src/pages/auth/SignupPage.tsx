import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Building2, ShieldCheck, Sparkles, UserPlus } from 'lucide-react';
import toast from 'react-hot-toast';
import { tenantApi, tenantSlug, passwordStrength } from '../../lib/tenant';
import { useAuthStore } from '../../store/auth';

type Step = 1 | 2;

type FieldErrors = Partial<Record<
  'name' | 'slug' | 'primary_contact_email' | 'admin_email' | 'admin_password' | 'admin_full_name',
  string
>>;

export function SignupPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [step, setStep] = useState<Step>(1);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});

  // Step 1
  const [name, setName] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [slug, setSlug] = useState('');
  const [contactEmail, setContactEmail] = useState('');

  // Step 2
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [adminFullName, setAdminFullName] = useState('');
  const [tos, setTos] = useState(false);

  const strength = passwordStrength(adminPassword);

  function onChangeName(value: string) {
    setName(value);
    if (!slugTouched) setSlug(tenantSlug(value));
  }

  function goToStep2(event: FormEvent) {
    event.preventDefault();
    const next: FieldErrors = {};
    if (name.trim().length < 2) next.name = 'Name is required';
    if (!/^[a-z0-9][a-z0-9-]*$/.test(slug) || slug.length < 2) {
      next.slug = 'Use lowercase letters, numbers, and dashes';
    }
    if (contactEmail && !/^.+@.+\..+$/.test(contactEmail)) {
      next.primary_contact_email = 'Enter a valid email';
    }
    setErrors(next);
    if (Object.keys(next).length === 0) setStep(2);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next: FieldErrors = {};
    if (adminFullName.trim().length < 2) next.admin_full_name = 'Your full name is required';
    if (!/^.+@.+\..+$/.test(adminEmail)) next.admin_email = 'Enter a valid email';
    if (strength.score < 2) next.admin_password = 'Choose a stronger password (10+ chars, mix of cases, digits)';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (!tos) {
      toast.error('You must accept the terms of service to continue.');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await tenantApi.signup({
        name: name.trim(),
        slug,
        admin_email: adminEmail.trim().toLowerCase(),
        admin_password: adminPassword,
        admin_full_name: adminFullName.trim(),
        primary_contact_email: contactEmail || null,
      });
      await setSession(resp.access_token, resp.refresh_token, resp.tenant);
      toast.success('Welcome to EnterpriseCore');
      navigate('/', { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        if (detail.toLowerCase().includes('slug')) setErrors({ slug: detail });
        else if (detail.toLowerCase().includes('email')) setErrors({ admin_email: detail });
        else toast.error(detail);
      } else {
        toast.error('Could not complete signup. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 py-10 text-ink">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Sparkles size={22} />
          </div>
          <div>
            <p className="text-lg font-semibold">EnterpriseCore AI Suite</p>
            <p className="text-xs text-ink-muted">Create your workspace in two steps</p>
          </div>
        </div>

        <div className="ec-card space-y-4 p-6">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold">
              {step === 1 ? 'Tell us about your organization' : 'Create your admin account'}
            </h1>
            <span className="ec-badge-green text-[10px]">Step {step}/2</span>
          </div>

          {step === 1 ? (
            <form onSubmit={goToStep2} className="space-y-4">
              <div>
                <label className="ec-label" htmlFor="org-name">
                  <Building2 size={13} className="inline mr-1 -mt-0.5" />
                  Organization name
                </label>
                <input
                  id="org-name"
                  className="ec-input"
                  value={name}
                  onChange={(e) => onChangeName(e.target.value)}
                  required
                  autoFocus
                  data-testid="signup-name"
                />
                {errors.name ? <p className="mt-1 text-xs text-rose-600">{errors.name}</p> : null}
              </div>
              <div>
                <label className="ec-label" htmlFor="org-slug">Workspace URL slug</label>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-ink-muted">/</span>
                  <input
                    id="org-slug"
                    className="ec-input"
                    value={slug}
                    onChange={(e) => {
                      setSlugTouched(true);
                      setSlug(e.target.value.toLowerCase());
                    }}
                    pattern="[a-z0-9][a-z0-9\-]*"
                    minLength={2}
                    maxLength={80}
                    required
                    data-testid="signup-slug"
                  />
                </div>
                <p className="mt-1 text-[11px] text-ink-subtle">Lowercase letters, numbers, and dashes.</p>
                {errors.slug ? <p className="mt-1 text-xs text-rose-600">{errors.slug}</p> : null}
              </div>
              <div>
                <label className="ec-label" htmlFor="contact-email">Primary contact email (optional)</label>
                <input
                  id="contact-email"
                  className="ec-input"
                  type="email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  data-testid="signup-contact-email"
                />
                {errors.primary_contact_email ? (
                  <p className="mt-1 text-xs text-rose-600">{errors.primary_contact_email}</p>
                ) : null}
              </div>
              <button className="ec-btn-primary w-full" type="submit" data-testid="signup-next">
                Continue <ArrowRight size={16} />
              </button>
            </form>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label className="ec-label" htmlFor="admin-name">Your full name</label>
                <input
                  id="admin-name"
                  className="ec-input"
                  value={adminFullName}
                  onChange={(e) => setAdminFullName(e.target.value)}
                  required
                  data-testid="signup-admin-name"
                />
                {errors.admin_full_name ? (
                  <p className="mt-1 text-xs text-rose-600">{errors.admin_full_name}</p>
                ) : null}
              </div>
              <div>
                <label className="ec-label" htmlFor="admin-email">Admin email</label>
                <input
                  id="admin-email"
                  className="ec-input"
                  type="email"
                  autoComplete="email"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  required
                  data-testid="signup-admin-email"
                />
                {errors.admin_email ? (
                  <p className="mt-1 text-xs text-rose-600">{errors.admin_email}</p>
                ) : null}
              </div>
              <div>
                <label className="ec-label" htmlFor="admin-password">Password</label>
                <input
                  id="admin-password"
                  className="ec-input"
                  type="password"
                  autoComplete="new-password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  required
                  minLength={10}
                  data-testid="signup-admin-password"
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
                {errors.admin_password ? (
                  <p className="mt-1 text-xs text-rose-600">{errors.admin_password}</p>
                ) : null}
              </div>
              <label className="flex items-start gap-2 text-xs text-ink-muted">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={tos}
                  onChange={(e) => setTos(e.target.checked)}
                  data-testid="signup-tos"
                />
                <span>
                  I agree to the <a className="text-brand-600 hover:underline" href="/terms" target="_blank" rel="noreferrer">terms of service</a>
                  {' '}and <a className="text-brand-600 hover:underline" href="/privacy" target="_blank" rel="noreferrer">privacy policy</a>.
                </span>
              </label>

              <div className="flex gap-2">
                <button
                  type="button"
                  className="ec-btn-secondary"
                  onClick={() => setStep(1)}
                  disabled={submitting}
                >
                  <ArrowLeft size={16} /> Back
                </button>
                <button
                  className="ec-btn-primary flex-1"
                  type="submit"
                  disabled={submitting}
                  data-testid="signup-submit"
                >
                  <UserPlus size={16} />
                  {submitting ? 'Creating workspace…' : 'Create workspace'}
                </button>
              </div>
            </form>
          )}
        </div>

        <p className="mt-4 text-center text-xs text-ink-muted">
          <ShieldCheck size={11} className="inline -mt-0.5" /> Start your 14-day free trial. No credit card required.
        </p>
        <p className="mt-2 text-center text-xs text-ink-muted">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-600 hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
