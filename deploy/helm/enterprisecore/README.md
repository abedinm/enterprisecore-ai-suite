# EnterpriseCore AI Suite — Helm chart

Deploys the FastAPI backend, React SPA, optional Postgres, optional Ollama, with HPA, PDB, optional ServiceMonitor, and ingress with TLS.

## Quickstart

```bash
helm install ec deploy/helm/enterprisecore \
  --namespace enterprisecore --create-namespace \
  --set ingress.host=enterprisecore.example.com \
  --set secrets.anthropicApiKey="$ANTHROPIC_API_KEY"
```

## Values

See `values.yaml` for the full schema (heavily commented). The fields you almost always override:

| Path                          | What                                                  |
|-------------------------------|--------------------------------------------------------|
| `image.backend.tag`           | Container tag pinned to the release you want         |
| `image.frontend.tag`          | Same                                                  |
| `ingress.host`                | Public DNS name                                       |
| `ingress.tls.secretName`      | cert-manager-managed TLS secret                       |
| `secrets.secretKey`           | 64+ random bytes (auto-generated if blank)            |
| `secrets.encryptionKey`       | column-level encryption key (auto-generated if blank) |
| `secrets.anthropicApiKey`     | Claude API key                                        |
| `secrets.openaiApiKey`        | OpenAI API key                                        |
| `postgres.enabled`            | `false` to use external Postgres                      |
| `externalDatabase.dsn`        | When `postgres.enabled=false`                         |
| `autoscaling.maxReplicas`     | Cap on backend pods                                   |
| `prometheus.enabled`          | `true` if kube-prometheus-stack is installed          |

## External Postgres

```yaml
postgres:
  enabled: false
externalDatabase:
  dsn: "postgresql+psycopg2://user:pass@my-rds.aws.com:5432/enterprisecore"
  # Or point at a pre-existing Secret:
  # existingSecret: my-rds-creds
  # existingSecretKey: dsn
```

## TLS via cert-manager

The default annotations on the Ingress request a Let's Encrypt certificate via the `letsencrypt-prod` ClusterIssuer. Make sure cert-manager is installed and that ClusterIssuer exists, or override `ingress.annotations` with your own.

## ServiceMonitor (Prometheus)

```yaml
prometheus:
  enabled: true
  serviceMonitor:
    labels:
      release: kube-prometheus-stack  # required label for kps to pick it up
```

## Upgrades

```bash
helm upgrade ec deploy/helm/enterprisecore -n enterprisecore \
  --set image.backend.tag=0.7.0 --set image.frontend.tag=0.7.0
```

Rolling update strategy is `maxSurge: 1, maxUnavailable: 0` so there's always a running pod during the swap.

## Uninstall

```bash
helm uninstall ec -n enterprisecore
# Persistent volumes are kept by default (helm.sh/resource-policy: keep).
# Remove them manually if you want a clean slate.
```

## Helm test

```bash
helm test ec -n enterprisecore
```

Runs a transient `curl` Pod that hits `/api/health` and `/healthz`.
