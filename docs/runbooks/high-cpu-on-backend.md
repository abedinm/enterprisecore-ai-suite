# Runbook — High CPU on backend

## Symptoms

- Alert `BackendHighCPU` firing — `avg(rate(process_cpu_seconds_total[5m])) by (instance) > 0.85`.
- `ec_http_request_duration_seconds` p95 climbing above 1s.
- Customer reports of slow UI.
- `uvicorn` worker logs show `WARNING: worker took longer than 30s`.

## Severity

- **Sev 2** if one host is hot but the load balancer is spreading traffic and overall p95 < 2s.
- **Sev 1** if every backend host is hot OR a single host is the only one and the app is unresponsive.

## Immediate mitigation

1. Check whether autoscaling has kicked in:

   ```bash
   kubectl get hpa ec-backend
   aws ecs describe-services --cluster ec --services ec-backend | jq '.services[0].desiredCount'
   ```

2. If autoscaling is disabled or rate-limited, scale up manually:

   ```bash
   kubectl scale deploy ec-backend --replicas=$((CURRENT*2))
   ```

3. If the spike is from a single endpoint, rate-limit it:

   ```bash
   # Add a temporary rule in the gateway / nginx
   limit_req_zone $binary_remote_addr zone=hot:10m rate=10r/s;
   ```

4. If the spike is from a single tenant, throttle them:

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/tenants/$TENANT_ID/throttle" \
     -d '{"qps": 5}'
   ```

## Root cause investigation

Identify the hot route:

```promql
topk(10,
  sum by (path, method) (
    rate(ec_http_request_duration_seconds_sum[5m])
    / rate(ec_http_request_duration_seconds_count[5m])
  )
)
```

Identify slow DB queries:

```promql
topk(10,
  sum by (operation) (
    rate(ec_db_query_duration_seconds_sum[5m])
    / rate(ec_db_query_duration_seconds_count[5m])
  )
)
```

Live profile a worker (read-only — does not stop the process):

```bash
pip install py-spy
sudo py-spy top --pid $(pgrep -f "uvicorn.*ec_backend" | head -1)
```

Dump a flame graph:

```bash
sudo py-spy record -o /tmp/flame.svg --pid $(pgrep -f uvicorn | head -1) --duration 30
```

Check for:

- A recently deployed change that introduced a regression (`git log --since='2 hours ago'`).
- A long-running ad-hoc admin job competing for CPU (`ps auxf | sort -k 3 -r | head`).
- A traffic spike from one tenant — query `ec_http_requests_total` by `tenant` label (custom label, if enabled).

## Permanent fix

- Optimise the hot endpoint (caching, N+1 queries, denormalisation).
- Add an index — see `database-connection-pool-exhausted.md` for the procedure.
- Set sensible autoscaling thresholds (target CPU 60%, max replicas ≥ 2 x peak).
- Apply per-tenant rate limits (see `app/core/rate_limit.py`) so a single noisy tenant cannot saturate.

## Postmortem checklist

- [ ] Was the autoscaler appropriately configured?
- [ ] Was there a recent code change that should be reverted or rolled forward?
- [ ] Did p95 / p99 alerts fire BEFORE CPU did? If not, tune SLO alerts.
- [ ] Capture the flame graph in the incident document.
