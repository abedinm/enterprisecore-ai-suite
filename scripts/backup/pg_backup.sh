#!/usr/bin/env bash
# pg_backup.sh — take a compressed pg_dump of the EnterpriseCore database,
# encrypt it, and upload to S3 (or any S3-compatible object store).
#
# Designed for cron / systemd timer / Kubernetes CronJob.
# All configuration via environment variables — no positional args.
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
#   BACKUP_S3_BUCKET     — destination bucket (no s3:// prefix)
#   BACKUP_S3_PREFIX     — prefix under the bucket (e.g. prod/)
#
# Optional env:
#   BACKUP_TMP_DIR       — working directory; default /var/lib/postgresql/backup-tmp
#   BACKUP_RETENTION_DAYS — local prune horizon; default 7
#   BACKUP_GPG_RECIPIENT — if set, encrypt with this GPG public key recipient
#   BACKUP_USE_SSE       — if set to "1", upload with --sse AES256 (default 1)
#   BACKUP_USE_OBJECT_LOCK — if set to "1", retain via S3 Object Lock for OBJECT_LOCK_DAYS
#   OBJECT_LOCK_DAYS     — retention days for Object Lock; default 30
#   PARALLEL_JOBS        — pg_dump parallel jobs; default 4
#   COMPRESSION_LEVEL    — pg_dump -Z; default 6
#   SLACK_WEBHOOK_URL    — if set, post success / failure
#
# Exit codes:
#   0  success
#   1  generic failure
#   2  dependency missing
#   3  S3 upload failed
#   4  encryption failed

set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  log "ERROR: $*"
  notify_slack "failure" "$*"
  exit "${2:-1}"
}

notify_slack() {
  local status="$1"; local msg="$2"
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    local color=$([ "$status" = "success" ] && echo "good" || echo "danger")
    curl -fsS -X POST -H 'Content-Type: application/json' \
      -d "$(printf '{"attachments":[{"color":"%s","text":"pg_backup %s on %s: %s"}]}' \
        "$color" "$status" "$(hostname)" "$msg")" \
      "$SLACK_WEBHOOK_URL" >/dev/null || true
  fi
}

# --- preflight ---------------------------------------------------------------

for bin in pg_dump aws; do
  command -v "$bin" >/dev/null 2>&1 || die "$bin not found in PATH" 2
done

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET is required}"
: "${BACKUP_S3_PREFIX:?BACKUP_S3_PREFIX is required}"

PGPORT="${PGPORT:-5432}"
BACKUP_TMP_DIR="${BACKUP_TMP_DIR:-/var/lib/postgresql/backup-tmp}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
BACKUP_USE_SSE="${BACKUP_USE_SSE:-1}"
BACKUP_USE_OBJECT_LOCK="${BACKUP_USE_OBJECT_LOCK:-0}"
OBJECT_LOCK_DAYS="${OBJECT_LOCK_DAYS:-30}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-6}"

mkdir -p "$BACKUP_TMP_DIR"

TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
BASENAME="ec-${PGDATABASE}-${TS}"
DUMP_PATH="${BACKUP_TMP_DIR}/${BASENAME}.pgc"

# --- dump --------------------------------------------------------------------

log "Starting pg_dump host=$PGHOST db=$PGDATABASE -> $DUMP_PATH"

# Directory-format dump for parallelism, then archive.
DUMP_DIR="${BACKUP_TMP_DIR}/${BASENAME}.d"
rm -rf "$DUMP_DIR"

pg_dump \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --format=directory \
  --jobs="$PARALLEL_JOBS" \
  --compress="$COMPRESSION_LEVEL" \
  --no-owner --no-privileges \
  --file="$DUMP_DIR" \
  || die "pg_dump failed"

log "pg_dump complete; packing"

# Pack the directory into a single archive for ease of upload / encryption.
tar -C "$BACKUP_TMP_DIR" -cf "$DUMP_PATH" "${BASENAME}.d"
rm -rf "$DUMP_DIR"

# --- encrypt -----------------------------------------------------------------

UPLOAD_PATH="$DUMP_PATH"
if [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
  command -v gpg >/dev/null 2>&1 || die "gpg required but not found" 2
  log "Encrypting with GPG recipient $BACKUP_GPG_RECIPIENT"
  gpg --batch --yes --trust-model always \
    --output "${DUMP_PATH}.gpg" \
    --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
    "$DUMP_PATH" \
    || die "gpg encrypt failed" 4
  rm -f "$DUMP_PATH"
  UPLOAD_PATH="${DUMP_PATH}.gpg"
fi

# --- checksum ----------------------------------------------------------------

SHA="$(sha256sum "$UPLOAD_PATH" | awk '{print $1}')"
SIZE="$(stat -c %s "$UPLOAD_PATH")"
log "Checksum sha256=$SHA size=$SIZE"

# --- upload ------------------------------------------------------------------

S3_KEY="${BACKUP_S3_PREFIX%/}/$(basename "$UPLOAD_PATH")"
S3_URI="s3://${BACKUP_S3_BUCKET}/${S3_KEY}"

UPLOAD_ARGS=()
[[ "$BACKUP_USE_SSE" = "1" ]] && UPLOAD_ARGS+=(--sse AES256)
UPLOAD_ARGS+=(
  --metadata "sha256=${SHA},size=${SIZE},source=$(hostname)"
)

if [[ "$BACKUP_USE_OBJECT_LOCK" = "1" ]]; then
  RETAIN_UNTIL="$(date -u -d "+${OBJECT_LOCK_DAYS} days" +%Y-%m-%dT%H:%M:%SZ)"
  UPLOAD_ARGS+=(
    --object-lock-mode COMPLIANCE
    --object-lock-retain-until-date "$RETAIN_UNTIL"
  )
fi

log "Uploading to $S3_URI"
aws s3 cp "$UPLOAD_PATH" "$S3_URI" "${UPLOAD_ARGS[@]}" \
  || die "s3 upload failed" 3

# --- local prune -------------------------------------------------------------

log "Pruning local backups older than $BACKUP_RETENTION_DAYS days"
find "$BACKUP_TMP_DIR" -maxdepth 1 -type f -name "ec-*.pgc*" \
  -mtime "+$BACKUP_RETENTION_DAYS" -delete || true

# --- done --------------------------------------------------------------------

log "Backup complete uri=$S3_URI sha256=$SHA size=$SIZE"
notify_slack "success" "$S3_URI size=$SIZE"
