# Runbook — High memory on backend

## Symptoms

- Alert `BackendHighMemory` firing — `process_resident_memory_bytes / on (instance) machine_memory_bytes > 0.85`.
- OOMKiller events: `dmesg | grep -i oom`, or `kubectl get events | grep OOMKilled`.
- Worker restarts visible in `uvicorn` logs: `Worker (pid:X) was sent SIGKILL!`.
- p99 latency spike following a worker recycle.

## Severity

- **Sev 2** if memory is high but stable and the app is serving traffic.
- **Sev 1** if workers are being OOMKilled and request latency is degrading.

## Immediate mitigation

1. Confirm headroom on the host:

   ```bash
   free -h
   ps -eo pid,rss,cmd --sort=-rss | head
   ```

2. If a single worker is leaking, recycle it (gracefully — uvicorn drains in-flight):

   ```bash
   sudo systemctl reload ec-backend
   ```

3. If the application is misbehaving, restart with extra workers using a memory cap (cgroups / k8s `memory.limit`):

   ```bash
   kubectl set resources deploy/ec-backend --limits=memory=4Gi --requests=memory=2Gi
   ```

4. As a stop-gap, lower `WORKER_MAX_REQUESTS` to recycle workers more frequently:

   ```bash
   # in /etc/ec/backend.env
   WORKER_MAX_REQUESTS=2000
   WORKER_MAX_REQUESTS_JITTER=200
   sudo systemctl restart ec-backend
   ```

## Root cause investigation

Live snapshot:

```bash
pip install memray
sudo memray attach --pid $(pgrep -f uvicorn | head -1) -o /tmp/leak.bin
# wait ~60s
sudo memray flamegraph /tmp/leak.bin -o /tmp/leak.html
```

Common causes:

- **Caching without a cap.** Look for `lru_cache(maxsize=None)` introduced recently: `git log --since='1 week ago' -p backend/app | grep -B2 lru_cache`.
- **Unbounded query result loading.** A new endpoint returning ALL rows of a table without pagination. Search for `.all()` on large tables.
- **OpenTelemetry buffer growth** if the OTLP exporter is unreachable. Check `journalctl -u ec-backend | grep -i otlp` for export errors.
- **Workflow / importer job loading a large file into memory** instead of streaming.

## Permanent fix

- Switch any `.all()` over large tables to streaming with `yield_per()` or pagination.
- Cap LRU caches: `lru_cache(maxsize=10_000)`.
- Set `MallocArenaMax=2` to limit glibc arena bloat (Linux only).
- Add a `MemoryGrowth` alert that triggers earlier than the OOM threshold (e.g., >70% RSS growth in 1 hour).

## Postmortem checklist

- [ ] Was the leak introduced by a recent change?
- [ ] Did OOMKills cause data loss or just latency?
- [ ] Are worker resource limits configured?
- [ ] Is memray output captured in the incident document?
