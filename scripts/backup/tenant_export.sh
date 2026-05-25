#!/usr/bin/env bash
# tenant_export.sh — export a single tenant's data via the GDPR export endpoint.
# Useful for: data-subject access requests, ad-hoc tenant migration, support tickets,
# and the off-board flow when a customer terminates.
#
# Required env:
#   EC_API_BASE        — e.g. https://app.example.com
#   EC_ADMIN_TOKEN     — admin bearer token with gdpr:export scope
#   TENANT_ID          — UUID of the tenant to export
#
# Optional env:
#   EXPORT_FORMAT      — json (default) or csv
#   OUT_DIR            — destination directory; default ./exports
#   GPG_RECIPIENT      — encrypt the bundle for this recipient
#   UPLOAD_S3_URI      — if set, upload encrypted bundle here (e.g. s3://bucket/prefix/)
#   WAIT_SECS          — long-poll timeout; default 600
#   POLL_INTERVAL      — seconds between polls; default 10

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

: "${EC_API_BASE:?}"; : "${EC_ADMIN_TOKEN:?}"; : "${TENANT_ID:?}"

EXPORT_FORMAT="${EXPORT_FORMAT:-json}"
OUT_DIR="${OUT_DIR:-./exports}"
WAIT_SECS="${WAIT_SECS:-600}"
POLL_INTERVAL="${POLL_INTERVAL:-10}"
mkdir -p "$OUT_DIR"

AUTH=(-H "Authorization: Bearer $EC_ADMIN_TOKEN")
JSON=(-H "Content-Type: application/json")

# --- kick off the export job -------------------------------------------------

log "Requesting export for tenant $TENANT_ID format=$EXPORT_FORMAT"
JOB_JSON="$(curl -fsS -X POST "${AUTH[@]}" "${JSON[@]}" \
  "${EC_API_BASE%/}/api/v1/admin/tenants/${TENANT_ID}/export" \
  -d "{\"format\":\"${EXPORT_FORMAT}\"}")" \
  || die "export request failed"

JOB_ID="$(jq -r '.job_id' <<<"$JOB_JSON")"
[[ -n "$JOB_ID" && "$JOB_ID" != "null" ]] || die "no job_id in response: $JOB_JSON"
log "Export job id=$JOB_ID"

# --- poll until ready --------------------------------------------------------

ELAPSED=0
DOWNLOAD_URL=""
while (( ELAPSED < WAIT_SECS )); do
  STATUS_JSON="$(curl -fsS "${AUTH[@]}" "${EC_API_BASE%/}/api/v1/jobs/${JOB_ID}")"
  STATUS="$(jq -r '.status' <<<"$STATUS_JSON")"
  case "$STATUS" in
    succeeded)
      DOWNLOAD_URL="$(jq -r '.result.download_url' <<<"$STATUS_JSON")"
      break;;
    failed|cancelled)
      die "export job ended status=$STATUS detail=$(jq -r '.error // empty' <<<"$STATUS_JSON")";;
    *)
      log "status=$STATUS elapsed=${ELAPSED}s"
      sleep "$POLL_INTERVAL"
      ELAPSED=$((ELAPSED + POLL_INTERVAL));;
  esac
done

[[ -n "$DOWNLOAD_URL" ]] || die "export did not complete within ${WAIT_SECS}s"

# --- download ---------------------------------------------------------------

OUT="${OUT_DIR}/tenant-${TENANT_ID}-$(date -u +%Y-%m-%dT%H-%M-%SZ).${EXPORT_FORMAT}.zip"
log "Downloading bundle -> $OUT"
curl -fsS "${AUTH[@]}" "$DOWNLOAD_URL" -o "$OUT" || die "download failed"

# --- encrypt -----------------------------------------------------------------

if [[ -n "${GPG_RECIPIENT:-}" ]]; then
  command -v gpg >/dev/null 2>&1 || die "gpg required"
  gpg --batch --yes --trust-model always \
    --output "${OUT}.gpg" \
    --encrypt --recipient "$GPG_RECIPIENT" "$OUT"
  rm -f "$OUT"
  OUT="${OUT}.gpg"
  log "Encrypted -> $OUT"
fi

# --- upload ------------------------------------------------------------------

if [[ -n "${UPLOAD_S3_URI:-}" ]]; then
  DEST="${UPLOAD_S3_URI%/}/$(basename "$OUT")"
  log "Uploading -> $DEST"
  aws s3 cp "$OUT" "$DEST" --sse AES256 || die "upload failed"
fi

log "Tenant export complete -> $OUT"
