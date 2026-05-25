# Cloud deployment

Three Terraform modules ship with the repo: `deploy/terraform/aws`, `deploy/terraform/gcp`, `deploy/terraform/azure`. They produce production-shaped deployments — opinionated defaults, sensible costs, and tuneable via variables.

## Side-by-side

| Aspect                  | AWS                         | GCP                       | Azure                          |
|-------------------------|-----------------------------|---------------------------|--------------------------------|
| Compute                 | ECS Fargate                 | Cloud Run                 | Container Apps                 |
| Database                | RDS Postgres                | Cloud SQL Postgres        | PostgreSQL Flexible Server     |
| Cache                   | ElastiCache Redis           | Memorystore Redis         | Azure Cache for Redis          |
| Object storage          | S3 (KMS encrypted)          | GCS (CMEK encrypted)      | Blob Storage (ZRS)             |
| Container registry      | ECR                         | Artifact Registry         | Container Registry             |
| Secrets                 | Secrets Manager             | Secret Manager            | Key Vault                      |
| TLS                     | ACM cert on ALB             | Google-managed cert       | Container Apps managed cert    |
| Load balancer           | ALB                         | Global HTTPS LB           | Container Apps Ingress         |
| Autoscaling             | App Auto Scaling on CPU     | Cloud Run native          | Container Apps HTTP scaler     |
| Cold-start risk         | None (always warm)          | Some (min_instances=2)    | None                           |
| ~Monthly cost (small)   | $220                        | $230                      | $225                           |
| Multi-AZ uplift         | Multi-AZ RDS toggle         | Regional Cloud SQL toggle | ZoneRedundant HA toggle        |
| Best for                | AWS-native shops, biggest knob set | Lowest ops, fast deploy | Microsoft-native shops, hybrid |

All three provision into private subnets/VNets with no public DB or cache; the only public surface is the load balancer.

## Terraform quickstart (per provider)

Each module has its own `README.md` with the variables and apply walkthrough. Common pattern:

```bash
cd deploy/terraform/<provider>
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform plan -out tf.plan
terraform apply tf.plan
```

After apply, each module emits:

- A DNS target (ALB DNS name, GCP LB IP, or Container App FQDN) — create your A/CNAME record
- A container registry URL — push your backend + frontend images
- DB / cache endpoints — for emergency direct access

Re-apply after pushing images to roll out new versions:

```bash
terraform apply -var backend_image_tag=0.7.0 -var frontend_image_tag=0.7.0
```

### Image build + push (works for all three)

```bash
# Build locally
docker build -t enterprisecore-backend:0.7.0 .
docker build -f nginx.Dockerfile -t enterprisecore-frontend:0.7.0 .

# Retag and push — see provider README for the registry-specific login command
docker tag enterprisecore-backend:0.7.0 <registry>/enterprisecore-backend:0.7.0
docker push <registry>/enterprisecore-backend:0.7.0
```

## Domain + DNS

1. Pick a host like `enterprisecore.example.com`.
2. After `terraform apply`, copy the LB target from the Terraform outputs.
3. Create a Route 53 ALIAS (AWS), Cloud DNS A record (GCP), or your provider's equivalent.
4. **Allow time for cert provisioning.** Managed certs (GCP) and Let's Encrypt-via-cert-manager (k8s) need DNS to resolve before they validate — expect 5–30 minutes.

If you're putting Cloudflare or another CDN in front:

- Use Cloudflare's "Full (strict)" mode and let the cloud LB hold its own cert.
- Or use Cloudflare Origin Certificates and skip the cloud-side cert entirely.
- Make sure WebSocket / SSE upgrade headers pass through (`/api/v1/ai/stream` is SSE).

## Email + SMTP

EnterpriseCore sends transactional email (password resets, magic links, invites). Pick one:

| Provider     | Why                                                  |
|--------------|------------------------------------------------------|
| AWS SES      | Cheap, but requires production access approval       |
| SendGrid     | Easy, free tier, decent deliverability               |
| Postmark     | Best deliverability for transactional                |
| Mailgun      | EU residency if needed                               |

Configure via env vars on the backend:

```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.xxxxx
SMTP_FROM=no-reply@enterprisecore.example.com
SMTP_USE_TLS=true
```

Wire these into:

- AWS: add to the Secrets Manager secret + the ECS task definition `secrets` block.
- GCP: add to Secret Manager + the Cloud Run service env.
- Azure: add to Key Vault + reference in the Container App secrets.

## Production security checklist

### Identity & access

- [ ] No long-lived static credentials in CI — use OIDC (AWS IAM Identity Provider, GCP Workload Identity, Azure Federated Credentials).
- [ ] Limit `terraform apply` to a dedicated IAM principal with state-bucket access only.
- [ ] Enable MFA on all human users; require SSO if practical.
- [ ] Rotate the app's `SECRET_KEY` / `ENCRYPTION_KEY` if any operator with access leaves.

### Network

- [ ] DB and cache stay in private subnets; the only public surface is the LB.
- [ ] Security groups / firewall rules narrow ingress to 443 only (HTTP redirects to HTTPS at the LB).
- [ ] WAF on the LB if the app is exposed to the open internet (AWS WAF, Cloud Armor, Azure Front Door).
- [ ] Restrict egress on the backend to the AI provider domains you actually use.

### Data at rest

- [ ] KMS / CMEK encryption on object storage, DB, snapshots.
- [ ] Key rotation enabled (90d default in all three modules).
- [ ] Backup encryption verified — restore-test once a quarter.
- [ ] Bucket versioning + lifecycle rules so deletes are recoverable.

### Data in flight

- [ ] TLS 1.2+ only on the LB (1.3 preferred — TF modules set `TLS13-1-2-2021-06` on AWS).
- [ ] DB connections forced to SSL (`?sslmode=require` in the DSN).
- [ ] Internal pod-to-pod traffic uses cluster CA if the cluster supports mTLS (mesh territory; opt-in).

### Application

- [ ] Sentry DSN wired; alerts hooked to a channel you actually read.
- [ ] Rate limiting active (SlowAPI in the app + LB-level rate limits).
- [ ] OWASP audit on the cookie + auth flow (already covered by the security middleware tests).
- [ ] CSP header tuned for your domain (see `SecurityHeadersMiddleware`).

### Operational

- [ ] Logs shipped off-host (CloudWatch / Cloud Logging / Log Analytics — wired in all three modules).
- [ ] Metrics scraped (Prometheus on k8s; CloudWatch metrics on ECS; Cloud Monitoring on Cloud Run; Azure Monitor).
- [ ] Disaster recovery runbook tested annually.
- [ ] Patch the base images monthly; pin tags to immutable shas in production.

### Compliance

- [ ] Audit logging enabled on the database (pgAudit on managed Postgres).
- [ ] Data residency: pick the region that satisfies your customer contracts.
- [ ] DPA + sub-processor list updated when you add a new cloud provider or AI vendor.
- [ ] Retention policies defined for logs and backups (GDPR, HIPAA, SOC 2, whichever applies).

## What requires manual setup

- DNS record creation (none of the modules manage your DNS zone — they emit the target only)
- TLS cert (managed certs on GCP / Azure are automatic; AWS needs an ACM cert ARN as input)
- AI provider keys (Anthropic, OpenAI — supply as Terraform inputs)
- Email/SMTP credentials (see above)
- Initial bootstrap admin user — first login flow creates the org admin
- License key (paid SKUs) — set `LICENSE_KEY` in the same way as other secrets
