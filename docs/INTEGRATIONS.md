# Third-party integrations

EnterpriseCore ships with a small connector framework + seven first-class
integrations: **Slack**, **Google Workspace**, **Zapier**,
**Microsoft Teams**, **Microsoft 365**, **DocuSign**, and **GitHub**.
Together they cover the most-requested mid-market wiring scenarios:

* Real-time notifications into the team's chat (Slack, Microsoft Teams)
* Calendar + spreadsheet sync (Google Workspace, Microsoft 365)
* Anything-to-anything via Zapier's 5,000+ app library
* E-signature for contracts and proposals (DocuSign)
* Developer repo connections for the AI Coding module (GitHub)

All three are tenant-scoped: a customer installing Slack only sees
Slack messages for events in their own tenant. OAuth tokens are stored
encrypted under the tenant's own Data Encryption Key (BYOK-aware via
`app/core/encryption.py`).

## Architecture

```
event_bus.publish(Event)
    ├─► outbound webhooks (Phase 8.0 — generic HTTP)
    ├─► Redis stream (when REDIS_URL set)
    └─► in-process subscribers
            ├─► integrations registry → connector.handle_event()
            └─► workflow engine → matching Workflow.execute()
```

* `app/services/integrations/base.py` — `Integration` ABC.
* `app/services/integrations/registry.py` — connector singletons +
  event-bus glue.
* `app/services/integrations/{slack,google_workspace,zapier}.py` — the
  three concrete connectors.
* `app/models/integrations.py` — `TenantIntegration` table (encrypted
  tokens + JSON config).

## Connector catalog

| Key | Category | Configurable when | Default events |
|---|---|---|---|
| `slack` | messaging | `SLACK_CLIENT_ID` + `SLACK_CLIENT_SECRET` set | `crm.deal.won`, `crm.lead.created`, `finance.invoice.paid`, `construction.risk.created`, `webchat.conversation.created` |
| `google_workspace` | calendar | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` set | `projects.task.completed`, `projects.project.created`, `construction.milestone.upcoming` |
| `zapier` | automation | always | `*` (every event the customer subscribes to) |
| `microsoft_teams` | messaging | `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` set | `crm.deal.won`, `crm.lead.created`, `finance.invoice.paid`, `construction.risk.created` |
| `microsoft_365` | calendar | `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` set | `projects.project.created`, `construction.milestone.upcoming`, `marketing.upload` |
| `docusign` | esignature | `DOCUSIGN_CLIENT_ID` + `DOCUSIGN_CLIENT_SECRET` set | `crm.proposal.sent`, `crm.contract.created`, `construction.contract.created` |
| `github` | developer | `GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` set | `coding.repo.connected` |

The Google Workspace connector additionally requires
`requirements-integrations.txt` (`google-auth` + `google-api-python-client`)
for the actual API calls to land — without them the OAuth dance still
works but event handlers log a warning and skip the API call.

## Endpoints

All endpoints under `/api/v1/integrations`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/catalog` | user | List available connectors + whether they're configurable on this deployment. |
| GET | `/installed` | user | The tenant's currently-installed connectors. |
| POST | `/{key}/install` | admin/manager | Start install. OAuth connectors return an authorization URL; Zapier returns the static API key (shown once). |
| GET | `/oauth/callback?key=...&code=...&state=...` | public (state-verified) | Third-party redirect target. |
| POST | `/{key}/uninstall` | admin | Revoke + delete the row. |
| PATCH | `/{key}/config` | admin/manager | Update the tenant config bag (default channel, event filter, Zapier outbound URL, etc.). |
| POST | `/{key}/test` | admin/manager | Fire a synthetic event to confirm wiring. |
| POST | `/zapier/inbound?key=...` | public (API-key verified) | Zapier-built Zaps call this with `{action, data}` to perform an action on our side. |

## Slack install flow

1. Admin clicks **Connect Slack** in the UI.
2. Frontend calls `POST /integrations/slack/install`; gets back an
   `install_url` pointing at `slack.com/oauth/v2/authorize`.
3. User authorizes in the Slack UI; Slack redirects to
   `GET /integrations/oauth/callback?key=slack&code=...&state=slack:<tenant_id>`.
4. We exchange the code via `slack.com/api/oauth.v2.access` and store the
   bot token + workspace metadata.
5. The connector is now subscribed to its default events via the
   in-process event bus. Posts land in the workspace's incoming-webhook
   channel (or a channel set via `PATCH /integrations/slack/config`).

## Google Workspace install flow

Mirrors Slack, but the scopes requested are `calendar.events` +
`drive.file`. The connector stores both `access_token` and
`refresh_token` (Google uses short-lived access tokens). Refresh-flow
plumbing lives in `_google_service`; missing-library guards keep the
event bus running even when the SDK isn't installed.

## Zapier — outbound + inbound

Zapier has no OAuth flow:

