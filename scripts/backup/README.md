# Backup scripts

Production-tested backup scripts for EnterpriseCore.

All scripts are POSIX bash, designed for Linux. They are parameterised via environment variables — no positional arguments — so they're equally happy under cron, systemd timers, and Kubernetes CronJobs.

Windows / PowerShell ports (`.ps1`) can be added in the future for self-hosted on-prem deployments; the equivalents would be straightforward wrappers around `pg_dump.exe` + the AWS Tools for PowerShell.

---

## Scripts

| Script | What it does |
|---|---|
| `pg_backup.sh` | pg_dump (parallel, directory-format), tar, optional GPG encryption, upload to S3 with optional Object Lock. |
| `pg_backup_verify.sh` | Pulls the latest backup, restores into a temp database, runs sanity queries. Run monthly. |
| `tenant_export.sh` | Uses the GDPR export endpoint to bundle a single tenant's data; optional GPG + S3 upload. |
| `storage_backup.sh` | rsync the local file-upload directory to S3 with versioning. |

---

## Quick start

1. Source your env file:

   ```bash
   set -a
   . /etc/ec/backup.env
   set +a
   ```

   Sample `backup.env`:

   ```bash
   PGHOST=db.internal
   PGPORT=5432
   PGUSER=ec_backup
   PGPASSWORD='<from secrets manager>'
   PGDATABASE=enterprisecore
   BACKUP_S3_BUCKET=ec-backups
   BACKUP_S3_PREFIX=prod
   BACKUP_GPG_RECIPIENT=backup-key@example.com
   BACKUP_USE_OBJECT_LOCK=1
   OBJECT_LOCK_DAYS=30
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
   ```

2. Run the backup:

   ```bash
   sudo -u postgres /opt/ec/scripts/backup/pg_backup.sh
   ```

3. Verify weekly:

   ```bash
   sudo -u postgres /opt/ec/scripts/backup/pg_backup_verify.sh
   ```

---

## Schedule via cron

```cron
# /etc/cron.d/ec-backup
# m h dom mon dow user command
15 3 * * * postgres /opt/ec/scripts/backup/pg_backup.sh >> /var/log/ec-backup/$(date +\%Y-\%m-\%d).log 2>&1
20 5 * * 0 postgres /opt/ec/scripts/backup/pg_backup_verify.sh >> /var/log/ec-backup/verify-$(date +\%Y-\%m-\%d).log 2>&1
30 4 * * * root      /opt/ec/scripts/backup/storage_backup.sh >> /var/log/ec-backup/storage-$(date +\%Y-\%m-\%d).log 2>&1
```

Cron's environment is impoverished; load env vars at the top of each script's wrapper or include `BASH_ENV=/etc/ec/backup.env` in the crontab.

---

## Schedule via systemd timer

```ini
# /etc/systemd/system/ec-backup.service
[Unit]
Description=EnterpriseCore Postgres backup
After=network-online.target

[Service]
Type=oneshot
User=postgres
EnvironmentFile=/etc/ec/backup.env
ExecStart=/opt/ec/scripts/backup/pg_backup.sh
StandardOutput=append:/var/log/ec-backup/backup.log
StandardError=append:/var/log/ec-backup/backup.log
```

```ini
# /etc/systemd/system/ec-backup.timer
[Unit]
Description=Daily EnterpriseCore Postgres backup

[Timer]
OnCalendar=*-*-* 03:15:00 UTC
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ec-backup.timer
```

---

## Schedule via Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: ec-pg-backup
  namespace: ec-prod
spec:
  schedule: "15 3 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          serviceAccountName: ec-backup
          containers:
          - name: backup
            image: ghcr.io/enterprisecore/backup:pg16
            envFrom:
            - secretRef: { name: ec-backup-env }
            command: ["/opt/ec/scripts/backup/pg_backup.sh"]
            resources:
              requests: { cpu: "500m", memory: "512Mi" }
              limits:   { cpu: "2",    memory: "4Gi"   }
```

The image `ghcr.io/enterprisecore/backup:pg16` should be pinned to the same Postgres major version as the server to avoid `pg_dump` version skew.

---

## Encryption

Two options:

- **Server-side encryption (SSE-S3 / SSE-KMS)** — set `BACKUP_USE_SSE=1` (default). S3 encrypts at rest with its own key.
- **Client-side encryption (GPG)** — set `BACKUP_GPG_RECIPIENT=<keyid>`. The dump is encrypted before upload, so the cloud provider never sees the plaintext.

For Tier 1 deployments, do BOTH: client-side GPG + SSE-KMS.

---

## Retention and immutability

- **Local retention** (on the host running the script) — set `BACKUP_RETENTION_DAYS`. Default 7.
- **S3 lifecycle** — configure on the bucket itself, not in this script. Typical lifecycle:
  - Tier 1: 7 days STANDARD → 30 days STANDARD_IA → 90 days GLACIER → 1 year DEEP_ARCHIVE → expire.
  - Tier 2: 30 days STANDARD_IA → 90 days GLACIER → expire.
  - Tier 3: 7 days STANDARD → expire.
- **Object Lock** — set `BACKUP_USE_OBJECT_LOCK=1`. Backups become immutable (Compliance mode) for `OBJECT_LOCK_DAYS`. Defends against ransomware that gains write access to S3.

---

## Failure modes and alerting

Every script exits non-zero on failure and (if `SLACK_WEBHOOK_URL` is set) posts to Slack. For cron / systemd, run a watchdog that alerts if the script hasn't run successfully in the expected window.

Example Prometheus blackbox / textfile alerting:

```bash
# at the bottom of pg_backup.sh after success
echo "ec_backup_last_success_timestamp $(date +%s)" \
  > /var/lib/node_exporter/textfile_collector/ec_backup.prom
```

Then alert:

```yaml
- alert: BackupStale
  expr: time() - ec_backup_last_success_timestamp > 90000   # ~25 hours
  for: 5m
  labels: { severity: page }
  annotations:
    summary: "EnterpriseCore backup is stale ({{ $value }} seconds since last success)"
```

---

## See also

- `docs/DISASTER_RECOVERY.md` — RTO/RPO targets and DR scenarios.
- `docs/runbooks/database-backup-failed.md` — on-call response when this script fails.
- `docs/runbooks/database-restore.md` — restoring from a backup.
- `scripts/restore/` — restore counterparts to these scripts.
