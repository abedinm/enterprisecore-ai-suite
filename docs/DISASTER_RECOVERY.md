# Disaster recovery

This document defines EnterpriseCore's disaster-recovery (DR) posture: what we promise customers, what scenarios we plan for, how we recover from each, how often we drill, and who to call.

It is shipped as a template — self-hosted customers should adapt the RTO/RPO tiers and procedures to match their own deployment.

---

## Objectives by tier

EnterpriseCore deployments are classified into three tiers based on the customer's SLA. The tier sets the Recovery Time Objective (RTO — how long until service is restored) and Recovery Point Objective (RPO — how much data we tolerate losing).

| Tier | Customer profile | RTO | RPO |
|---|---|---|---|
| **Tier 1** | Production-critical enterprise customers | 1 hour | 1 hour |
| **Tier 2** | Standard business customers | 4 hours | 4 hours |
| **Tier 3** | Trial / dev / non-production | 24 hours | 24 hours |

What this means concretely:

- **Tier 1:** continuous WAL archival (PITR), warm standby in a second AZ, hourly off-region backup, runbook target 1h.
- **Tier 2:** WAL archival, off-region backup every 4 hours, runbook target 4h.
- **Tier 3:** daily off-region backup, restore on demand.

A deployment's tier is set in `deploy/terraform/<env>/main.tfvars` as `dr_tier=1|2|3`.

---

## Scenarios

We plan and drill against five named scenarios. Each has a defined recovery procedure.

### Scenario A — Availability Zone failure

The primary AZ of the active region becomes unreachable. EBS / RDS / GKE nodes in that AZ are unavailable. Other AZs in the same region remain healthy.

**Recovery:**

1. Application: the load balancer health-checks remove the affected AZ; Kubernetes / ECS reschedules pods to surviving AZs. No manual action if capacity headroom exists.
2. Database: if the primary is in the failed AZ, fail over to the synchronous standby in another AZ. AWS RDS Multi-AZ does this automatically (~60s). For self-managed Postgres, run `repmgr standby promote` on the standby.
3. Verify application can write — `curl /api/v1/readyz` should return 200 after failover.
4. Decommission and replace the failed primary at the customer's leisure.

**RTO target:** <5 minutes (Tier 1), <30 minutes (Tier 2).
**RPO target:** zero (synchronous replication).

### Scenario B — Region failure

The entire primary region is unreachable.

**Recovery:**

1. Confirm region is down via the cloud provider's status page and out-of-band tooling — don't rely on your own monitoring (which may also be in that region).
2. Promote the secondary region's read replicas to read-write — `aws rds promote-read-replica --db-instance-identifier ec-secondary`.
3. Update DNS to point to the secondary region's load balancer. Lower the TTL of the apex record proactively (see weekly checklist) so failover is fast.
4. Verify application and data integrity in the secondary region.
5. Announce on status page.

**RTO target:** 1 hour (Tier 1), 4 hours (Tier 2), 24 hours (Tier 3).
**RPO target:** depends on replication lag; cross-region async replication typically ≤5 minutes.

**Important caveats:** secondary region is configured for read-only by default and may not have the full set of background workers. Bring up the worker fleet in the secondary region as part of the runbook.

### Scenario C — Database corruption

Data is in place but logically corrupt — bad migration, runaway query, software bug, malicious insider.

**Recovery:**

1. **Stop the application** — `kubectl scale deploy/ec-backend --replicas=0` — to prevent further writes against corrupt data.
2. Identify the corruption window. Audit log + Sentry errors + customer reports.
3. Decide on the recovery target time. PITR with WAL archival can target a specific UTC second.
4. Restore: see `docs/runbooks/database-restore.md` for full-database restore, or:
   - **PITR (managed Postgres):** `aws rds restore-db-instance-to-point-in-time --restore-time <iso8601>`.
   - **PITR (self-managed):** stop, restore the last basebackup, replay WAL up to the target.
5. Bring the application back up against the restored database.
6. Reconcile any out-of-band data sources (Stripe, integrations) by replaying events from after the restored point.

**RTO target:** 1-4 hours depending on database size.
**RPO target:** PITR allows zero data loss up to the target second.

### Scenario D — Ransomware / malicious encryption

Live data is encrypted or destroyed by an attacker.

**Recovery:**

1. **Isolate** the affected systems — sever network, revoke credentials, snapshot the volumes for forensics.
2. Page the security lead and outside counsel.
3. Determine whether backups are also affected. Off-site, immutable backups (S3 Object Lock / WORM) should be the safe answer.
4. Build the restore target on a NEW, clean network. Do not restore into the compromised environment.
5. Restore from the most recent backup taken BEFORE the compromise indicator. Carry forward audit logs to identify what changed in between.
6. Coordinate with law enforcement as appropriate.
7. Run security forensics on the snapshots before discarding them.
8. Implement remediation (rotate all secrets, refresh certificates, force password reset for all users).

