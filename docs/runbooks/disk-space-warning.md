# Runbook — Disk space warning

## Symptoms

- Alert `DiskUsageHigh` firing: `node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15`.
- Application errors like `IOError: No space left on device`.
- Backups failing — see `database-backup-failed.md`.
- Postgres logs `PANIC: could not write to file ... No space left on device`.

## Severity

- **Sev 2** at <15% free, >5% free remaining.
- **Sev 1** at <5% free OR Postgres is impacted.

## Immediate mitigation

1. Find the biggest consumers:

   ```bash
   df -h
   sudo du -h --max-depth=1 / 2>/dev/null | sort -h | tail
   ```

2. Quick wins (in order):

   ```bash
   # Old journal logs
   sudo journalctl --vacuum-time=2d

   # Docker — dangling images / unused volumes
   sudo docker system df
   sudo docker system prune -af --volumes

   # Pip / npm caches
   sudo rm -rf /root/.cache /home/*/.cache/pip /home/*/.cache/yarn

   # apt
   sudo apt-get clean
   ```

3. Application-specific:

   ```bash
   # EnterpriseCore log directory
   sudo find /var/log/ec -type f -name "*.log.*" -mtime +7 -delete

   # Storage uploads — if S3-backed, local cache is purgeable
   sudo find /var/lib/ec/storage-cache -type f -atime +14 -delete

   # Backup staging
   sudo find /var/lib/postgresql/backups -type f -mtime +3 -delete
   ```

4. If Postgres is on the affected volume, **never** delete inside its data dir. Instead grow the volume:

   ```bash
   # AWS EBS
   aws ec2 modify-volume --volume-id $VOL --size $NEW_SIZE
   sudo growpart /dev/nvme0n1 1
   sudo resize2fs /dev/nvme0n1p1   # ext4
   sudo xfs_growfs /                # XFS
   ```

## Root cause investigation

- Steady growth → capacity planning issue. Look at `node_filesystem_avail_bytes` over 90 days.
- Step jump → identify the moment from the metric and correlate with deploys / large imports / new tenants.
- Postgres bloat — table bloat with old MVCC tuples. Check:

  ```sql
  SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
  FROM pg_catalog.pg_statio_user_tables
  ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;
  ```

  Run `VACUUM (VERBOSE, ANALYZE) <table>` on offenders, or `pg_repack` for large heaps.

- Log file growth — application logging at DEBUG by mistake. Check `LOG_LEVEL` env.

## Permanent fix

- Tighten `logrotate` rules: 7 days local, ship to log aggregator.
- Configure storage-cache TTL.
- Add `DiskGrowthRate` alert at 5% / day.
- Add capacity-plan review to monthly ops cadence.

## Postmortem checklist

- [ ] Was the alert too late (did the disk fill before alert fired)?
- [ ] Are autoscaling-volume policies in place for EBS / managed disks?
- [ ] Is Postgres on a dedicated volume (it should be)?
