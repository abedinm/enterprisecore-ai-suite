# EnterpriseCore on Azure — Terraform

Azure Container Apps for compute, PostgreSQL Flexible Server, Azure Cache for Redis, Blob Storage uploads, Container Registry, Key Vault for secrets.

## Prerequisites

- Azure subscription
- `az login` completed
- Terraform 1.6+
- A domain you control (point a CNAME at the backend Container App FQDN, or front it with Azure Front Door)

## Quickstart

```bash
cd deploy/terraform/azure

cat > terraform.tfvars <<EOF
location           = "eastus"
domain_name        = "enterprisecore.example.com"
db_password        = "REPLACE_WITH_RANDOM"
app_secret_key     = "REPLACE_WITH_64_BYTES_OF_RANDOM"
app_encryption_key = "REPLACE_WITH_32_BYTES_OF_RANDOM"
anthropic_api_key  = "sk-ant-..."
EOF

terraform init
terraform apply
```

Apply takes ~15–25 minutes.

## Pushing images

```bash
az acr login --name $(terraform output -raw container_registry_url | cut -d. -f1)

docker build -t "$(terraform output -raw container_registry_url)/enterprisecore-backend:0.6.0" .
docker push "$(terraform output -raw container_registry_url)/enterprisecore-backend:0.6.0"

docker build -f nginx.Dockerfile -t "$(terraform output -raw container_registry_url)/enterprisecore-frontend:0.6.0" .
docker push "$(terraform output -raw container_registry_url)/enterprisecore-frontend:0.6.0"

terraform apply -var backend_image_tag=0.6.0 -var frontend_image_tag=0.6.0
```

## Custom domain + TLS

Container Apps issues a free managed certificate when you bind a custom domain. After apply:

```bash
az containerapp hostname add \
  --resource-group enterprisecore-rg \
  --name enterprisecore-frontend \
  --hostname enterprisecore.example.com

az containerapp hostname bind \
  --resource-group enterprisecore-rg \
  --name enterprisecore-frontend \
  --hostname enterprisecore.example.com \
  --environment enterprisecore-cae \
  --validation-method CNAME
```

You'll be prompted to add an `asuid.` TXT record + a CNAME to the frontend FQDN.

For routing `/api`, `/site`, `/widget.js`, `/metrics` to the backend Container App, front the apps with Azure Front Door or Application Gateway — Container Apps Ingress doesn't do path-based routing across apps.

## Cost ballpark (East US)

- Container Apps (2 backend replicas, 0.5 vCPU / 1 GB; 1 frontend, 0.25 / 0.5): ~$55/mo
- PostgreSQL Flexible Server `GP_Standard_D2s_v3` 64 GB: ~$130/mo
- Redis Basic C1: ~$15/mo
- ZRS storage account + Container Registry + KV + Log Analytics: ~$25/mo

Total: ~$225/mo. Zone-redundant Postgres bumps the DB line by ~70%.

## Destroy

```bash
terraform destroy
```

Key Vault has purge protection; the resource group destroy will soft-delete it for 30 days.
