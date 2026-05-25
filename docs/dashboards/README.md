# Grafana dashboards

Importable Grafana dashboards for EnterpriseCore. All dashboards target Grafana 11+ and a Prometheus datasource scraping the application's `/metrics` endpoint.

---

## Dashboards

| File | UID | Description |
|---|---|---|
| `enterprisecore-overview.json` | `ec-overview` | Main dashboard: HTTP request rate, latency, error rate, in-flight, DB, AI, web chat, build info |
| `enterprisecore-ai.json` | `ec-ai` | AI calls, spend, latency, success rate, top models, breakdown by provider/feature |
| `enterprisecore-billing.json` | `ec-billing` | Subscriptions, MRR, trials, churn, Stripe webhook health, revenue |
| `enterprisecore-tenants.json` | `ec-tenants` | Per-tenant usage: top 20 by request rate / AI cost / storage; error rate by tenant |
| `enterprisecore-construction.json` | `ec-construction` | Construction-PM specifics: active projects, risks by severity, overdue milestones, RFIs, daily logs |

Each dashboard:
- Default time range: last 6h (overview / AI / tenants) or last 30d (billing / construction).
- Refresh: 30s (operational) or 5m (reporting).
- Uses `ec_*` metric names from `backend/app/core/metrics.py`.
- Has a `datasource` template variable so the same JSON works in any environment.

---

## Importing

### Via the Grafana UI

1. Open Grafana → **Dashboards → New → Import**.
2. Upload the JSON file OR paste its contents.
3. Pick the Prometheus datasource when prompted.
4. Save. The UID is preserved so subsequent re-imports update in place.

### Via provisioning

For repeatable deploys, place the dashboards on disk and configure a provisioning file.

`/etc/grafana/provisioning/dashboards/ec.yaml`:

```yaml
apiVersion: 1
providers:
  - name: enterprisecore
    orgId: 1
    folder: EnterpriseCore
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards/enterprisecore
```

Copy the five JSON files into `/var/lib/grafana/dashboards/enterprisecore/` and restart Grafana.

### Via the HTTP API

```bash
for f in docs/dashboards/*.json; do
  jq '{dashboard: ., overwrite: true, folderUid: "enterprisecore"}' "$f" \
    | curl -fsS -X POST -H "Authorization: Bearer $GRAFANA_API_KEY" \
      -H "Content-Type: application/json" \
      --data-binary @- \
      "https://grafana.example.com/api/dashboards/db"
done
```

---

## Metrics referenced

All `ec_*` metrics exposed by the backend `/metrics` endpoint (see `backend/app/core/metrics.py`):

- `ec_http_requests_total{method, path, status}`
- `ec_http_request_duration_seconds_bucket{method, path, le}`
- `ec_http_in_flight_requests`
- `ec_db_query_duration_seconds_bucket{operation, le}`
- `ec_ai_calls_total{provider, model, feature, success}`
- `ec_ai_tokens_in_total{provider, model}`
- `ec_ai_tokens_out_total{provider, model}`
- `ec_ai_cost_usd_total{provider, model}`
- `ec_ai_latency_seconds_bucket{provider, model, le}`
- `ec_webchat_messages_total{bot_id, role}`
- `ec_build_info{version, commit, env}`

Some dashboards reference metrics that may be added in later waves (e.g., `ec_subscription_count`, `ec_tenant_request_rate`, `ec_construction_*`). When those are not yet emitted, the relevant panels render as "No data" — the dashboards themselves remain valid.

---

## Conventions

- **Cardinality caution.** Tenant-scoped metrics live in dashboards filtered by a `tenant` template variable; do not blow up overview dashboards with high-cardinality breakdowns.
- **Deploy annotation.** The overview dashboard annotates deploys via `changes(ec_build_info[1m]) > 0`. The tag keys carry version / commit / env so hover shows the deploy.
- **Color thresholds.** Where used, follow:
  - Green / yellow / red on latency: 0–1s green, 1–2s yellow, 2s+ red.
  - Green / yellow / red on success rate: 0–95% red, 95–99% yellow, 99%+ green.
- **Templating.** Every dashboard has a `datasource` variable so the JSON is portable.