1. Admin clicks **Install Zapier**; we generate a `zk_<48-char-secret>`
   API key and show it once.
2. Admin pastes the key into Zapier's webhook trigger configuration so
   their Zaps can call us.
3. Admin pastes a Zapier "Catch Hook" URL into our config (via
   `PATCH /integrations/zapier/config` with
   `{"config": {"outbound_webhook_url": "https://hooks.zapier.com/..."}}`).
   From then on every matching event is POSTed to that URL.

Inbound actions (called by a Zap):

* `create_crm_lead` — `{name, email, company, source}` → new Contact +
  Lead, fires `crm.lead.created`.
* `create_calendar_event` — `{title, when, description}` → fires
  `projects.project.created` so the Google Workspace connector picks it
  up.
* `add_note` — `{title, body}` → creates an in-app Notification.

## Security notes

* OAuth tokens are encrypted under the tenant DEK — the global
  EncryptionKey can rotate without touching them.
* OAuth state tokens embed the tenant id and are verified on callback.
* Zapier API keys are stored encrypted; the inbound endpoint scans each
  Zapier row and attempts to decrypt — only the right tenant's DEK
  yields the matching plaintext.
* Slack `chat.postMessage` calls use the **bot token** (not the
  workspace incoming-webhook URL) so message attribution stays clean.

## Microsoft Teams + Microsoft 365 — shared Azure AD app

Both Microsoft connectors share one Azure AD app registration. Set:

* `MICROSOFT_CLIENT_ID` — application (client) id of the Azure AD app
* `MICROSOFT_CLIENT_SECRET` — client secret
* `MICROSOFT_TENANT_ID` — either a directory GUID (single-tenant) or
  `common` (multi-tenant, the default)
* `MICROSOFT_REDIRECT_URI` — the public `/api/v1/integrations/oauth/callback?key=microsoft_teams` URL

The Teams connector requests `ChannelMessage.Send`,
`Team.ReadBasic.All`, `offline_access`. The 365 connector requests
`Calendars.ReadWrite`, `Mail.Send`, `Files.ReadWrite`, `offline_access`.
After install, the tenant configures `team_id` + `channel_id` (Teams)
and `default_calendar_id` + `sharepoint_site_id` (365) via
`PATCH /integrations/{key}/config`.

Calendar sync is write-only in v1: outbound project + milestone events
land in the user's calendar but the suite does not yet read MS Calendar
back into a merged view. Bidirectional sync is on the v2 roadmap.

## DocuSign — e-signature for contracts

Set `DOCUSIGN_CLIENT_ID`, `DOCUSIGN_CLIENT_SECRET`, and
`DOCUSIGN_BASE_URL` (`https://account-d.docusign.com` for sandbox,
`https://account.docusign.com` for production). Scopes: `signature`,
`extended`. On callback we record the DocuSign `account_id` and the
returned `base_uri` so subsequent envelope calls hit the right API host.

When the connector receives one of its default events
(`crm.proposal.sent`, `crm.contract.created`,
`construction.contract.created`) it POSTs a `sent`-status envelope to
the DocuSign Envelopes API with the recipient drawn from
`event.payload.recipient_email` (falling back to the tenant's
`default_sender_email`). `auto_send` may be toggled off in config to
queue envelopes for manual review instead.

Inbound webhook: DocuSign Connect notifications POST to
`POST /api/v1/integrations/docusign/inbound?tenant_id=<tenant_id>` with
the simplified JSON payload. Completed envelopes emit
`docusign.envelope.completed` on the local event bus — workflows can
subscribe to mark the local document signed or write a CRM
CommunicationEntry. HMAC signature verification of the inbound payload
is deferred to v2.

## GitHub — repo connections for the AI Coding module

Set `GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET`. Scopes: `repo`,
`read:user`, `read:org`. On `coding.repo.connected` events the connector
hits `GET /repos/{owner}/{repo}` and appends repo metadata
(default branch, clone URL, private/public) to the tenant's
`connected_repos` config list.

Inbound webhook:
`POST /api/v1/integrations/github/inbound?tenant_id=<tenant_id>`
accepts GitHub webhook deliveries. For `issues` events it emits
`github.issue.opened`, `github.issue.closed`, or
`github.issue.reopened` on the local bus. Webhook secret verification
is deferred to v2 — for v1 the tenant id query parameter plus the
"integration must be installed" check are the only access controls.

## Graceful degradation

For every OAuth-based connector (Slack, Google, Microsoft Teams,
Microsoft 365, DocuSign, GitHub), unsetting the relevant
`<PROVIDER>_CLIENT_ID` env var causes:

* `is_configurable()` to return `False` (catalog shows "needs config")
* `install_url()` to return a documentation link instead of raising
  (so the UI can still render a button pointing to the provider's
  developer docs)
* `handle_oauth_callback()` to raise `ValidationFailed` with a clear
  message
* event handlers to silently skip outbound API calls and log a warning
