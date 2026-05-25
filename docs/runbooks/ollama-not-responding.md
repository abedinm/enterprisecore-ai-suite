# Runbook — Ollama not responding

## Symptoms

- AI chat features return 503 with body `{"error": "ai_provider_unavailable"}`.
- `ec_ai_calls_total{provider="ollama", success="false"}` climbing.
- Health check `GET /api/v1/ai/healthz?provider=ollama` returning 503.
- Logs: `ollama.client.timeout — POST /api/chat exceeded 30s`.

## Severity

- **Sev 2** if other providers are configured and the system fell back gracefully.
- **Sev 1** if Ollama is the only configured provider and AI features are down.

## Immediate mitigation

1. Confirm Ollama is reachable from the backend:

   ```bash
   curl -fsS "http://$OLLAMA_HOST:11434/api/version"
   curl -fsS "http://$OLLAMA_HOST:11434/api/tags" | jq .models[].name
   ```

2. If unreachable, check the host:

   ```bash
   ssh ec-ollama-1
   sudo systemctl status ollama
   sudo journalctl -u ollama -n 200
   nvidia-smi   # if GPU-backed
   ```

3. Restart:

   ```bash
   sudo systemctl restart ollama
   sudo journalctl -u ollama -f
   ```

4. If GPU memory is exhausted (`nvidia-smi` shows OOM), evict unused models:

   ```bash
   ollama list
   ollama rm <unused-model>
   ```

5. Failover to a cloud provider, if configured:

   ```bash
   curl -X PATCH -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/ai/provider-priority" \
     -d '["openai","anthropic","ollama"]'
   ```

## Root cause investigation

- **GPU OOM** — model larger than VRAM. Check `nvidia-smi --query-gpu=memory.used,memory.total --format=csv`.
- **Disk full** — Ollama writes scratch space. See `disk-space-warning.md`.
- **CPU saturation** — Ollama is CPU-bound on small machines without a GPU. Check `top`.
- **Model not downloaded** — request for a model name that isn't installed. Logs show `error: model "xyz" not found, try pulling it first`.
- **Concurrent request limit** — Ollama serializes requests per model. Bursts produce queueing.

Quick check of recent AI calls per model:

```promql
sum by (model, success) (rate(ec_ai_calls_total{provider="ollama"}[5m]))
```

## Permanent fix

- Pre-pull required models in the Ollama container's startup script.
- Right-size GPU / CPU for expected concurrency. Reference numbers in `docs/PERFORMANCE.md`.
- Configure multiple Ollama hosts behind a round-robin / least-loaded LB.
- Set per-model `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_LOADED_MODELS`.
- Enable backend-side queueing with the jobs worker so chat requests degrade gracefully under load.

## Postmortem checklist

- [ ] Did the failover to cloud provider work as expected?
- [ ] Were customers charged for fallback (cloud) usage? Comp where appropriate.
- [ ] Are GPU-OOM alerts in place?
- [ ] Document the model-vs-VRAM matrix in `docs/AI_CODING.md` if missing.
