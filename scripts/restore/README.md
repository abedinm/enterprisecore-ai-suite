# Restore scripts

Counterparts to `scripts/backup/`. Bring data back from backups, single-tenant exports, or provider-managed PITR.

All scripts are POSIX bash for Linux.

---

## Scripts

| Script | What it does |
|---|---|
| `pg_restore.sh` | Full-database restore from an S3 backup. Takes a pre-snapshot, drops the target DB, restores, re-grants, optionally runs migrations, ANALYZE. |
| `grants.sql` | Application-tier role grants applied after `pg_restore`. Edit role names to match your environment. |
| `tenant_import.sh` | Restore a single tenant from a `tenant_export.sh` bundle via the admin API. |
| `point_in_time_recovery.sh` | Wraps the cloud provider's PITR command (AWS RDS / Cloud SQL / Azure Postgres Flexible Server). |

---

## Choosing the right script

| Situation | Use |
|---|---|
| Database is gone / corrupt; have an S3 backup | `pg_restore.sh` |
| Single tenant deleted by mistake; have a recent tenant export | `tenant_import.sh` |
| Need to recover to a specific second; using managed Postgres with WAL archival | `point_in_time_recovery.sh` |
| Single row / table deleted; no full restore needed | manual `INSERT` from audit log, see `docs/runbooks/database-restore.md` |

---

## Pre-flight for any restore

1. **Stop the application** writes (`kubectl scale deploy/ec-backend --replicas=0`). Do not skip — concurrent writes during restore produce silent data divergence.
2. **Take a pre-restore snapshot** — `pg_restore.sh` does this automatically; if you're using PITR you should snapshot the existing instance first.
3. **Confirm the backup you're restoring from**:

   ```bash
   aws s3 ls s3://ec-backups/$ENV/ | tail -10
   ```

4. **Decide RTO** — communicate to the customer.
5. **Have the runbook open** — `docs/runbooks/database-restore.md`.

---

## Example: full-database restore

```bash
set -a
. /etc/ec/restore.env
set +a

export BACKUP_KEY=s3://ec-backups/prod/ec-enterprisecore-2026-05-22T03-15Z.pgc.gpg
export PGDATABASE=enterprisecore
export ALEMBIC_DIR=/opt/ec/backend

/opt/ec/scripts/restore/pg_restore.sh
```

The script:
1. Snapshots the current DB to `BACKUP_TMP_DIR`.
2. Downloads the requested backup.
3. Decrypts (if `.gpg`).
4. Drops and recreates the target database.
5. Restores with 4 parallel jobs.
6. Applies `grants.sql`.
7. Optionally runs `alembic upgrade head`.
8. Runs `ANALYZE` to refresh planner statistics.
9. Prints user / tenant counts as a sanity check.

---

## Example: PITR with AWS RDS

```bash
PROVIDER=aws \
AWS_REGION=us-east-1 \
SOURCE_INSTANCE=ec-prod \
TARGET_INSTANCE=ec-prod-restored-20260522 \
TARGET_TIMESTAMP=2026-05-22T10:34:00Z \
  /opt/ec/scripts/restore/point_in_time_recovery.sh
```

The script does NOT cut DNS for you. After the new instance is `available`:

1. Run smoke tests against the new endpoint.
2. Update the Secrets Manager entry / Kubernetes secret with the new connection string.
3. Restart the backend pods.
4. Decommission the old instance after a clean window.

---

## Example: single-tenant restore

```bash
EC_API_BASE=https://app.example.com \
EC_ADMIN_TOKEN=$ADMIN_TOKEN \
BUNDLE_PATH=s3://ec-backups/prod/tenant-c0a1b2-2026-05-21T03-00Z.json.zip.gpg \
GPG_DECRYPT=1 \
TARGET_TENANT_ID=c0a1b2-... \
  /opt/ec/scripts/restore/tenant_import.sh
```

The bundle is idempotent (matched by `export_bundle_id`). Re-running is safe.

---

## Post-restore validation

```bash
# Schema head matches code
alembic current

# Row counts vs. expected (compare with monitoring dashboard)
psql -c "SELECT 'users' AS t, count(*) FROM users
         UNION ALL SELECT 'tenants', count(*) FROM tenants
         UNION ALL SELECT 'invoices', count(*) FROM invoices;"

# Application reachable
curl -fsS https://app.example.com/api/v1/healthz
curl -fsS https://app.example.com/api/v1/readyz

# Audit a sample tenant can log in
curl -fsS -X POST https://app.example.com/api/v1/auth/login \
  -d '{"email":"qa@example.com","password":"..."}'
```

If anything looks off, you have the pre-restore snapshot path (printed by `pg_restore.sh`) to roll back to.

---

## See also

- `docs/runbooks/database-restore.md` — operator-facing recovery procedure.
- `docs/DISASTER_RECOVERY.md` — overarching DR strategy.
- `scripts/backup/` — backup counterparts.
