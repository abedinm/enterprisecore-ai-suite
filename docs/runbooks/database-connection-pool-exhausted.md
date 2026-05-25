# Runbook — Database connection pool exhausted

## Symptoms

- Backend logs flooded with `QueuePool limit of size N overflow M reached, connection timed out`.
- Customer-facing 500 errors with body `{"error": "service unavailable", "code": "db_unavailable"}`.
- `ec_http_requests_total{status="503"}` rate climbing.
- Postgres `pg_stat_activity` close to `max_connections`.

## Severity

- **Sev 1** — the application is intermittently unavailable. Page immediately.

## Immediate mitigation

1. See what Postgres sees:

   ```bash
   psql -c "SELECT count(*) AS connections,
                   sum((state='active')::int) AS active,
                   sum((state='idle')::int) AS idle,
                   sum((state='idle in transaction')::int) AS idle_in_txn
            FROM pg_stat_activity
            WHERE datname='enterprisecore';"

   psql -c "SHOW max_connections;"
   ```

2. Identify offenders:

   ```bash
   psql -c "SELECT pid, usename, application_name, state,
                   now() - state_change AS state_duration,
                   substr(query, 1, 100) AS query
            FROM pg_stat_activity
            WHERE datname='enterprisecore'
              AND state != 'idle'
            ORDER BY state_change ASC
            LIMIT 30;"
   ```

3. Kill long-running idle-in-transaction sessions (they hold locks AND pool slots):

   ```bash
   psql -c "SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE state='idle in transaction'
              AND state_change < now() - interval '5 minutes'
              AND datname='enterprisecore';"
   ```

4. Rolling restart of the backend will recycle pools cleanly:

   ```bash
   kubectl rollout restart deploy/ec-backend
   ```

5. If `max_connections` is the bottleneck, deploy a pooler (PgBouncer in transaction mode) in front:

   ```bash
   # see deploy/pgbouncer/ for the chart
   helm install pgbouncer deploy/pgbouncer -n data
   ```

## Root cause investigation

Common causes:

- **Connection leak** — a code path that opens a session but never closes it. Search for new `Session()` outside the dependency-injection scope: `grep -rn "SessionLocal()" backend/app`.
- **Long-running transactions.** Look for missing `commit()` / `rollback()`. The audit query above with `idle in transaction` > 5 min surfaces these.
- **Sudden traffic spike** — see `high-cpu-on-backend.md`.
- **Pool size too small for traffic** — check `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` in env.
- **A connection-hogging worker** (e.g., bulk importer) running without using the job queue.

Histogram of query durations:

```promql
histogram_quantile(0.99,
  sum by (le, operation) (rate(ec_db_query_duration_seconds_bucket[5m]))
)
```

## Permanent fix

- Use the dependency-injected session everywhere; `Session()` should not appear in endpoint code.
- Set `pool_pre_ping=True` (already the default) so dead connections are detected.
- Tune `DATABASE_POOL_SIZE` to (worker count × 2) + 5; `DATABASE_MAX_OVERFLOW` to half that.
- Deploy PgBouncer in transaction mode for tenants > ~50.
- Add a watchdog metric `db_idle_in_transaction_seconds` and alert at > 60 s.

## Postmortem checklist

- [ ] Was the offending code path identified?
- [ ] Is there a unit test that would have caught the leak?
- [ ] Is the alert threshold appropriate (fires before service degrades)?
- [ ] PgBouncer rollout decision documented.
