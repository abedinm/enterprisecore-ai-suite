# Self-hosting EnterpriseCore AI Suite

EnterpriseCore is offline-first by design — your data stays on hardware you control. This doc covers three deployment paths, hardware sizing, backups, TLS, upgrades, monitoring, and troubleshooting.

## Choosing a path

| Path                | Best for                                          | Complexity |
|---------------------|---------------------------------------------------|------------|
| Docker Compose      | Single VM, 1–50 users, fastest setup              | Low        |
| Helm on Kubernetes  | 50–5000 users, HA, rolling upgrades, autoscaling  | Medium     |
| Manual install      | Air-gapped environments without container runtime | High       |

## Hardware sizing

| Concurrent users | CPU      | RAM   | Disk   | Notes                                |
|------------------|----------|-------|--------|--------------------------------------|
| 1–10             | 2 vCPU   | 4 GB  | 50 GB  | Docker Compose on a $20/mo VPS works |
| 10–50            | 4 vCPU   | 8 GB  | 100 GB | Postgres on the same host is fine    |
| 50–250           | 8 vCPU   | 16 GB | 250 GB | Split Postgres to a managed service  |
| 250–1000         | 16 vCPU  | 32 GB | 500 GB | Kubernetes + managed Postgres + Redis|
| 1000+            | k8s + HPA, sharded as needed                                              |

Add ~8 GB of RAM and ~30 GB of disk per Ollama model you intend to host locally.

## Database choice

- **SQLite (default)** — single-user demo only. Not safe for production multi-user workloads; locks degrade under concurrency.
- **Postgres 14+** — required for anything beyond demo use. Bundled in `docker-compose.yml` and the Helm chart, but you should use a managed Postgres (RDS / Cloud SQL / Azure DB / Crunchy) in production for backups + PITR.

Set `DB_BACKEND=postgres` and `POSTGRES_DSN=postgresql+psycopg2://user:pass@host:5432/db`.

## Path 1: Docker Compose on a single VM

### Prerequisites

- Linux VM (Ubuntu 22.04 LTS or later recommended)
- Docker Engine 24+ and the Compose plugin
- 10 GB free disk for images, 50 GB+ for data
- A domain name pointing at the VM's public IP

### Steps

```bash
# Clone the repo (or copy these files via your release process)
git clone https://github.com/enterprisecore/ai-suite.git
cd ai-suite

# Configure secrets
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -base64 24)
SECRET_KEY=$(openssl rand -base64 64 | tr -d '\n')
ENCRYPTION_KEY=$(openssl rand -base64 48 | tr -d '\n')
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
EOF
chmod 600 .env

# Build + boot
docker compose build
docker compose up -d

# Tail logs
docker compose logs -f backend
```

The stack now listens on `:8080` (frontend) and `:8765` (backend). Put a reverse proxy in front for TLS — Caddy is the simplest option:

```caddy
# /etc/caddy/Caddyfile
enterprisecore.example.com {
    reverse_proxy localhost:8080
}
```

Restart Caddy and you've got Let's Encrypt-managed TLS automatically.

To start a local LLM as well:

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull llama3.2
```

## Path 2: Helm on Kubernetes

### Prerequisites

- Kubernetes 1.27+ cluster
- `kubectl` configured for that cluster
- Helm 3.12+
- An ingress controller (ingress-nginx recommended)
- cert-manager + a ClusterIssuer for Let's Encrypt
- A StorageClass that provisions PVCs (most managed clusters provide this)

### Install

```bash
helm install ec deploy/helm/enterprisecore \
  --namespace enterprisecore --create-namespace \
  --set ingress.host=enterprisecore.example.com \
  --set secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set secrets.openaiApiKey="$OPENAI_API_KEY"
```

The chart auto-generates `SECRET_KEY`, `ENCRYPTION_KEY`, and the Postgres password on first install. They're stored in `Secret/<release>-secrets` and preserved across `helm upgrade`.

External Postgres:

```yaml
# values-prod.yaml
postgres:
  enabled: false
externalDatabase:
  existingSecret: rds-creds       # contains key "dsn"
  existingSecretKey: dsn
```

See `deploy/helm/enterprisecore/README.md` for the full values reference.

## Path 3: Manual install (no containers)

For air-gapped environments where Docker isn't allowed. Outline:

1. Provision Postgres 16 separately.
2. Install Python 3.13, Node 20, nginx on the host.
3. `pip install -r backend/requirements.txt` into a venv.
4. Build the frontend: `cd frontend && npm ci && npm run build`.
5. Serve `frontend/dist/` via nginx using `deploy/nginx/nginx.conf` (adjust `proxy_pass` to point at `127.0.0.1:8765`).
6. Run the backend via systemd:

```ini
# /etc/systemd/system/enterprisecore.service
[Unit]
Description=EnterpriseCore AI Suite backend
After=network.target postgresql.service

[Service]
Type=simple
User=enterprisecore
WorkingDirectory=/opt/enterprisecore/backend
EnvironmentFile=/etc/enterprisecore/env
ExecStart=/opt/enterprisecore/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765 --workers 2
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/enterprisecore

