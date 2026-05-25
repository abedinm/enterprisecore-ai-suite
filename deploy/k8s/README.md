# Raw Kubernetes manifests (Kustomize)

Helm-free alternative. Same shape as the Helm chart but as plain YAML wired together with Kustomize.

## Quickstart

```bash
# 1. Create the secret out-of-band:
kubectl create namespace enterprisecore
kubectl create secret generic enterprisecore-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -base64 64 | tr -d '\n')" \
  --from-literal=ENCRYPTION_KEY="$(openssl rand -base64 48 | tr -d '\n')" \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')" \
  --from-literal=POSTGRES_DSN="postgresql+psycopg2://ec:CHANGEME@enterprisecore-postgres:5432/enterprisecore" \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-..." \
  -n enterprisecore

# 2. Apply
kubectl apply -k deploy/k8s/

# 3. Watch
kubectl -n enterprisecore get pods -w
```

## Customization

Create your own kustomization that layers on top:

```yaml
# my-cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
  - ../../deploy/k8s
namespace: ec-prod
images:
  - name: ghcr.io/enterprisecore/enterprisecore-backend
    newTag: 0.7.0
patches:
  - path: ingress-prod.yaml
    target:
      kind: Ingress
      name: enterprisecore
```

```bash
kubectl apply -k my-cluster/
```

## What's not included

- Network policies (see Helm chart for an example)
- ServiceMonitor for Prometheus (see Helm chart)
- Ollama (rarely deployed via raw manifests; use Helm or a dedicated GPU stack)
- External secret management (use sealed-secrets / external-secrets / SOPS)
