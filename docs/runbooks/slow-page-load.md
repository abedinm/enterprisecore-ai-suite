# Runbook — Slow page load

## Symptoms

- Customer reports "the dashboard takes 5+ seconds to load."
- RUM (Sentry / Web-Vitals) shows LCP > 4 s, INP > 200 ms.
- Synthetic check `dashboard-load` failing the 2s SLO.

## Severity

- **Sev 3** for one customer with no SLA breach.
- **Sev 2** if multiple customers AND the SLO is breached for >10 minutes.

## Immediate mitigation

1. Narrow down: backend slow, frontend slow, or network slow?

   ```bash
   # Backend timing of the data endpoints the dashboard uses
   curl -w "@/etc/ec/curl-format.txt" -o /dev/null -sS \
     -H "Authorization: Bearer $TOKEN" \
     "https://app.example.com/api/v1/dashboard"
   ```

   (`curl-format.txt` prints `time_namelookup, time_connect, time_starttransfer, time_total`.)

2. If `time_starttransfer` is the dominant component, the backend is slow → see `high-cpu-on-backend.md` and `database-connection-pool-exhausted.md`.

3. If `time_total - time_starttransfer` is dominant, payload is too large → see if a recent change inflated the dashboard JSON.

4. If frontend is slow:

   ```bash
   # Bundle size — anything new in the last week?
   cd frontend && npm run bundle-report
   ```

5. As a stop-gap, enable the dashboard payload cache:

   ```bash
   # /etc/ec/backend.env
   DASHBOARD_CACHE_TTL_SECONDS=30
   ```

## Root cause investigation

Most useful PromQL:

```promql
# p95 latency for the dashboard endpoint
histogram_quantile(0.95,
  sum by (le) (
    rate(ec_http_request_duration_seconds_bucket{path="/api/v1/dashboard"}[5m])
  )
)

# Heaviest queries during dashboard load
topk(5,
  rate(ec_db_query_duration_seconds_sum{operation=~"dashboard.*"}[5m])
)
```

Sentry performance traces — filter `transaction:GET /api/v1/dashboard` and inspect the slowest spans.

Common causes:

- New widget added without index on its driving query.
- N+1 query for "open invoices per tenant" — should be aggregated server-side.
- Missing `defer()` on heavy columns (JSON blobs).
- Frontend regression — a third-party script added to `index.html`.
- CDN cache miss — origin shielding misconfigured.

## Permanent fix

- Add index, denormalise, or aggregate at the database for slow dashboards.
- Apply `defer()` to columns > 4 KB that the dashboard doesn't render.
- Set `DASHBOARD_CACHE_TTL_SECONDS=15` as a permanent setting if data freshness allows.
- Lighthouse budget enforcement (already in `scripts/lighthouse-audit.js` — see `docs/RELEASE_PROCESS.md`).
- Add `web-vitals` reporting and alert on field-data p95 > 2.5 s.

## Postmortem checklist

- [ ] Identify the request that became slow and the change that introduced it.
- [ ] Confirm SLO restored.
- [ ] Did frontend monitoring detect the regression before customers?
