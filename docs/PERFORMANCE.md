# Performance baseline and scaling

This document describes the expected performance characteristics of EnterpriseCore at a reference workload, identifies the common bottlenecks, and gives scaling recommendations.

It is the document to read when:

- A customer asks "how big a machine do we need?"
- An engineer is investigating a latency regression.
- An operator is sizing the database for an upgrade.
- A prospect is evaluating us against a competitor.

---

## Reference workload

When we publish numbers we use a defined reference workload so the numbers are meaningful:

- **50 tenants** with mixed activity.
- **100 users** across those tenants (~2 users/tenant on average; long-tail up to 20).
- **10 000 invoices** total (~200/tenant average).
- **1 000 customers** total in CRM-style modules.
- **500 construction projects** with **5 000 daily logs** and **1 000 RFIs**.
- **30 days** of audit log retained, ~2 000 events/day.
- **5 web chat bots** across all tenants, **500 messages/day**.
- **20 active integrations** (Slack / Google / Zapier / generic webhooks).

This is the dataset used to seed the performance test environment via `scripts/perf/seed_reference.sh` (TODO when Wave 5 lands).

---

## Reference host

Baseline numbers below are measured on:

- **CPU:** 4 cores (Intel Xeon Cascade Lake or AMD EPYC equivalent, ~3 GHz sustained).
- **Memory:** 16 GB.
- **Disk:** NVMe SSD, ~3 000 IOPS sustained.
- **Network:** 1 Gbps.
- **OS:** Ubuntu 22.04 LTS.
- **Postgres:** 16, default tuning + `shared_buffers=4GB`, `effective_cache_size=12GB`, `random_page_cost=1.1`.
- **Backend:** uvicorn with 4 workers (one per core).
- **Frontend:** static build served by nginx, gzip enabled, HTTP/2.

Numbers degrade gracefully when ANY one of these is halved; numbers scale linearly when all are doubled up to ~8 cores / 32 GB.

---

## Expected baselines

| Operation | Target p50 | Target p95 | Target p99 |
|---|---|---|---|
| Dashboard initial load (API + render) | 250 ms | **500 ms** | 900 ms |
| Search across 100 K records (full-text) | 90 ms | **300 ms** | 700 ms |
| Invoice list page (50 rows + facets) | 70 ms | 200 ms | 450 ms |
| Create-invoice POST | 80 ms | 250 ms | 500 ms |
| PDF generation (5-page invoice) | 600 ms | **2 s** | 4 s |
| AI chat first token (Ollama local, 7B model, RTX 4060+) | 250 ms | 700 ms | 1.5 s |
| AI chat sustained throughput (Ollama local, 7B model, RTX 4060+) | — | **~100 tokens/sec** | — |
| Stripe webhook processing | 50 ms | 200 ms | 400 ms |
| Tenant signup → first-login | — | 4 s | 8 s |
| GDPR export (single tenant, reference dataset) | — | 8 s | 20 s |

The **bold** rows are the customer-facing SLOs we publish.

---

## Throughput baselines

Sustained over a 30-minute test on the reference host:

- HTTP requests: **~1 200 RPS** with mixed read/write traffic before p95 exceeds 500 ms.
- Background jobs: **~80 jobs/sec** at average payload (resume-screening, importer rows, webhook deliveries).
- Webhook deliveries: **~200 deliveries/sec** to a responding receiver.
- Audit-stream events: **~5 000 events/sec** to a responding sink.

---

## Where the time goes

Typical mix of a 200 ms dashboard request:

```
client TLS + HTTP/2     8 ms
nginx proxy             3 ms
uvicorn -> app          5 ms
auth + tenant context   12 ms   <-- DB roundtrip
ORM queries (4 queries) 90 ms   <-- DB roundtrip x4
serialisation           18 ms
gzip                    4 ms
network return          15 ms
client render           45 ms
                       ----
                       ~200 ms
```

Notes:

- Database accounts for ~50% of latency. The single highest-leverage optimisation is reducing query count and round-trip count (Eager loading, batching, materialised views).
- Network is non-trivial for distant customers; CDN-edge caching of static assets and gzip-ing JSON cuts perceived latency materially.
- Client render is dominated by hydration; the bundle-size budget in `scripts/bundle-report.js` is the gate.

---

## Bottleneck identification

The order of operations when investigating slowness:

### 1. Confirm with metrics

- Grafana → EnterpriseCore Overview → HTTP latency p95 panel. Is the regression global or one endpoint?
- Click through to the AI / Billing / Tenants dashboards if scoped.

### 2. Slow-query log

Enable for the duration of investigation:

```sql
ALTER SYSTEM SET log_min_duration_statement = '100ms';
SELECT pg_reload_conf();
```

