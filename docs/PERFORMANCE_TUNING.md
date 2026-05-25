# Performance Tuning Guide

How to keep EnterpriseCore fast as a tenant's data grows. Companion
document to [PERFORMANCE.md](PERFORMANCE.md), which covers user-facing
latency targets. This document is for the engineer who needs to figure
out *why* an endpoint got slow and what to do about it.

---

## 1. Reference Workload

The defaults are tuned for the following per-tenant scale, which our
performance tests use as the upper bound for "small to mid customer":

| Entity              | Rows  | Notes                                        |
| ------------------- | ----- | -------------------------------------------- |
| Invoices            | 10000 | 12-month rolling window of issued + draft   |
| Customers           | 1000  | Active accounts                              |
| Tasks               | 5000  | Across all projects                          |
| Knowledge documents | 500   | RAG corpus                                   |
| Webchat messages    | 50000 | 30-day rolling                               |
| Tenants in install  | 50    | Shared backend, isolated by ORM auto-filter  |

A "fully loaded" install spans roughly 50 of these tenants on the same
Postgres database. The ORM tenant auto-filter
(`app/core/tenant_orm.py`) ensures every query is single-tenant-scoped
under the hood, so capacity planning multiplies by tenant count.

---

## 2. How to Find a Slow Query

### 2.1 Slow-query log (production)

Set `QUERY_PERF_LOG=1` to enable the per-cursor timing hook installed
by `app/db/session.py`. Statements slower than
`QUERY_PERF_THRESHOLD_MS` (default 50 ms) emit a WARN log line of the
form:

```
WARNING  app.db.query_perf: slow_query ms=148.3 sql=SELECT invoices.id, invoices.total ...
```

Pipe those into Loki / Grafana / Sentry's logs panel. Production
deployments should leave the hook *off* (small overhead per statement)
unless actively investigating.

### 2.2 EXPLAIN QUERY PLAN (sqlite) / EXPLAIN (postgres)

Once you have a candidate SQL, run it directly:

```bash
sqlite3 storage/enterprisecore.db "EXPLAIN QUERY PLAN <paste sql>"
```

Look for `SCAN <table>` (sequential scan, slow) vs `SEARCH USING INDEX
<name>` (index hit, fast). If it's a SCAN, an index is missing — add
it in a new alembic migration following the
`alembic/versions/0024_perf_indexes.py` pattern (idempotent, probes
for table + columns + existing index before creating).

### 2.3 N+1 detection (tests + dev)

`app/services/query_perf.py` exposes a `count_queries(engine)` context
manager. Drop it around any endpoint call to see the per-statement
trace:

```python
from app.services.query_perf import count_queries

with count_queries(engine) as q:
    client.get("/api/v1/projects/analytics", headers=auth_headers)
print(q.count, q.by_table())
```

`tests/test_n_plus_one_audit.py` uses this to pin a query budget for
every hot endpoint — when a future PR accidentally reintroduces an
N+1, the test fails with the actual count + the table breakdown so
the cause is obvious. Add a new test for every new dashboard-style
rollup you introduce.

---

## 3. Eliminating N+1 Patterns

The signature of an N+1 in this codebase is a Python `for` loop that
issues a query per row. Fix patterns:

### 3.1 Per-parent child fetch → bulk + group

**Before:**

```python
projects = db.scalars(select(Project)).all()
for p in projects:
    tasks = db.scalars(select(Task).where(Task.project_id == p.id)).all()
    ...
```

**After:**

```python
projects = db.scalars(select(Project)).all()
from app.services.query_perf import bulk_by_parent
tasks_by_project = bulk_by_parent(
    db, Task, Task.project_id, [p.id for p in projects],
)
for p in projects:
    tasks = tasks_by_project[p.id]
    ...
```

Or replace with a single aggregate when you only need counts/sums:

```python
rows = db.execute(
    select(Task.project_id, Task.status, func.count(Task.id))
    .where(Task.project_id.in_(project_ids))
    .group_by(Task.project_id, Task.status)
).all()
```

### 3.2 Per-row relationship traversal → eager loading

When rendering a list of parents that each touch one or more
relationships in the response, use the `with_eager` helper to attach
`selectinload`:

```python
from app.services.query_perf import with_eager

stmt = with_eager(select(Invoice).limit(50), Invoice.lines)
invoices = db.scalars(stmt).all()
```

