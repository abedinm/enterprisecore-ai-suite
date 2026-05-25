# Runbook — SSO login failing

## Symptoms

- Customer ticket: "Nobody at our company can log in via SSO."
- 4xx spike on `/api/v1/auth/oidc/callback` or `/api/v1/auth/saml/acs`.
- Logs: `oidc.token_exchange_failed` / `saml.signature_validation_failed` / `saml.audience_mismatch`.
- `ec_sso_login_failures_total` climbing for a single `tenant_id`.

## Severity

- **Sev 2** for one tenant.
- **Sev 1** if it affects all tenants (likely our IdP integration regression).

## Immediate mitigation

1. Confirm whether the issue is single-tenant or platform-wide.

   ```promql
   topk(5,
     sum by (tenant_id) (rate(ec_sso_login_failures_total[15m]))
   )
   ```

2. For a single tenant, fall back to email + password (or magic link) so users are not locked out:

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/tenants/$TENANT_ID/sso/disable_temp"
   ```

3. Generate a one-time magic link for the tenant admin so they can fix their IdP config:

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/magic-link" \
     -d "{\"email\": \"$ADMIN_EMAIL\", \"tenant_id\": \"$TENANT_ID\"}"
   ```

## Root cause investigation

For OIDC:

```bash
# Discovery doc reachable?
curl -fsS "$ISSUER/.well-known/openid-configuration" | jq .

# JWKS keys
curl -fsS "$JWKS_URI" | jq .keys[].kid

# Decode the latest failed id_token (from logs)
echo "$ID_TOKEN" | jwt decode -
```

Common OIDC issues:

- IdP rotated their signing key but our JWKS cache is stale. Force refresh: `redis-cli DEL "oidc:jwks:$tenant"`.
- IdP `iss` URL has a trailing slash that doesn't match our stored issuer.
- IdP issued a token with `aud` that doesn't match our `client_id`.
- Customer recently rotated their OIDC client secret without updating EnterpriseCore.

For SAML:

```bash
# Validate the SAML response
xmlsec1 --verify --pubkey-cert-pem /etc/ec/sso/$tenant-idp.crt response.xml

# Check the metadata expiry
xmllint --xpath "//*[local-name()='EntityDescriptor']/@validUntil" idp-metadata.xml
```

Common SAML issues:

- IdP metadata expired — re-upload via `POST /api/v1/sso/saml/metadata`.
- IdP rotated their signing cert.
- Clock skew between our NotBefore / NotOnOrAfter assertion and the IdP.
- AudienceRestriction doesn't match our SP entity ID.

For SCIM:

- Most failures are 401 from a rotated bearer token. Rotate in our admin UI and ask customer to update.

## Permanent fix

- Implement automatic JWKS rotation refresh on first 4xx with `kid_unknown`.
- Add an `SsoMetadataExpiringSoon` alert (>30 days from `validUntil`).
- Document customer-facing IdP setup more explicitly in `docs/SELF_HOSTING.md` / SSO section.

## Postmortem checklist

- [ ] How long was the tenant unable to log in?
- [ ] Was the temp-disable mechanism used?
- [ ] Could a customer admin have self-served the fix?
- [ ] Add a unit test that reproduces the failure mode.
