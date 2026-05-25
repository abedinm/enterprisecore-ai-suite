# Runbook — Tenant cannot log in

## Symptoms

- Customer ticket: "I can't log in" / "Wrong password but I know it's correct."
- 4xx spike on `/api/v1/auth/login` for one `tenant_id` slug.
- Log: `auth.login.user_not_found` / `auth.login.bad_password` / `auth.login.tenant_disabled` / `auth.login.locked`.

## Severity

- **Sev 3** for a single user.
- **Sev 2** for a single tenant (all users locked out).
- **Sev 1** if multiple tenants are affected (auth service issue) — see `sso-login-failing.md`.

## Immediate mitigation

Decision tree:

```
Is the tenant disabled / suspended?
  → Look up: SELECT slug, status FROM tenants WHERE slug='...';
  → If status != 'active': resume per customer-success approval.

Is the user locked out (rate limit / failed attempts)?
  → Look up: SELECT email, locked_until FROM users WHERE email='...';
  → If locked_until > now(): clear via admin endpoint.

Is the user password hash valid?
  → Try the password reset flow ourselves to confirm email delivery works.

Is SSO required and the user is trying password login?
  → Check tenant SSO settings; advise customer.

Is the tenant on an SSO outage?
  → Issue a temporary magic link (see sso-login-failing.md).
```

Useful commands:

```bash
# Unlock a user
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://app.example.com/api/v1/admin/users/$USER_ID/unlock"

# Resume a suspended tenant
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://app.example.com/api/v1/admin/tenants/$TENANT_ID/resume"

# Issue a one-time magic link
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://app.example.com/api/v1/admin/magic-link" \
  -d "{\"email\":\"$EMAIL\",\"tenant_id\":\"$TENANT_ID\"}"
```

## Root cause investigation

Common scenarios:

- **Account locked from brute-force protection.** Check `users.locked_until`. Default lockout is 15 minutes after 5 failed attempts.
- **Tenant suspended for unpaid invoice.** Check `tenants.status='suspended'` and `subscriptions.status='past_due'`.
- **User invitation never accepted.** `SELECT accepted_at FROM tenant_invitations WHERE email='...'`. If null, resend invite.
- **Email mismatch** — customer signed up with `Foo@Example.com` but is trying `foo@example.com`. Our table is lowercase-normalised; login should be too. If it isn't, that's a bug.
- **Cookie domain mismatch.** Customer is on `app.example.com` but cookies are set for `example.com`. See `docs/SELF_HOSTING.md` cookie domain section.
- **Hostname routing.** Customer is on `acme.example.com` but the tenant slug is `acme-corp`. Check `tenants.subdomain` vs requested hostname.

## Permanent fix

- Ensure password-reset email is reachable from the user's mail provider — track in our SES bounce dashboard.
- Make lockout duration configurable per tenant (high-security tenants want longer).
- Provide a self-service unlock for tenant admins on their own org users.

## Postmortem checklist

- [ ] How many users were unable to log in and for how long?
- [ ] Was the root cause customer-side or our side?
- [ ] Did the customer admin have the tools they needed?
- [ ] Update FAQ in `docs/USER_MANUAL.md` if a common confusion.
