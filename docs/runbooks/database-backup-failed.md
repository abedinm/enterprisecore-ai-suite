# Runbook — Database backup failed

## Symptoms

- PagerDuty / alertmanager firing `BackupJobFailed` for the EnterpriseCore Postgres backup.
- The nightly cron / systemd timer / Kubernetes CronJob `ec-pg-backup` exits non-zero.
- Slack `#ec-ops` shows `pg_backup.sh: exit 1 — see /var/log/ec-backup/<date>.log`.
- `aws s3 ls s3://ec-backups/<env>/` shows no new object for the day.

## Severity

- **Sev 2** if a single backup fails and the previous backup is <25 hours old. Page during business hours.
- **Sev 1** if two consecutive backups have failed OR the most recent successful backup is >48 hours old. Page immediately — RPO breach in progress.

## Immediate mitigation

1. Confirm the alert is real:

   ```bash
   aws s3 ls "s3://ec-backups/$ENV/" --recursive | tail -5
   ```

2. Trigger a manual backup attempt:

   ```bash
   sudo -u postgres /opt/ec/scripts/backup/pg_backup.sh
   echo "exit=$?"
   ```

3. If the manual run succeeds, the cron context is the problem — investigate environment / permissions. If it fails, capture the full log and continue.

4. If 24 hours from the last good backup is about to elapse, take a quick logical dump locally as a safety net:

   ```bash
   sudo -u postgres pg_dump -Fc enterprisecore > /var/lib/postgresql/emergency-$(date -u +%Y%m%dT%H%M).pgc
   ```

## Root cause investigation

Common causes, in order of frequency:

- **Disk full** on the host running pg_dump. Check `df -h /var/lib/postgresql /tmp`.
- **S3 credentials expired** or IAM role rotated. Check `~/.aws/credentials` mtime; run `aws sts get-caller-identity`.
- **GPG key missing** (if encrypting at rest with GPG). Check `gpg --list-keys` for the expected backup key.
- **Network / S3 endpoint unreachable.** Try `curl -v https://s3.amazonaws.com/` from the host.
- **pg_dump version skew** — minor-version mismatch between pg_dump and the server can fail. Check `pg_dump --version` vs `psql -c 'SELECT version();'`.
- **Backup script change** in the last 24h — check `git log -p scripts/backup/pg_backup.sh`.

Useful queries:

```bash
# tail the log
tail -200 /var/log/ec-backup/$(date -u +%Y-%m-%d).log

# disk
df -h
du -sh /var/lib/postgresql/*

# S3 perms
aws s3 cp /etc/hostname s3://ec-backups/$ENV/_perm-check.txt && \
  aws s3 rm s3://ec-backups/$ENV/_perm-check.txt
```

## Permanent fix

- Out of disk → either grow the volume or move `BACKUP_TMP_DIR` to a larger mount. See `scripts/backup/README.md`.
- Credentials rotated → update the instance role / `~/.aws/credentials`; re-encrypt the `.env` if checked into a secret manager.
- pg_dump skew → align versions; the recommended deployment pattern is to run pg_dump from a container pinned to the same major version as the server (image tag in `scripts/backup/README.md`).
- Script regression → revert via `git revert <sha>`; add a test in `scripts/backup/tests/`.

## Postmortem checklist

- [ ] How long was the RPO exceeded?
- [ ] Was alerting timely (page fired within 15 minutes of failure)?
- [ ] Did the emergency-dump path work?
- [ ] Is the underlying cause monitored (e.g., disk-space alert at 80%)?
- [ ] Schedule the action items in the next sprint.
