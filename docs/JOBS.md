# Background Jobs

EnterpriseCore ships with an RQ-backed background job system that moves
heavy work (AI calls, knowledge ingest, webhook delivery, GDPR exports,
large imports, workflow execution, audit-log streaming) off the HTTP
request path. The same call site works in two modes:

| Mode  | Trigger                | Behaviour                                                |
| ----- | ---------------------- | -------------------------------------------------------- |
| Async | `REDIS_URL` is set     | Pushed onto an RQ queue; a separate worker process runs it. |
| Sync  | `REDIS_URL` not set    | Runs inline on the request thread; same observability rows are written. |

The sync fallback exists so the test suite, single-binary self-host
installs, and `pip install && uvicorn` developers never need Redis to
have a working app.

## Call site

```python
from app.services.jobs import enqueue_or_run
from app.services.jobs_tasks import run_importer_commit

handle = enqueue_or_run(run_importer_commit, import_job_id)
# handle.job_id  -> id of the row in the `jobs` table
# handle.mode    -> "sync" or "redis"
# handle.status  -> "queued" | "running" | "completed" | "failed"
```

Two rules every callable must follow:

1. **Don't take a `Session` argument.** Open `SessionLocal()` inside the
   function — sessions can't be pickled onto the queue.
2. **Take a row id, not a row.** Re-fetch inside the function so retries
   land on fresh state.

The existing wrappers live in `app/services/jobs_tasks.py`:

- `process_knowledge_document(doc_id)` — chunk + embed
- `run_importer_commit(import_job_id)` — large CSV / SaaS import
- `dispatch_webhook_event(payload)` — outbound webhook fan-out
- `flush_audit_streams()` — push audit log to SIEMs
- `run_gdpr_export(export_job_id, storage_dir)` — materialise data bundle
- `execute_workflow_for_event(workflow_id, payload)` — one workflow run
- `run_ai_completion(provider, model, prompt, ...)` — provider AI call

## Tenant safety

`enqueue_or_run` captures the current tenant id at enqueue time and
re-establishes it on the worker side via `tenant_scope(...)`. The ORM
auto-filter then behaves identically to an inbound HTTP request.

Workers **never leak tenant context across jobs**: the `tenant_scope`
context manager is opened and exited per-job. Two concurrent jobs for
different tenants see only their own rows.

## Worker

```bash
REDIS_URL=redis://localhost:6379/0 python scripts/run_worker.py
```

Listens on `high` → `default` → `low` queues in priority order. Honours
`LOG_FORMAT=json` for structured logs and `SENTRY_DSN` for unhandled
exception reporting. SIGTERM/SIGINT trigger a clean shutdown — the
worker finishes the current job, then exits.

## Admin observability

All admin/manager-gated, tenant-scoped:

| Endpoint                                | What                                       |
| --------------------------------------- | ------------------------------------------ |
| `GET /api/v1/jobs`                      | Recent jobs, filter `status`, `function_name` |
| `GET /api/v1/jobs/{id}`                 | Job detail + attempt history               |
| `GET /api/v1/jobs/stats`                | Counters for the dashboard tile            |
| `POST /api/v1/jobs/{id}/cancel`         | Best-effort cancel (admin-only)            |
| `POST /api/v1/jobs/{id}/retry`          | Re-enqueue with original args (admin-only) |

## Data model

Two new tables (migration `0022_jobs`):

- `jobs` — one row per `enqueue_or_run` call; tracks lifecycle, last error,
  result excerpt, RQ job id. Indexed on `(tenant_id, status, created_at)`.
- `job_attempts` — one row per execution attempt (each retry appends),
  with start/finish timestamps, duration, and error message.

Both tables carry `tenant_id` and are subject to the auto-filter.

## Testing

`tests/test_jobs.py` covers sync mode behaviour, mocked Redis mode, retry
+ cancel state transitions, and cross-tenant isolation. The Redis-mode
tests install a `MagicMock` queue via `jobs_svc.set_queue_override(...)`
so no real Redis is needed in CI.