`selectinload` runs one extra query with `WHERE FK IN (...)` rather
than an outer-join, which is the right shape for our many-to-many
dashboard rollups.

### 3.3 Per-sprint aggregate → grouped aggregate

The project-analytics endpoint previously did one `SUM(story_points)`
per active sprint. The rewrite uses one `GROUP BY sprint_id` query
regardless of sprint count. Pattern applies anywhere you have N rows
and need a single scalar per row from a child table.

---

## 4. Response Caching

`app/core/cache.py` provides a `@cache_response` decorator for safe GET
endpoints. **What "safe" means:** the response is the same for every
caller in the same tenant, and changes infrequently enough that a
stale answer for the cache TTL is acceptable.

### 4.1 Currently cached

| Endpoint                              | TTL    | Invalidation                                   |
| ------------------------------------- | ------ | ---------------------------------------------- |
| `GET /api/v1/license/features`        | 5 min  | License activate/deactivate                    |
| `GET /api/v1/modules`                 | 5 min  | License activate/deactivate (catalog re-filter)|
| `GET /api/v1/rbac/permissions`        | 1 hour | Custom-role create/update/delete                |
| `GET /api/v1/billing/plans`           | 1 hour | None — pricing changes only on deploy           |
| `GET /api/v1/integrations/catalog`    | 1 hour | None — connector list is process-static         |
| `GET /api/v1/importers`               | 1 hour | None — importer list is process-static          |
| `GET /api/v1/workflows/action-types`  | 1 hour | None — action types are process-static          |
| `GET /api/v1/gdpr/data-categories`    | 1 hour | None — data categories are process-static       |

### 4.2 What we explicitly DO NOT cache

* Any endpoint returning tenant-data (invoices, customers, deals,
  tasks, contacts, messages) — the staleness window would cause the
  UI to show out-of-date totals after a mutation.
* Anything user-specific (notifications, jobs you created, recent
  activity) — the cache decorator can fold user-id in via
  `include_user=True`, but the hit rate is too low to justify the
  memory cost.
* Anything that depends on a query parameter we cannot deterministically
  fold into the key — use `vary_by=(...)` to declare every meaningful
  parameter explicitly.

### 4.3 Cache invalidation rules

Use `cache.invalidate_for_tenant(namespace)` from inside the mutating
endpoint. Pattern: any handler that changes the data a cached endpoint
returns must call invalidate on commit.

```python
db.commit()
invalidate_for_tenant("rbac:permissions")
return result
```

Don't try to be clever — wipe the whole namespace for the tenant. The
hit rate after the next miss-then-fill is fast enough that selective
invalidation rarely pays off.

### 4.4 Optional Redis backend

Set `REDIS_URL` in the environment (via a new field on `Settings` if
not already present) to switch the cache backend from in-process to
Redis. The Redis path is best-effort — any Redis error falls back to
the in-process backend so a temporary Redis outage doesn't take down
the cache layer.

---

## 5. Index Strategy

Every model that uses `TenantMixin` gets `tenant_id` indexed
automatically by the auto-filter migration (`0013_multitenant`).
**Composite indexes** layer ``(tenant_id, <hot column>)`` on top:

| Table                  | Composite                              | Why                                                  |
| ---------------------- | -------------------------------------- | ---------------------------------------------------- |
| invoices               | `(tenant_id, status)`                  | Dashboard outstanding / overdue queries              |
| invoices               | `(tenant_id, status, created_at)`      | Sorted lists within a status bucket                  |
| deals                  | `(tenant_id, stage)`                   | CRM pipeline view                                    |
| tasks                  | `(tenant_id, status)`                  | Project analytics open-task counts                   |
| tasks                  | `(project_id, status)`                 | Per-project task aggregate (N+1 fix relies on this)  |
| knowledge_documents    | `(kb_id, status)`                      | Ingest worker scan                                   |
| knowledge_documents    | `(tenant_id, status)`                  | Knowledge dashboard                                  |
| webchat_conversations  | `(last_message_at)`                    | Bot inbox ORDER BY                                   |
| expenses               | `(tenant_id, date)`                    | P&L date-range scan                                  |

Adding a new composite: bump the next alembic version, follow the
`0024_perf_indexes.py` template (idempotent + per-step probe).

---

## 6. Bulk Operations

For inserting / updating / deleting many rows at once, **never** use a
Python loop with `db.add()` + `db.commit()` per row. Patterns:

### 6.1 Bulk insert

