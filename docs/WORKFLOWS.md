# No-code workflow automation

EnterpriseCore's workflow engine lets tenants build **if-this-then-that**
rules without writing code. A workflow watches one event type
(optionally filtered by payload contents) and runs an ordered list of
actions when a matching event fires.

This is intentionally *small*: the trigger filter and template languages
are deliberately constrained so the feature is safe to expose in a
webform. Customers who need raw scripting use the outbound webhook
subscription mechanism (Phase 8.0) instead.

## Concepts

* **Workflow** — one rule. Owned by a tenant; max 100 active per
  tenant; max 10 actions per workflow.
* **WorkflowRun** — one execution of a workflow against one event. Kept
  forever so the admin can audit *why* a particular Slack message did
  or didn't go out.
* **Trigger** — `trigger_event_type` (a key from `EVENT_TYPES` or a
  wildcard pattern like `crm.*`) + `trigger_filter` (a flat dict of
  payload conditions).
* **Actions** — ordered list. Each action has a `type` (e.g.
  `send_slack_message`) and a `config` dict. String values inside the
  config are Jinja2-templated with the event payload as the context.

## Trigger filter language

A flat dict of `{"dotted.payload.path": comparison_spec}`. Every clause
must pass for the workflow to run.

Supported comparison specs:

| Spec | Meaning |
|---|---|
| `"value"` | Exact equality (string or numeric). |
| `"> 1000"` | Greater than (numeric). |
| `"< 1000"` | Less than. |
| `">= 1000"` / `"<= 1000"` | Range comparisons. |
| `"!= value"` | Not equal. |
| `"in:a,b,c"` | Membership test (string-split on commas). |

Example: only fire on big closed-won deals from priority customers:

```json
{
  "trigger_event_type": "crm.deal.won",
  "trigger_filter": {
    "amount": "> 50000",
    "customer.tier": "in:enterprise,vip"
  }
}
```

## Action catalog

Retrieve at runtime via `GET /api/v1/workflows/action-types`.

| Type | What it does |
|---|---|
| `send_slack_message` | Uses the tenant's Slack integration to post a templated message. |
| `send_email` | Sends an email via the configured `EMAIL_PROVIDER`. |
| `create_calendar_event` | Republishes a `projects.project.created` event so the Google Workspace connector handles the Calendar API call. |
| `create_crm_followup` | Creates a `crm.FollowUp` row. |
| `create_task` | Creates a `projects.Task` row. |
| `post_webhook` | POSTs a JSON body to an arbitrary URL. |
| `update_field` | (reserved) Patches a field on the triggering record. |
| `notify_user` | Creates an in-app `Notification` row. |

## Templating

String values inside `config` are rendered via a sandboxed Jinja2
environment. The context is:

```jinja2
{{ payload.* }}    # the event's payload dict
{{ event.type }}   # event type
{{ event.id }}     # event id
```

Example action config:

```json
{
  "type": "send_slack_message",
  "config": {
    "channel": "#sales-wins",
    "template": "New deal: {{payload.name}} for ${{payload.amount}}"
  }
}
```

The sandbox blocks dunders and imports — workflow authors can't escape
to the host environment from a template.

## Endpoints

All under `/api/v1/workflows`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | user | List the tenant's workflows. |
| POST | `/` | admin/manager | Create a workflow. Validates event-type and action-type catalogs. |
| GET | `/action-types` | user | The action catalog the UI renders forms from. |
| GET | `/{id}` | user | Detail. |
| PATCH | `/{id}` | admin/manager | Update name / trigger / actions / active flag. |
| DELETE | `/{id}` | admin | Delete. |
| POST | `/{id}/test` | admin/manager | Fire a synthetic event matching the trigger so the customer sees the actions run end-to-end. |
| GET | `/{id}/runs?limit=50` | user | Recent execution history. |

## Execution model

* The engine subscribes to every event on the bus via
  `services/workflow_engine.register_subscribers()`.
* For each event with a tenant id, it loads all active workflows in
  that tenant, evaluates triggers, and runs surviving workflows
  sequentially.
* Action failures DO NOT stop the workflow — the partial run records
  every action's result so the admin can see exactly which step broke.
* The whole engine runs inside the publishing call site. For
  high-throughput tenants we recommend setting `REDIS_URL` so the
  Redis-backed event-bus worker absorbs the dispatch latency.

## Caps

| Limit | Why |
|---|---|
| 100 active workflows per tenant | Keeps the per-event scan cheap. |
| 10 actions per workflow | Prevents accidental fan-out storms. |
| 10s HTTP timeout per outbound action | Hard cap on action duration. |

## Testing

`tests/test_workflows.py` covers:

1. Create + list + run end-to-end (action fires, run row written).
2. Trigger filter excludes non-matching events.
3. Template rendering substitutes payload values.
4. Action failure marks the run `partial` and bumps `failures_count`.
5. Cross-tenant: tenant A's workflow ignores tenant B's events.
6. Trigger event-type validation rejects garbage strings.
7. The action-types endpoint surfaces the full catalog.