Aggregate top offenders:

```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC LIMIT 20;
```

Reset stats after fixing so the next investigation starts clean:

```sql
SELECT pg_stat_statements_reset();
```

### 3. py-spy on a live worker

Read-only sampling profiler, low overhead:

```bash
pip install py-spy
sudo py-spy top --pid $(pgrep -f uvicorn | head -1)
sudo py-spy record -o /tmp/flame.svg --pid $(pgrep -f uvicorn | head -1) --duration 30
```

### 4. Sentry performance

If Sentry tracing is enabled (`SENTRY_TRACES_SAMPLE_RATE > 0`), filter by `transaction:<route>` to see which spans dominate.

### 5. OpenTelemetry / Tempo

Distributed traces give end-to-end timing including external API calls (Stripe, AI providers, integrations).

### 6. Frontend

```bash
cd frontend && npm run bundle-report
npx lighthouse https://app.example.com/dashboard --view
```

Watch for bundle growth, third-party scripts, and unused JS.

---

## Scaling recommendations

EnterpriseCore scales vertically and horizontally with predictable rules of thumb.

### When to add backend replicas

- CPU sustained > 60% across all workers for 10 minutes.
- p95 latency > 750 ms for the dashboard endpoint.
- In-flight requests > 80% of worker count.

Two replicas should be the floor for any production deployment so a single host loss does not produce an outage.

### When to scale the database vertically

- `pg_stat_activity` regularly at >75% of `max_connections` after PgBouncer.
- `pg_stat_database.blks_read / blks_hit` ratio > 5% (cache misses).
- WAL write rate sustained > 50% of disk IOPS.

Move from 4-core to 8-core when first triggered; from 8 to 16 when triggered again. Past 16 cores, consider read replicas before further scale-up.

### When to add read replicas

- Read traffic ≫ write traffic (typical EnterpriseCore ratio is 4:1).
- Dashboards / reports are a significant fraction of load.
- The `read_only_db` connection string is configured in the app (the ORM is read-replica-aware).

### When to shard

We do NOT recommend sharding until:

- Single-database total size > 500 GB AND can't be helped by archival.
- Or write rate > 5 000 TPS sustained.

Below those thresholds vertical scale + read replicas is cheaper and simpler.

The natural shard key is `tenant_id` (every table is already tenant-scoped). The migration path: deploy two physical databases, route writes by tenant_id hash. Complex — engage the database lead.

### When to move from SQLite to Postgres

EnterpriseCore self-hosted ships with SQLite as the default for single-user evaluation. Move to Postgres when:

- Concurrent users > 5.
- Tenants > 3.
- Tests fail with `database is locked` errors under realistic load.

There is no migration script bundled — re-deploy with `DATABASE_URL=postgresql://...` from scratch, then use the importer to bring data over.

### Ollama / GPU sizing

Rule of thumb for local LLM inference:

| Model size | Min VRAM | RTX 4060 (8GB) | RTX 4090 (24GB) | A100 40GB |
|---|---|---|---|---|
| 3B | 4 GB | ~120 tok/s | ~250 tok/s | ~400 tok/s |
| 7B | 7 GB | ~100 tok/s | ~180 tok/s | ~300 tok/s |
| 13B | 13 GB | does not fit | ~120 tok/s | ~200 tok/s |
| 34B | 24 GB | does not fit | tight; quantise | ~120 tok/s |
| 70B | 40 GB | does not fit | does not fit | ~50 tok/s |

For concurrency, plan for ~1 concurrent user per model loaded, not per GPU. The default `OLLAMA_NUM_PARALLEL=4` is conservative; raise it after observing GPU memory headroom.

---

## Anti-patterns

Things we have measured to be slow, in order of how often we see them:

- **`.all()` over a multi-thousand-row table** without pagination — load times grow linearly with table size; switch to streaming or pagination.
- **N+1 queries from a serialiser** — always join or use `selectinload()` in the service layer.
- **Synchronous webhook delivery on the request path** — should go through the job queue.
- **Loading a whole file into memory** instead of streaming during import/export.
- **Per-row INSERT** in bulk operations — use `INSERT ... VALUES (...), (...), (...)` or `COPY`.
- **No index on the foreign key used in dashboard queries** — every new table needs the tenant_id index in the migration.
- **Logging at DEBUG in production** — log volume gates disk and aggregator cost.

---

## How we measure

The numbers in this document come from:

1. Synthetic load tests in `scripts/perf/` using `k6` against the reference deployment.
2. Production telemetry from a designated reference tenant (anonymous, fictional dataset).
3. Annual measurement campaign; numbers updated each release that materially changes runtime characteristics.

If you find a real-world number meaningfully different from a target above, file an issue with the metric, the dataset size, and the host specs.
