# Enterprise installation guide

EnterpriseCore ships in three deployment shapes. This document covers all of
them — how to choose, how to size, how to install, and what to harden after
the first boot.

For the security posture each install must satisfy in production, see
[SECURITY_HARDENING.md](SECURITY_HARDENING.md). For upgrades after the
initial install, see [UPGRADE_GUIDE.md](UPGRADE_GUIDE.md). For the disaster
recovery story, see [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

## Deployment shapes side-by-side

| Dimension                     | Desktop (.exe / .dmg / .AppImage)     | Self-hosted Kubernetes                       | SaaS (enterprisecore.com)            |
| ----------------------------- | ------------------------------------- | -------------------------------------------- | ------------------------------------ |
| Users per node                | 1 (single workstation)                | 10 – 10,000+ per cluster                     | 1 – 10,000+ per tenant               |
| Database                      | Local SQLite + per-tenant DEK         | External Postgres 14+                        | Managed Postgres (RDS / Cloud SQL)   |
| LLM connectivity              | Local Ollama or BYOK (OpenAI/Claude)  | Local Ollama, BYOK, or air-gapped            | Anthropic Claude (BYOK supported)    |
| Air-gappable                  | Yes (Ollama)                          | Yes (Ollama, mirrored container registry)    | No                                   |
| Updates                       | Auto-updater (Squirrel/Sparkle)       | Helm chart bump + rolling restart            | Continuous, managed                  |
| SSO / SCIM                    | Yes                                   | Yes                                          | Yes                                  |
| Backups                       | User-driven export                    | Postgres + storage volume + admin rotates    | Hourly snapshots, 30-day retention   |
| Suitable for                  | Solo founders, small teams, demos     | Regulated industries, on-prem mandates       | Most customers                       |
| Effort to install             | Minutes                               | A day for an experienced operator            | Sign-up form                         |

## Hardware sizing

These numbers are for the **self-hosted** shape. The Desktop build runs on
any laptop that can host Ollama. SaaS sizing is automatic.

| Users      | Backend pods | Backend CPU/RAM/pod | Postgres CPU/RAM | Disk (storage volume) | Redis | Ollama (if used) |
| ---------- | ------------ | ------------------- | ---------------- | --------------------- | ----- | ---------------- |
| 10         | 2            | 0.5 vCPU / 1 GiB    | 2 vCPU / 4 GiB   | 20 GiB                | none  | 4 vCPU / 16 GiB  |
| 100        | 2            | 1 vCPU / 2 GiB      | 4 vCPU / 8 GiB   | 100 GiB               | 1 GiB | 8 vCPU / 32 GiB  |
| 1,000      | 4            | 2 vCPU / 4 GiB      | 8 vCPU / 16 GiB  | 500 GiB               | 4 GiB | 16 vCPU / 64 GiB |
| 10,000     | 12           | 4 vCPU / 8 GiB      | 16 vCPU / 64 GiB | 2 TiB + tiered S3     | 16 GiB| dedicated GPU(s) |

Notes:
- The backend is stateless — scale horizontally.
- Postgres benefits more from RAM than CPU once tables are warmed.
- Redis is optional below 100 users. It accelerates the event bus and
  rate limiter; without it the backend uses in-process fallbacks.
- Ollama only matters if the customer chose local LLMs. BYOK or SaaS LLMs
  reduce the LLM line item to network egress.

## Required services

| Service     | Required | Versions tested | Notes                                                       |
| ----------- | -------- | --------------- | ----------------------------------------------------------- |
| Postgres    | Yes      | 14, 15, 16      | SQLite supported for Desktop only; not for multi-pod K8s.   |
| Redis       | Optional | 6, 7            | Required for cross-process event bus + distributed locks.   |
| Ollama      | Optional | 0.1.x           | Air-gap mode. Otherwise BYOK to OpenAI / Anthropic / Azure. |
| S3 / minio  | Optional | n/a             | Required for >100 GiB uploads or tiered audit log storage.  |
| SMTP relay  | Optional | n/a             | Required for invites, magic-link auth, billing notices.     |
| OIDC / SAML | Optional | n/a             | Required when SSO is enabled.                               |

## Network requirements

| Direction | Port | Destination                       | Required?                            |
| --------- | ---- | --------------------------------- | ------------------------------------ |
| Out       | 443  | `*.openai.com`, `*.anthropic.com` | Only when BYOK to those vendors      |
| Out       | 443  | `licensing.enterprisecore.com`    | Only when using remote license keys  |
| Out       | 443  | SMTP / SendGrid / SES             | If outbound email is enabled         |
| Out       | 443  | Stripe API                        | Only when Stripe billing is enabled  |
| Out       | 443  | Customer's webhook receivers      | When the customer creates webhooks   |
| In        | 443  | App's public hostname             | Required                             |
| In        | 443  | `/scim/v2/*`                      | Required when SSO/SCIM is enabled    |
| In        | 443  | `/widget.js`, `/site/*`           | Public — embeddable widget + sites   |
| In        | 9090 | `/metrics`                        | Internal Prometheus scrape only      |

For fully air-gapped deployments, set `OLLAMA_BASE_URL` to a local Ollama
node, leave `LICENSE_KEY` blank (uses on-prem licensing file), and
explicitly drop the Stripe, OpenAI, and SendGrid env vars. No outbound
internet is required.

## High-availability topology

```
                      ┌─────────────────────────┐
                      │   Public load balancer  │  TLS 1.3, HSTS, OCSP
                      └────────────┬────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
        ┌───────▼──────┐  ┌────────▼──────┐  ┌────────▼──────┐
        │  backend-1   │  │  backend-2    │  │  backend-N    │
        │  (FastAPI)   │  │  (FastAPI)    │  │  (FastAPI)    │
        └───────┬──────┘  └────────┬──────┘  └────────┬──────┘
                │                  │                  │
                └──────────────────┼──────────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  │                │                │
          ┌───────▼──────┐ ┌───────▼──────┐ ┌──────▼──────┐
          │  Postgres    │ │  Redis       │ │  S3 bucket  │
          │  primary +   │ │  Sentinel    │ │  (uploads)  │
          │  read replica│ │  (3 nodes)   │ │             │
          └──────────────┘ └──────────────┘ └─────────────┘
```

- Backend pods are stateless. Run an active-active set behind a TCP/HTTPS
  load balancer (HAProxy, AWS ALB, GCP HTTPS LB). Sticky sessions are
  **not** required.
- Postgres runs as a single primary plus one or more streaming
  replicas. Reads issued by the search-index rebuild + the analytics
  endpoints can be routed to the replica via a separate connection
  string (`READ_DATABASE_URL`).
- Redis is run as Sentinel (3 nodes for quorum) when used; if it is
  unreachable the backend falls back to in-process state.
- The uploads volume is S3-backed in production. The local-disk path is
  only used by the Desktop build.

## Disaster recovery preview

The full DR runbook lives in [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).
Headline numbers for the self-hosted shape:

- **RPO**: 5 minutes (continuous Postgres WAL archiving + 5-minute S3 sync).
- **RTO**: 30 minutes (restore Postgres from latest snapshot + replay WAL
  + redeploy Helm chart + cut DNS).
- Backups are tested monthly via the `scripts/dr_drill.sh` script.

## Step-by-step: docker-compose on a single VM

This is the right shape for ≤100 users on a single tenant or a customer
piloting the suite on one box.

1. Provision a Linux VM (Ubuntu 22.04 LTS recommended) with 4 vCPU, 8 GiB
   RAM, 100 GiB disk. Open port 443.
2. Install Docker Engine + Compose v2 from the official Docker repo.
3. Clone the repository and copy the example override file:
   ```bash
   git clone https://github.com/your-org/enterprisecore.git
   cd enterprisecore
   cp docker-compose.override.yml.example docker-compose.override.yml
   ```
4. Edit `docker-compose.override.yml` to set:
   - `SECRET_KEY` (rotate from the placeholder; 64+ random chars)
   - `DATABASE_URL` (Postgres DSN — local container OK for pilots)
   - `APP_PUBLIC_URL` (HTTPS public hostname)
   - `STRIPE_*` / `OPENAI_API_KEY` / `LICENSE_KEY` if you have them
5. Bring it up:
   ```bash
   docker compose up -d
   docker compose exec backend alembic upgrade head
   docker compose exec backend python -m app.scripts.bootstrap_admin \
       --email admin@your-org.com
   ```
6. Put TLS in front. Caddy with auto-HTTPS works in 5 lines; nginx with
   certbot is the alternative.
7. Visit `https://<host>/`, sign in with the bootstrap admin email
   (magic link sent to console if SMTP isn't configured), and run through
   the post-install checklist below.

## Step-by-step: Helm install on Kubernetes

This is the right shape for ≥100 users, multiple tenants, or any
production deployment that needs HA.

1. Provision the cluster (EKS / GKE / AKS / k3s). Three worker nodes
   minimum.
2. Provision Postgres (RDS / Cloud SQL / on-cluster operator). Capture
   the connection string.
3. Optionally provision Redis (ElastiCache / Memorystore / on-cluster
   operator).
4. Add the Helm repo and install:
   ```bash
   helm repo add enterprisecore https://charts.enterprisecore.com
   helm repo update
   kubectl create namespace enterprisecore
   kubectl -n enterprisecore create secret generic ec-secrets \
       --from-literal=SECRET_KEY=$(openssl rand -hex 32) \
       --from-literal=DATABASE_URL=postgresql://... \
       --from-literal=LICENSE_KEY=... \
       --from-literal=STRIPE_API_KEY=...
   helm install enterprisecore enterprisecore/enterprisecore \
       --namespace enterprisecore \
       --values values.production.yaml
   ```
5. Apply the database migration job (the chart ships one):
   ```bash
   kubectl -n enterprisecore wait --for=condition=complete \
       job/enterprisecore-migrate --timeout=10m
   ```
6. Confirm the rollout:
   ```bash
   kubectl -n enterprisecore get pods
   kubectl -n enterprisecore logs deploy/enterprisecore-backend --tail=50
   curl -fsSL https://<host>/api/health
   ```
7. Configure ingress + TLS — the chart works with cert-manager out of the
   box. Set `ingress.tls=true` and point `ingress.host` at your DNS.
8. Run the post-install checklist below.

## Post-install checklist

Do these immediately after the first boot — every one is a hard
production requirement.

- [ ] **Change the bootstrap admin password** (or remove the bootstrap
      admin entirely once your SSO is wired up).
- [ ] **Rotate `SECRET_KEY`** if you copied the example value. The value
      signs every JWT — leaking it is total compromise. Use 64+ random
      chars from `openssl rand -hex 32` or equivalent.
- [ ] **Install the license key** under Settings → Billing. The suite
      runs in evaluation mode without one.
- [ ] **Configure SSO** under Settings → Security → SSO. OIDC and SAML
      are both supported; SCIM auto-provisions users from the IdP.
- [ ] **Set the tenant IP allowlist** under Settings → Security if your
      org has fixed network egress.
- [ ] **Enable the audit-log stream** under Settings → Compliance. The
      backend can forward audit events to Splunk HEC, Datadog Logs, or
      any HTTPS endpoint.
- [ ] **Verify backups.** Run `scripts/dr_drill.sh --dry-run` (Helm
      install) or `docker compose exec backend python -m app.scripts.dr_drill`
      (docker-compose).
- [ ] **Configure SMTP.** Magic-link login, invites, and billing
      notifications all need a working outbound mail relay.

## Production readiness checklist

Done at go-live and re-audited quarterly.

- [ ] TLS 1.3 only; weak ciphers disabled at the LB.
- [ ] HSTS turned on with `max-age=63072000; includeSubDomains; preload`.
- [ ] Off-site backups verified by an actual restore inside the last 90
      days.
- [ ] Monitoring scrape on `/metrics` configured (Prometheus +
      Grafana / Datadog).
- [ ] Alerting on the 10 dashboards in `docs/dashboards/`.
- [ ] On-call rota + runbook reviewed (see [ON_CALL.md](ON_CALL.md)).
- [ ] SSO enforced; password login disabled for admin accounts.
- [ ] MFA required for every privileged role.
- [ ] Audit stream destination tested (a synthetic event hits the SIEM).
- [ ] SECRET_KEY rotation policy in place (every 90 days minimum).
- [ ] Webhook secrets rotated at least once since first boot.
- [ ] License auto-renewal verified, expiry alert tested.
- [ ] DR drill executed in the last 90 days.
