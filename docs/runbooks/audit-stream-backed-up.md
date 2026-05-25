# Runbook — Audit stream backed up

## Symptoms

- Alert `AuditStreamQueueDepth` firing: queue depth > 10 000 events.
- `ec_audit_events_pending` gauge climbing.
- Customer SIEM (Splunk / Datadog / Sumo) shows last-event timestamp >15 minutes behind real-time.
- Log: `audit_streamer: failed to deliver batch — retry queued`.

## Severity

- **Sev 2** — events are buffered and not lost. Customers monitor compliance in real time, so SLA is "events delivered within 5 minutes."
- **Sev 1** if the on-disk buffer is filling and we're at risk of dropping events.

## Immediate mitigation

1. Identify which sink is failing:

   ```promql
   topk(5,
     sum by (sink, tenant_id) (rate(ec_audit_delivery_failures_total[15m]))
   )
   ```

2. Inspect the most recent failure:

   ```bash
   curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/audit/streams/$STREAM_ID/last-error" | jq .
   ```

3. Test the destination manually (Splunk HEC example):

   ```bash
   curl -k "https://splunk.customer.com:8088/services/collector" \
     -H "Authorization: Splunk $HEC_TOKEN" \
     -d '{"event": "ec-ping"}'
   ```

4. If the destination is up but slow, raise the per-stream concurrency temporarily:

   ```bash
   curl -X PATCH -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/audit/streams/$STREAM_ID" \
     -d '{"concurrency": 8}'
   ```

5. If the destination is permanently down and the buffer is filling, pause delivery to that stream (events continue to be written to the durable buffer; resume picks up from the offset):

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/audit/streams/$STREAM_ID/pause"
   ```

## Root cause investigation

- **Sink credentials rotated** → customer change without notice. Send template email to the tenant admin.
- **Sink rate-limiting us** (Splunk HEC, Datadog) — back off and reduce batch size.
- **Sink endpoint changed** — customer migrated to a new hostname; metadata isn't updated.
- **Our event volume spiked** — investigate the source. A bulk importer or a noisy integration may be generating excessive audit events.

Top tenants by event rate:

```promql
topk(10,
  sum by (tenant_id) (rate(ec_audit_events_total[5m]))
)
```

## Permanent fix

- Implement adaptive batch sizing based on observed sink success rate.
- Add `SinkLastError` to the tenant admin UI so customers can self-diagnose.
- Document expected event volumes in `docs/INTEGRATIONS.md` for sizing.
- Move from in-process buffer to a durable on-disk queue (Wave 4 design) for tenants > 1 M events/day.

## Postmortem checklist

- [ ] Were any events dropped? (Cross-check `ec_audit_events_dropped_total`.)
- [ ] Was the customer notified within 15 minutes of detection?
- [ ] Did the resume from offset work cleanly?
- [ ] Is the buffer sized appropriately for the tenant's volume?
