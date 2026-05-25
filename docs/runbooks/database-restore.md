# Runbook — Database restore

This runbook covers restoring the Postgres database from an off-site backup. It is invoked by `disaster-recovery` scenarios, by data-corruption incidents, and by point-in-time recovery requests from customers.

## Symptoms

- Confirmed data loss / corruption — see `database-connection-pool-exhausted.md` or the relevant runbook to confirm root cause first.
- Customer ticket: "Restore tenant X to time T."
- DR drill: full-region restore exercise in progress.

## Severity

- **Sev 1** if production data is gone or unusable. Restore is the critical path.
- **Sev 2** if this is a partial restore (single tenant) where the rest of production is functioning.
- **Sev 3** if this is a DR drill on a non-production environment.

## Pre-flight

1. Decide the target: **full database** restore (this runbook) or **single tenant** (see `tenant_import.sh`).
2. Identify the backup to restore. List available backups:

   ```bash
   aws s3 ls "s3://ec-backups/$ENV/" --recursive | sort -k1,2
   ```

3. Note the backup filename and the wall-clock target. The script is parameterised by `BACKUP_KEY`.
4. **Stop the application** to prevent dual-writes:

   ```bash
   sudo systemctl stop ec-backend ec-frontend
   ```

5. Snapshot the current database (even if corrupt) so you can roll back the restore if needed:

   ```bash
   sudo -u postgres pg_dump -Fc enterprisecore > /var/lib/postgresql/pre-restore-$(date -u +%Y%m%dT%H%M).pgc
   ```

## Immediate mitigation

Run the restore script:

```bash
sudo -u postgres BACKUP_KEY=s3://ec-backups/prod/2026-05-22T03-15.pgc.gpg \
  /opt/ec/scripts/restore/pg_restore.sh
```

The script:
1. Downloads the backup to `BACKUP_TMP_DIR`.
2. Decrypts (if `BACKUP_GPG_RECIPIENT` is set).
3. Drops the existing `enterprisecore` database (after confirmation).
4. Creates a fresh database with the same owner / collation.
5. Runs `pg_restore` with parallel jobs `${PARALLEL_JOBS:-4}`.
6. Re-applies role grants from `scripts/restore/grants.sql`.
7. Runs `ANALYZE` to refresh planner statistics.
8. Verifies with `SELECT count(*) FROM users; SELECT count(*) FROM invoices;` and exits non-zero if either is zero.

Expected runtime: ~3 minutes per GB of compressed backup on an 8-core host.

## Root cause investigation

If the restore fails:

- `pg_restore: error: could not connect to server` — Postgres is not running. Start it: `sudo systemctl start postgresql`.
- `pg_restore: error: invalid byte sequence` — backup is corrupt or wrong compression. Re-download from S3; verify checksum: `sha256sum ec-backup.pgc`.
- `permission denied for schema` — role grants script failed. Re-run `psql -f scripts/restore/grants.sql`.
- Migration mismatch — backup is from a different Alembic head. Run `alembic upgrade head` after restore.

## Permanent fix

This runbook describes the recovery procedure. The "permanent fix" depends on the originating incident — link to that runbook in the postmortem.

## Post-restore validation

```bash
# Schema head matches code
alembic current
alembic heads

# Row counts vs. expected
psql -c "SELECT 'users' AS table, count(*) FROM users
         UNION ALL SELECT 'invoices', count(*) FROM invoices
         UNION ALL SELECT 'tenants', count(*) FROM tenants;"

# Latest record per high-volume table
psql -c "SELECT max(created_at) FROM audit_log;"

# Application smoke test
curl -fsS https://app.example.com/api/v1/healthz
curl -fsS https://app.example.com/api/v1/readyz
```

## Restart application

```bash
sudo systemctl start ec-backend ec-frontend
sudo journalctl -u ec-backend -f
```

Watch the log for 5 minutes. Verify a test login succeeds.

## Postmortem checklist

- [ ] What was the RTO (start of restore → app back up)?
- [ ] What was the RPO (last record in restored snapshot)?
- [ ] Were there any data conflicts (records ingested between snapshot and incident)?
- [ ] If yes, were they re-applied from a secondary source (audit log / event bus)?
- [ ] Update the customer status page.
- [ ] Schedule a DR-drill cadence review.
