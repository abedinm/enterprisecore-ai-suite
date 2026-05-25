#!/usr/bin/env bash
# pg_restore.sh — restore EnterpriseCore database from an S3 backup.
#
# WARNING: destructive. Drops the target database. Always pre-snapshot the
# current state before running this in production.
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD
#   BACKUP_KEY            — full S3 URI to restore (s3://bucket/key)
#
# Optional env:
#   PGDATABASE            — target database name; default enterprisecore
#   PARALLEL_JOBS         — pg_restore -j; default 4
#   BACKUP_TMP_DIR        — default /var/lib/postgresql/backup-tmp
#   BACKUP_GPG_RECIPIENT  — if backup was encrypted; gpg-agent must hold the key
#   FORCE                 — set to 1 to skip the confirmation prompt
#   GRANTS_FILE           — SQL with GRANT statements; default /opt/ec/scripts/restore/grants.sql
#   ALEMBIC_DIR           — if set, run `alembic upgrade head` after restore
#   RUN_ANALYZE           — default 1
#   SLACK_WEBHOOK_URL     — notify on success / failure

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; notify "failure" "$*"; exit 1; }
notify() {
  local status="$1"; local msg="$2"
  [[ -n "${SLACK_WEBHOOK_URL:-}" ]] || return 0
  local color=$([ "$status" = "success" ] && echo good || echo danger)
  curl -fsS -X POST -H 'Content-Type: application/json' \
    -d "$(printf '{"attachments":[{"color":"%s","text":"pg_restore %s on %s: %s"}]}' \
      "$color" "$status" "$(hostname)" "$msg")" \
    "$SLACK_WEBHOOK_URL" >/dev/null || true
}

: "${PGHOST:?}"; : "${PGUSER:?}"; : "${BACKUP_KEY:?}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-enterprisecore}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
BACKUP_TMP_DIR="${BACKUP_TMP_DIR:-/var/lib/postgresql/backup-tmp}"
GRANTS_FILE="${GRANTS_FILE:-$(dirname "$0")/grants.sql}"
RUN_ANALYZE="${RUN_ANALYZE:-1}"
FORCE="${FORCE:-0}"

mkdir -p "$BACKUP_TMP_DIR"

# --- confirm -----------------------------------------------------------------

if [[ "$FORCE" != "1" ]]; then
  echo "About to DROP database '$PGDATABASE' on $PGHOST and restore from $BACKUP_KEY."
  echo "Type the database name to confirm:"
  read -r CONFIRM
  [[ "$CONFIRM" == "$PGDATABASE" ]] || die "confirmation mismatch"
fi

# --- pre-snapshot ------------------------------------------------------------

SNAP_PATH="${BACKUP_TMP_DIR}/pre-restore-${PGDATABASE}-$(date -u +%Y%m%dT%H%M%SZ).pgc"
log "Pre-restore snapshot -> $SNAP_PATH"
if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
  pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
          --dbname="$PGDATABASE" --format=custom --compress=6 \
          --no-owner --no-privileges \
          --file="$SNAP_PATH" \
    || log "WARNING: pre-snapshot failed; continuing"
else
  log "database not currently reachable; skipping pre-snapshot"
fi

# --- download ----------------------------------------------------------------

LOCAL="${BACKUP_TMP_DIR}/$(basename "$BACKUP_KEY")"
log "Downloading $BACKUP_KEY -> $LOCAL"
aws s3 cp "$BACKUP_KEY" "$LOCAL" || die "download failed"

# --- decrypt -----------------------------------------------------------------

DUMP_PATH="$LOCAL"
if [[ "$LOCAL" == *.gpg ]]; then
  command -v gpg >/dev/null 2>&1 || die "gpg required"
  log "Decrypting"
  gpg --batch --yes --decrypt --output "${LOCAL%.gpg}" "$LOCAL"
  DUMP_PATH="${LOCAL%.gpg}"
fi

# --- unpack ------------------------------------------------------------------

UNPACK_DIR="${BACKUP_TMP_DIR}/restore.$$"
mkdir -p "$UNPACK_DIR"
tar -xf "$DUMP_PATH" -C "$UNPACK_DIR"
DUMP_DIR="$(find "$UNPACK_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)"
[[ -d "$DUMP_DIR" ]] || die "no directory in archive"

# --- drop + recreate ---------------------------------------------------------

log "Dropping and recreating database $PGDATABASE"
psql -d postgres -c "SELECT pg_terminate_backend(pid)
                     FROM pg_stat_activity
                     WHERE datname='${PGDATABASE}' AND pid <> pg_backend_pid();" >/dev/null
psql -d postgres -c "DROP DATABASE IF EXISTS \"${PGDATABASE}\";"
psql -d postgres -c "CREATE DATABASE \"${PGDATABASE}\";"

# --- restore -----------------------------------------------------------------

log "Restoring with $PARALLEL_JOBS parallel jobs"
pg_restore --dbname="$PGDATABASE" \
  --no-owner --no-privileges \
  --jobs="$PARALLEL_JOBS" \
  "$DUMP_DIR" \
  || die "pg_restore failed"

# --- grants ------------------------------------------------------------------

if [[ -f "$GRANTS_FILE" ]]; then
  log "Applying $GRANTS_FILE"
  psql -d "$PGDATABASE" -f "$GRANTS_FILE" || die "grants apply failed"
fi

# --- migrations --------------------------------------------------------------

if [[ -n "${ALEMBIC_DIR:-}" ]]; then
  log "Running alembic upgrade head in $ALEMBIC_DIR"
  ( cd "$ALEMBIC_DIR" && alembic upgrade head ) || die "alembic upgrade failed"
fi

# --- analyze -----------------------------------------------------------------

if [[ "$RUN_ANALYZE" = "1" ]]; then
  log "Running ANALYZE"
  psql -d "$PGDATABASE" -c "ANALYZE;" >/dev/null
fi

# --- sanity ------------------------------------------------------------------

USERS=$(psql -d "$PGDATABASE" -tAc 'SELECT count(*) FROM users')
TENANTS=$(psql -d "$PGDATABASE" -tAc 'SELECT count(*) FROM tenants')
log "Post-restore counts users=$USERS tenants=$TENANTS"

rm -rf "$UNPACK_DIR" "$DUMP_PATH" "$LOCAL"

log "Restore complete from $BACKUP_KEY"
notify "success" "restored $PGDATABASE from $BACKUP_KEY users=$USERS tenants=$TENANTS"
