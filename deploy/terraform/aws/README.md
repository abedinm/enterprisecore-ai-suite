# EnterpriseCore on AWS — Terraform

Spins up a production-shaped deployment: VPC, ECS Fargate, RDS Postgres, ElastiCache Redis, ALB with ACM TLS, S3 uploads bucket, ECR repos, CloudWatch logs + alarms.

## Prerequisites

- AWS account + admin-equivalent credentials in `~/.aws/credentials` or env vars
- Terraform 1.6+
- A domain you control + an ACM certificate **in the same region** covering it
- The backend and frontend container images pushed to the ECR repos this module creates (apply once, push, then update `*_image_tag` and re-apply)

## Quickstart

```bash
cd deploy/terraform/aws

cat > terraform.tfvars <<EOF
region              = "us-east-1"
domain_name         = "enterprisecore.example.com"
acm_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/abc-..."
db_password         = "REPLACE_WITH_LONG_RANDOM_STRING"
app_secret_key      = "REPLACE_WITH_64_BYTES_OF_RANDOM"
app_encryption_key  = "REPLACE_WITH_32_BYTES_OF_RANDOM"
anthropic_api_key   = "sk-ant-..."
openai_api_key      = "sk-..."
EOF

terraform init
terraform plan -out tf.plan
terraform apply tf.plan
```

Outputs include the ALB DNS name; create a Route 53 ALIAS (or your DNS provider's equivalent) from `domain_name` -> `alb_dns_name`.

## Pushing images

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    "$(terraform output -raw ecr_backend_url | cut -d/ -f1)"

docker build -t "$(terraform output -raw ecr_backend_url):0.6.0" .
docker push "$(terraform output -raw ecr_backend_url):0.6.0"

docker build -f nginx.Dockerfile -t "$(terraform output -raw ecr_frontend_url):0.6.0" .
docker push "$(terraform output -raw ecr_frontend_url):0.6.0"

terraform apply -var backend_image_tag=0.6.0 -var frontend_image_tag=0.6.0
```

ECR is set to `IMMUTABLE` tags — bump the tag for every release.

## Cost ballpark (us-east-1, May 2026)

- ALB: ~$20/mo
- 2x Fargate backend (0.5 vCPU / 1 GB) + 2x frontend (0.25 / 0.5): ~$60/mo
- RDS `db.t4g.medium` single-AZ, 50 GB gp3: ~$60/mo
- ElastiCache `cache.t4g.micro`: ~$13/mo
- NAT Gateway x2: ~$70/mo (the largest single line item — consider a single NAT in dev)
- S3 + CloudWatch + KMS: a few dollars

Total: ~$220/mo for a 2-AZ baseline. Multi-AZ RDS roughly doubles the DB line.

## Destroy

```bash
terraform destroy
```

Note: RDS has `deletion_protection = true`. Flip it off in the resource (or via the console) before destroying, and expect a final snapshot to be created.
