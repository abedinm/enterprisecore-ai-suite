# Upgrade guide

EnterpriseCore is shipped on a continuous-release cadence — minor versions
ship every two weeks, patches as needed, and major versions roughly once a
year. This document is the canonical reference for upgrading between any
two versions, in any of the three deployment shapes.

For the install procedure, see [INSTALL_FOR_ENTERPRISE.md](INSTALL_FOR_ENTERPRISE.md).
For schema details, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md). For DR
recovery, see [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

## Version matrix

| From → To       | Effort                | Schema changes? | Breaking API changes? | Notes                                                  |
| --------------- | --------------------- | --------------- | --------------------- | ------------------------------------------------------ |
| 1.x → 1.(x+1)   | Standard patch        | None or trivial | None                  | Routine — schedule during low-traffic window.          |
| 1.x → 2.0       | Major upgrade         | Likely          | Possible              | Read the version's release notes before scheduling.    |
| 2.x → 2.(x+1)   | Standard patch        | None or trivial | None                  | Routine.                                               |
| Any → newest LTS| Use this guide        | Possibly        | See release notes     | Always upgrade through each major (no version skip).   |

EnterpriseCore follows semantic versioning: `MAJOR.MINOR.PATCH`. The
contract is:

- **PATCH** bumps (e.g. 1.4.2 → 1.4.3): bug fixes, performance,
  documentation. Never breaking. No schema work.
- **MINOR** bumps (e.g. 1.4.x → 1.5.0): new features, additive schema
  changes only (new tables, new nullable columns), backward-compatible
  API additions.
- **MAJOR** bumps (e.g. 1.x → 2.0): can include destructive schema
  changes (only with explicit operator opt-in), removed endpoints,
  renamed event types. Always paired with a migration window.

## General procedure

The procedure is the same in every shape — the commands differ.

```
┌─────────────────┐
│   1. BACKUP     │  Database + uploads volume.
└────────┬────────┘
         ▼
┌─────────────────┐
│   2. ANNOUNCE   │  In-app banner + status page if downtime is expected.
└────────┬────────┘
         ▼
┌─────────────────┐
│   3. PULL IMAGE │  Pull the new container / package the new binary.
└────────┬────────┘
         ▼
┌─────────────────┐
│   4. MIGRATE    │  alembic upgrade head — schema is forward-compatible
│                 │  with the OLD code, so you can run it before cutover.
└────────┬────────┘
         ▼
┌─────────────────┐
│   5. CUT OVER   │  Rolling restart pods (K8s) or swap binaries (compose).
└────────┬────────┘
         ▼
┌─────────────────┐
│   6. VERIFY     │  /api/health, login flow, one read + one write per
│                 │  critical module, audit log shows expected entries.
└────────┬────────┘
         ▼
┌─────────────────┐
│   7. WATCH      │  4xx/5xx rate, p95 latency, error budget for 60 min.
└─────────────────┘
```

If you don't manage your own schema, EnterpriseCore's Helm chart ships a
pre-rollout hook that runs step 4 for you. The chart blocks the rollout
until the migration job exits cleanly.

## Rolling upgrade on Kubernetes

```bash
# 1. Backup Postgres (your operator's preferred way).
kubectl -n enterprisecore exec postgres-0 -- pg_dump -Fc enterprisecore \
    > backup-$(date +%Y%m%d-%H%M%S).dump

# 2. Bump the Helm chart version.
helm repo update
helm upgrade enterprisecore enterprisecore/enterprisecore \
    --namespace enterprisecore \
    --values values.production.yaml \
    --version 1.5.0 \
    --atomic --timeout 15m

# 3. Watch the rollout.
kubectl -n enterprisecore rollout status deploy/enterprisecore-backend
kubectl -n enterprisecore get pods

# 4. Smoke test.
curl -fsSL https://<host>/api/health | jq
```

`--atomic` makes the upgrade self-rollback if any pod fails its readiness
probe. The chart uses `RollingUpdate` strategy with `maxSurge=1,
maxUnavailable=0` — every replica boots on the new image before any old
replica is terminated.

## docker-compose upgrade on a single VM

```bash
cd /opt/enterprisecore

# 1. Backup.
docker compose exec -T postgres pg_dump -Fc -U enterprisecore enterprisecore \
    > backups/db-$(date +%Y%m%d-%H%M%S).dump
tar czf backups/uploads-$(date +%Y%m%d-%H%M%S).tgz storage/uploads

# 2. Pull the new images.
git fetch --tags
git checkout v1.5.0
docker compose pull

# 3. Run migrations against the running database BEFORE cutting over —
# minor releases keep N-1 compatibility, so old pods still serve traffic.
docker compose run --rm backend alembic upgrade head

# 4. Restart the stack.
docker compose up -d
docker compose ps

# 5. Smoke test.
curl -fsSL https://<host>/api/health | jq
```

## Desktop upgrade

The Desktop builds (Windows .exe, macOS .dmg, Linux .AppImage) self-update
via the Electron auto-updater configured in
[AUTO_UPDATE.md](AUTO_UPDATE.md). Users are prompted when a new release is
available; the embedded SQLite schema is migrated on the next boot.

For air-gapped Desktop installs, fetch the new installer from your
internal mirror and run it; the migration runs as part of the first
launch.

## Schema migration safety

EnterpriseCore's Alembic migrations follow strict rules:

1. **Never destructive without consent.** A migration that drops a
   column, drops a table, or coerces a column type to a stricter shape
   must be guarded by the `EC_ALLOW_DESTRUCTIVE_MIGRATIONS=1` environment
   variable. Without it the migration aborts before issuing the DDL.
2. **Idempotent.** Every migration is safe to re-run. The Alembic
   version table catches double-application; the DDL itself uses
   `IF NOT EXISTS` / `IF EXISTS` guards so a half-applied migration can
   be re-tried without manual cleanup.
3. **Forward-only by default.** Down-migrations exist for development
   convenience only — production rollbacks are done by restoring the
   pre-migration backup, not by running `alembic downgrade`. The
   `RELEASE_PROCESS.md` spec details when a down-migration is actually
   safe.
4. **Additive within a MINOR.** New columns added in a MINOR release are
   nullable or have a server-side default. Old code keeps working
   against the new schema, which lets the upgrade interleave (migrate
   first, then swap pods).

## Downgrade procedure

Downgrade is intentionally limited — most schema work is forward-only.
The supported downgrade procedure is:

1. **Stop traffic** to the new version.
2. **Restore the pre-upgrade database backup.** This is the canonical
   rollback — the backup was taken at step 1 of the upgrade procedure.
3. **Pull the old container image** and bring it back up.

Attempting `alembic downgrade -1` is **only** supported when the
migration's docstring explicitly says so. Many of EnterpriseCore's
migrations are tagged `safe_downgrade: false` because they involve data
backfill that cannot be unwound in-place.

## Breaking changes — major versions

There have not yet been any major version bumps for EnterpriseCore. When
the first one ships, this section will read like:

> ### 1.x → 2.0
>
> **Breaking API changes**
> - `POST /api/v1/leads` — `assigned_to_id` is now required.
> - Deprecated `GET /api/v1/billing/usage` (use `/api/v1/billing/usage/summary`).
>
> **Breaking event types**
> - `crm.lead.created` payload now carries `tenant_plan` (additive — old
>   subscribers continue to work but new fields appear).
>
> **Destructive schema migrations**
> - `alembic upgrade 2.0_head` drops the legacy `webchat_messages_old`
>   table. Set `EC_ALLOW_DESTRUCTIVE_MIGRATIONS=1` to proceed.
>
> **Removed CLI flags**
> - `--legacy-auth` removed.
>
> **Operator action required**
> - Update any webhook receivers that pinned to the old event payload.
> - Rerun the SSO + SCIM mapping wizard — the schema changed.

Until then, every release falls under the routine MINOR/PATCH cadence
above.

## Pre-upgrade checklist

For any non-PATCH upgrade:

- [ ] Read the release notes for every intermediate MINOR.
- [ ] Confirm at least one verified backup younger than 24 hours.
- [ ] Confirm `/metrics` and the on-call dashboards are healthy.
- [ ] Schedule the window during low-traffic hours.
- [ ] Notify on-call rota.
- [ ] Pin the new image tag in version control before deploying it.
- [ ] Have the rollback runbook open in a second tab.

## Post-upgrade checklist

- [ ] `/api/health` returns 200 and the new version number.
- [ ] The login flow works against SSO.
- [ ] A read + a write succeed in each top-level module the customer
      uses (CRM, Finance, HR, Projects, Construction, etc.).
- [ ] No new error budget burn in the first 60 minutes.
- [ ] Audit log shows the operator's upgrade activity.
- [ ] Webhook deliveries continue to succeed (look at the dashboard).
- [ ] AI metering still records usage (a synthetic call to
      `/api/v1/ai/complete`).
