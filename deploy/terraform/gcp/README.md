# EnterpriseCore on GCP — Terraform

Cloud Run for compute, Cloud SQL Postgres, Memorystore Redis, GCS uploads, Artifact Registry for images, global HTTPS Load Balancer with Google-managed TLS.

## Prerequisites

- GCP project with billing enabled
- `gcloud` authenticated (`gcloud auth application-default login`)
- Terraform 1.6+
- A domain you control (you'll create an A record pointing at the LB IP)

## Quickstart

```bash
cd deploy/terraform/gcp

cat > terraform.tfvars <<EOF
project_id         = "my-project-1234"
region             = "us-central1"
domain_name        = "enterprisecore.example.com"
db_password        = "REPLACE_WITH_RANDOM"
app_secret_key     = "REPLACE_WITH_64_BYTES_OF_RANDOM"
app_encryption_key = "REPLACE_WITH_32_BYTES_OF_RANDOM"
anthropic_api_key  = "sk-ant-..."
EOF

terraform init
terraform apply
```

Apply will take 10–20 minutes (Cloud SQL is the slow step, Google-managed cert needs DNS validation before it provisions).

After apply: create an A record for your domain pointing at `terraform output lb_ip_address`. The managed cert will validate once DNS resolves.

## Pushing images

```bash
gcloud auth configure-docker $(terraform output -raw artifact_registry_repository | cut -d/ -f1)

docker build -t "$(terraform output -raw artifact_registry_repository)/backend:0.6.0" .
docker push "$(terraform output -raw artifact_registry_repository)/backend:0.6.0"

docker build -f nginx.Dockerfile -t "$(terraform output -raw artifact_registry_repository)/frontend:0.6.0" .
docker push "$(terraform output -raw artifact_registry_repository)/frontend:0.6.0"

terraform apply -var backend_image_tag=0.6.0 -var frontend_image_tag=0.6.0
```

## Cost ballpark (us-central1)

- Cloud Run (2 instances always-on, 1 vCPU / 1 GB): ~$50/mo backend, ~$15/mo frontend
- Cloud SQL `db-custom-2-7680` (2 vCPU / 7.5 GB), 50 GB SSD: ~$110/mo
- Memorystore Redis BASIC 1 GB: ~$35/mo
- GCS + load balancer + egress: ~$20/mo

Total: ~$230/mo. HA Cloud SQL roughly doubles the DB.

## Destroy

```bash
terraform destroy
```

Cloud SQL has `deletion_protection = true` — flip it to `false` in `main.tf` first.