```python
db.bulk_save_objects([Model(...) for row in rows])
db.commit()
```

`bulk_save_objects` skips relationship cascading and the unit-of-work
identity map, so it's an order of magnitude faster but you lose the
`before_insert` event listeners. The tenant auto-set listener fires on
`before_insert`, so for tenant-scoped rows pre-fill `tenant_id`
explicitly when using bulk inserts.

### 6.2 Bulk update

```python
db.execute(
    update(Task)
    .where(Task.project_id == project_id, Task.status == "todo")
    .values(status="done")
)
db.commit()
```

The auto-filter splices `tenant_id` into the WHERE on UPDATE/DELETE the
same way it does for SELECT, so cross-tenant leaks are impossible by
construction.

### 6.3 Bulk delete

```python
db.execute(delete(Task).where(Task.project_id == pid))
db.commit()
```

ORM-level `db.query(Task).filter(...).delete()` also works; the SQL
shape is identical.

---

## 7. Connection Pool Tuning

The engine in `app/db/session.py` uses SQLAlchemy's default pool with
`pool_pre_ping=True`. For production Postgres we recommend:

| Setting                  | Default | Production         |
| ------------------------ | ------- | ------------------ |
| `pool_size`              | 5       | 20                 |
| `max_overflow`           | 10      | 20                 |
| `pool_recycle` (seconds) | -1      | 1800 (30 min)      |
| `pool_pre_ping`          | True    | True               |

Pass these via env-var overrides on `_make_engine()` in
`app/db/session.py` once you have real production traffic. Until then
the defaults are fine — the pool is per-worker, so 4 workers × 5
connections = 20 against Postgres, which a single-CPU instance handles
comfortably.

For SQLite (the default for self-hosted / Electron-packaged installs),
ignore pool size — SQLite serializes writes anyway. Make sure
`PRAGMA journal_mode=WAL` is set (already done in
`_enable_sqlite_fk`); it's the single biggest single-tenant win.

---

## 8. Worker Count Guidance

The cloud deployment uses uvicorn. Rule of thumb: `workers = 2 * vCPU + 1`.

| Tier                 | vCPU | Workers | Notes                              |
| -------------------- | ---- | ------- | ---------------------------------- |
| Free tier            | 1    | 3       | I/O-bound mostly — 3 is fine        |
| Standard production  | 2    | 5       | Headroom for sync DB calls          |
| High-traffic         | 4    | 9       | After this, scale horizontally      |

The background-job worker (`app/services/jobs_worker.py`) runs as a
separate process pool so a long-running import doesn't starve HTTP
handlers. Keep it at 1-2 workers per instance — RQ handles
concurrency by spawning child processes within each.

---

## 9. Cheat Sheet — When to Reach for What

| Symptom                              | First move                                                            |
| ------------------------------------ | --------------------------------------------------------------------- |
| Endpoint slow under light load       | `count_queries` to confirm N+1; fix with `bulk_by_parent` or aggregate |
| Endpoint slow under heavy load       | `EXPLAIN QUERY PLAN`; add composite index in next alembic migration   |
| Same answer returned a lot           | `@cache_response` with a TTL matching the staleness tolerance         |
| Single user reports stale data       | Cache invalidation missing on the mutating endpoint                   |
| 100 % CPU on the DB                  | Increase `pool_size`; check for missing index causing full scans      |
| 100 % CPU on the API process         | Profile with `py-spy`; usually JSON serialization or Pydantic         |
| Memory growing unboundedly           | Cache backend; switch to Redis or lower the in-memory `max_entries`   |

---

## 10. Adding a New Cached Endpoint

1. Decorate the handler with `@cache_response(ttl=N, namespace="ns:key")`.
2. Add `response: Response` as the first parameter — the decorator sets
   `Cache-Control: private, max-age=N` and `X-Cache: HIT/MISS` headers
   for client + test visibility.
3. If the response varies by anything other than tenant, list those
   parameters via `vary_by=("status", "limit")`. **Do not** list
   tenant-id — it's always folded in automatically from
   `tenant_context`.
4. In every endpoint that mutates the underlying data, call
   `invalidate_for_tenant("ns:key")` after `db.commit()`.
5. Add a test in `tests/test_cache.py` that proves the MISS→HIT
   transition and the mutation→MISS transition.

That's it. Don't optimize ahead of measurement — the slow query log
+ `count_queries` will tell you exactly where the cycles are going.
