#!/usr/bin/env bash
# tenant_import.sh — restore a single tenant from a previous tenant_export.
#
# Used for:
#   - Restoring a tenant whose data was deleted by mistake.
#   - Migrating a tenant from one EnterpriseCore deployment to another.
#   - Cloning a tenant into a sandbox environment.
#
# The import is idempotent: re-running with the same bundle is a no-op (matched
# by export_bundle_id).
#
# Required env:
#   EC_API_BASE        — destination API base
#   EC_ADMIN_TOKEN     — admin bearer token with gdpr:import scope
#   BUNDLE_PATH        — path to the tenant export zip (or s3:// uri)
#
# Optional env:
#   TARGET_TENANT_ID   — tenant to import INTO; default = the one named in the bundle
#   GPG_DECRYPT        — set to 1 if the bundle is .gpg-encrypted
#   DRY_RUN            — set to 1 to validate without writing
#   WAIT_SECS          — long-poll timeout; default 1800
#   POLL_INTERVAL      — seconds between polls; default 15

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

: "${EC_API_BASE:?}"; : "${EC_ADMIN_TOKEN:?}"; : "${BUNDLE_PATH:?}"

GPG_DECRYPT="${GPG_DECRYPT:-0}"
DRY_RUN="${DRY_RUN:-0}"
WAIT_SECS="${WAIT_SECS:-1800}"
POLL_INTERVAL="${POLL_INTERVAL:-15}"

AUTH=(-H "Authorization: Bearer $EC_ADMIN_TOKEN")

# --- fetch bundle ------------------------------------------------------------

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

LOCAL_BUNDLE="${WORK_DIR}/bundle.zip"

if [[ "$BUNDLE_PATH" == s3://* ]]; then
  log "Downloading $BUNDLE_PATH"
  aws s3 cp "$BUNDLE_PATH" "$LOCAL_BUNDLE" || die "s3 download failed"
else
  [[ -f "$BUNDLE_PATH" ]] || die "bundle not found: $BUNDLE_PATH"
  cp "$BUNDLE_PATH" "$LOCAL_BUNDLE"
fi

if [[ "$GPG_DECRYPT" = "1" ]]; then
  command -v gpg >/dev/null 2>&1 || die "gpg required"
  log "Decrypting bundle"
  gpg --batch --yes --decrypt --output "${LOCAL_BUNDLE%.zip}.dec" "$LOCAL_BUNDLE"
  mv "${LOCAL_BUNDLE%.zip}.dec" "$LOCAL_BUNDLE"
fi

# --- upload to import endpoint ----------------------------------------------

UPLOAD_ARGS=(-F "bundle=@${LOCAL_BUNDLE}")
[[ -n "${TARGET_TENANT_ID:-}" ]] && UPLOAD_ARGS+=(-F "target_tenant_id=${TARGET_TENANT_ID}")
[[ "$DRY_RUN" = "1" ]] && UPLOAD_ARGS+=(-F "dry_run=true")

log "Submitting bundle to ${EC_API_BASE%/}/api/v1/admin/tenants/import"
JOB_JSON="$(curl -fsS -X POST "${AUTH[@]}" \
  "${EC_API_BASE%/}/api/v1/admin/tenants/import" \
  "${UPLOAD_ARGS[@]}")" \
  || die "submission failed"

JOB_ID="$(jq -r '.job_id' <<<"$JOB_JSON")"
[[ -n "$JOB_ID" && "$JOB_ID" != "null" ]] || die "no job_id: $JOB_JSON"
log "Import job id=$JOB_ID"

# --- poll --------------------------------------------------------------------

ELAPSED=0
while (( ELAPSED < WAIT_SECS )); do
  STATUS_JSON="$(curl -fsS "${AUTH[@]}" "${EC_API_BASE%/}/api/v1/jobs/${JOB_ID}")"
  STATUS="$(jq -r '.status' <<<"$STATUS_JSON")"
  case "$STATUS" in
    succeeded)
      log "Import complete"
      jq . <<<"$STATUS_JSON"
      exit 0;;
    failed|cancelled)
      die "import failed: $(jq -r '.error' <<<"$STATUS_JSON")";;
    *)
      log "status=$STATUS elapsed=${ELAPSED}s"
      sleep "$POLL_INTERVAL"
      ELAPSED=$((ELAPSED + POLL_INTERVAL));;
  esac
done

die "import did not complete within ${WAIT_SECS}s"
