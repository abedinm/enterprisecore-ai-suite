#!/usr/bin/env bash
# storage_backup.sh — rsync the application storage directory to S3 with versioning.
# Use when the EnterpriseCore deployment stores customer file uploads on a local
# volume rather than S3 directly.
#
# Required env:
#   STORAGE_DIR           — source path (e.g. /var/lib/ec/storage)
#   BACKUP_S3_BUCKET      — destination bucket (must have versioning enabled)
#   BACKUP_S3_PREFIX      — prefix (e.g. prod/storage/)
#
# Optional env:
#   BACKUP_USE_SSE        — default 1 (server-side encryption)
#   DELETE_FROM_DEST      — default 0; if 1, deletes from destination when source removed
#   SLACK_WEBHOOK_URL     — alert on failure
#   EXCLUDES              — comma-separated rsync patterns to skip; default "*.tmp,*.partial"
#
# Notes:
#   - S3 versioning is required so prior versions of a file remain recoverable.
#   - For very large storage (>1TB) consider running this nightly and using S3
#     replication for cross-region instead of a second copy here.

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; notify "failure" "$*"; exit "${2:-1}"; }
notify() {
  local status="$1"; local msg="$2"
  [[ -n "${SLACK_WEBHOOK_URL:-}" ]] || return 0
  local color=$([ "$status" = "success" ] && echo good || echo danger)
  curl -fsS -X POST -H 'Content-Type: application/json' \
    -d "$(printf '{"attachments":[{"color":"%s","text":"storage_backup %s on %s: %s"}]}' \
      "$color" "$status" "$(hostname)" "$msg")" \
    "$SLACK_WEBHOOK_URL" >/dev/null || true
}

: "${STORAGE_DIR:?STORAGE_DIR is required}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET is required}"
: "${BACKUP_S3_PREFIX:?BACKUP_S3_PREFIX is required}"
[[ -d "$STORAGE_DIR" ]] || die "STORAGE_DIR $STORAGE_DIR not found"

BACKUP_USE_SSE="${BACKUP_USE_SSE:-1}"
DELETE_FROM_DEST="${DELETE_FROM_DEST:-0}"
EXCLUDES="${EXCLUDES:-*.tmp,*.partial}"

command -v aws >/dev/null 2>&1 || die "aws cli required" 2

DEST="s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX%/}/"
SYNC_ARGS=(--storage-class STANDARD_IA)
[[ "$BACKUP_USE_SSE" = "1" ]] && SYNC_ARGS+=(--sse AES256)
[[ "$DELETE_FROM_DEST" = "1" ]] && SYNC_ARGS+=(--delete)

IFS=',' read -ra EXARR <<<"$EXCLUDES"
for pat in "${EXARR[@]}"; do
  SYNC_ARGS+=(--exclude "$pat")
done

log "Syncing $STORAGE_DIR -> $DEST"
START_TS=$(date +%s)

aws s3 sync "$STORAGE_DIR" "$DEST" "${SYNC_ARGS[@]}" \
  || die "aws s3 sync failed"

DURATION=$(( $(date +%s) - START_TS ))
SIZE_BYTES="$(du -sb "$STORAGE_DIR" | awk '{print $1}')"

log "Sync complete duration=${DURATION}s source_bytes=${SIZE_BYTES}"
notify "success" "${STORAGE_DIR} -> ${DEST} duration=${DURATION}s bytes=${SIZE_BYTES}"