**RTO target:** 24 hours (regardless of tier — security supersedes performance SLA).
**RPO target:** depends on backup cadence and compromise duration.

Critical: every customer with a Tier 1/2 SLA must have **off-site, immutable backups** verified within the last 30 days. See `scripts/backup/pg_backup.sh` for the AWS Object Lock configuration.

### Scenario E — Accidental data deletion

A user or admin deletes data they shouldn't have. This is the most common DR event.

**Recovery:**

1. Identify the deletion scope and timestamp from audit log.
2. For tenant-scoped deletion within last 30 days, attempt **tenant-only** restore using `scripts/restore/tenant_import.sh` against a snapshot from before the deletion.
3. For row-level deletion, fetch the data from the WAL or a logical backup; apply the inverse INSERT.
4. If the data is recoverable from another system (e.g., the audit log retains the full payload of CRUD events), reconstruct from there to avoid disruption.

**RTO target:** 1 hour for single-tenant; 4 hours for cross-tenant.
**RPO target:** zero if recovered from audit log; up to backup cadence otherwise.

---

## Drill schedule

DR plans rot in storage. We exercise them on a schedule.

- **Monthly:** backup verification (`scripts/backup/pg_backup_verify.sh`) on the latest off-site backup. Runs automatically; on-call reviews the report.
- **Quarterly tabletop:** the engineering team walks through one named scenario (A through E in rotation) verbally — what would we do, who calls whom, where are the runbooks. Lasts ~90 minutes.
- **Annual live drill:** a full, end-to-end failover exercise in a non-production environment cloned from production. We measure actual RTO/RPO against the targets and publish the result internally.

Each drill produces a report in `docs/dr-drills/YYYY-Q<n>.md` with: scenario, participants, timing, observations, action items.

---

## Off-site backups — the non-negotiable

Off-site, encrypted, immutable, regularly verified backups are the single most important DR control. The following are required:

1. **Off the primary host:** copies stored in a different blob store (S3, GCS, Azure Blob).
2. **Off the primary region:** at least one copy in a different region.
3. **Encrypted at rest:** GPG or SSE-KMS with a key the application cannot delete.
4. **Immutable for the retention window:** S3 Object Lock in Compliance mode, GCS retention policy, or Azure Immutability Policy.
5. **Verified:** `pg_backup_verify.sh` restores into a temp DB and runs sanity checks at least monthly.
6. **Retention:** Tier 1: 90 days hot + 1 year cold. Tier 2: 30 days hot + 90 days cold. Tier 3: 7 days hot.

---

## What is NOT backed up

To set expectations:

- **Customer file uploads stored in S3** — durability is the cloud provider's, S3 cross-region replication is configured for Tier 1/2.
- **Search indices** — rebuilt from the database on restore. Reindex job is part of restore.
- **AI provider conversation history** — not retained beyond the customer's data retention setting; not backed up separately.
- **Build artifacts and container images** — pinned by tag and rebuildable from source.
- **The Ollama model files** — re-downloaded on a new host. Pre-pull in the deploy script.

---

## DR contact list

(This list is a placeholder; populate with real contacts.)

| Role | Primary | Secondary | When to call |
|---|---|---|---|
| Incident Commander (IC) | rotating on-call | Secondary on-call | Always for Sev 1 |
| VP Engineering | name + phone | deputy | Multi-hour Sev 1, exec coordination |
| Database lead | name + phone | name | DB corruption, PITR |
| Security lead | name + phone | name | Suspected breach, ransomware |
| CTO | name + phone | n/a | Multi-day outage, media risk |
| Cloud provider TAM | name + phone | account number | AWS / GCP / Azure support escalation |
| Outside counsel | firm + phone | name | Confirmed breach, regulatory notification |
| Insurance broker | firm + phone | policy number | Material loss (>$25k incident cost) |
| Statuspage.io login | shared in password manager | n/a | Posting customer status updates |

Refresh quarterly. Anyone who leaves the company is removed within 24 hours of their last day.

---

## Customer-facing DR commitments

What we publish to customers in the DPA / Service Agreement:

- RTO and RPO targets per tier.
- Backup cadence and retention.
- Off-site backup posture (region count, immutability).
- DR drill cadence (quarterly tabletop, annual live).
- Notification commitments — customer notified within 1 hour of declaring a Sev 1 DR scenario.

We do NOT publish:

- Specific runbook procedures (attacker reconnaissance risk).
- Internal contact details.
- Cryptographic key locations.

---

## Self-hosted customers

Self-hosted customers are responsible for their own DR. EnterpriseCore provides:

- Backup scripts in `scripts/backup/` — work on Linux, parameterised via env vars.
- Restore scripts in `scripts/restore/`.
- This document as a template to copy and adapt.
- Migration / schema-version safety in the application — backups taken from version N can be restored into N+1 without surprise.

We do not provide DR-as-a-service for self-hosted deployments.