[Install]
WantedBy=multi-user.target
```

`EnvironmentFile` should contain `DB_BACKEND`, `POSTGRES_DSN`, `SECRET_KEY`, `ENCRYPTION_KEY`, `ENTERPRISECORE_DATA_DIR=/var/lib/enterprisecore`, and any AI keys.

## Backups

### Postgres

```bash
# Daily logical dump, retained for 30 days
pg_dump -Fc -h db.internal -U ec enterprisecore > /backups/ec-$(date +%F).dump
find /backups -name 'ec-*.dump' -mtime +30 -delete
```

Restore:

```bash
pg_restore -d enterprisecore -h db.internal -U ec --clean --if-exists /backups/ec-2026-05-20.dump
```

For managed Postgres, enable point-in-time recovery and rely on the provider's snapshot/PITR rather than logical dumps.

### Volume snapshots

The `/data` volume holds uploads, the knowledge index, and (if SQLite) the database. Snapshot it on a schedule:

- Docker Compose: `docker run --rm -v ec-data:/data -v /backups:/out alpine tar czf /out/data-$(date +%F).tgz -C / data`
- Kubernetes: use a CSI snapshotter like Velero or a CSI driver with `VolumeSnapshot`.

## TLS with cert-manager + Let's Encrypt

```yaml
# cluster-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f cluster-issuer.yaml
```

The chart's ingress is already annotated for `letsencrypt-prod`; the cert is provisioned automatically once DNS resolves.

## Upgrades

### Helm

```bash
helm upgrade ec deploy/helm/enterprisecore -n enterprisecore \
  --set image.backend.tag=0.7.0 --set image.frontend.tag=0.7.0
```

Rolling-update strategy `maxSurge: 1, maxUnavailable: 0` keeps the app available. Database migrations run automatically on backend startup (Alembic).

### Compose

```bash
git pull
docker compose pull        # if you use a registry
docker compose build       # if you build locally
docker compose up -d
```

### Manual

```bash
systemctl stop enterprisecore
git -C /opt/enterprisecore pull
/opt/enterprisecore/venv/bin/pip install -r /opt/enterprisecore/backend/requirements.txt
systemctl start enterprisecore
```

## Monitoring

The backend exposes Prometheus metrics on `/metrics`. To wire into kube-prometheus-stack:

```yaml
# values-prod.yaml
prometheus:
  enabled: true
  serviceMonitor:
    labels:
      release: kube-prometheus-stack  # matches the kps selector
```

For a standalone Prometheus, add a scrape config:

```yaml
scrape_configs:
  - job_name: enterprisecore-backend
    scrape_interval: 30s
    static_configs:
      - targets: ["enterprisecore.example.com"]
        labels:
          env: prod
    metrics_path: /metrics
    scheme: https
```

A starter Grafana dashboard is shipped in [`docs/monitoring/grafana-dashboard.json`](../deploy/grafana/grafana-dashboard.json) (TODO: import it via `grafana_dashboard ConfigMap` if you use the operator).

Key SLO metrics:

- `http_request_duration_seconds` (latency histogram, per route)
- `http_requests_total{status=~"5.."}` (error rate)
- `ec_db_pool_in_use` (connection pool saturation)
- `ec_ai_provider_request_total{provider, status}` (AI provider success/fail)

## Troubleshooting

| Symptom                                       | Check                                                                            |
|-----------------------------------------------|----------------------------------------------------------------------------------|
| Pod restarts with `OOMKilled`                 | Bump `resources.backend.limits.memory`; large knowledge indexes need more RAM    |
| 502 from ingress                              | Backend healthcheck failing — `kubectl logs <pod>`, check `/api/health` directly |
| `SECRET_KEY` warnings on startup              | Chart-generated keys exist in the cluster but pods can't read the Secret yet     |
| TLS cert pending forever                      | DNS hasn't propagated; cert-manager runs http-01 against the public host         |
| Postgres connection errors after upgrade      | Old Alembic head; check `alembic current` and run `alembic upgrade head` manually|
| SSE streaming (`/api/v1/ai/stream`) drops     | `proxy_buffering off;` must be set on the ingress (default for our nginx)        |
| Slow startup (>2 min)                         | Knowledge index re-loading from disk; tune `KNOWLEDGE_INGEST_POLL_SECONDS`       |
| Disk full on `/data`                          | Run housekeeping; `ENTERPRISECORE_DATA_DIR/storage/` accumulates uploads + logs  |

## Hardening checklist

- [ ] Rotate `SECRET_KEY` and `ENCRYPTION_KEY` at install; never reuse defaults.
- [ ] Restrict network egress (the app should only need 443 outbound + your AI providers).
- [ ] Enable Postgres connection encryption (`?sslmode=require` in the DSN).
- [ ] Set up backups + verify a restore once a quarter.
- [ ] Enable rate limiting on your ingress in addition to the app's `slowapi` limits.
- [ ] Turn on Sentry (`SENTRY_DSN`) and log shipping to a SIEM you actually read.
- [ ] Patch the host OS and `docker compose pull` weekly.
- [ ] Restrict admin access by IP if your reverse proxy supports it.
- [ ] Test the disaster-recovery runbook (delete the pod, watch it recover, restore from backup).

See `SECURITY.md` at the repo root for the responsible-disclosure process and known security posture.
