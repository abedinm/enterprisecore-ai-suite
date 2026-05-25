#!/usr/bin/env bash
# pg_backup_verify.sh — pull the latest backup from S3, restore into a temp
# database, run sanity queries. Fails non-zero if anything looks wrong.
#
# This is the single most important DR control. Run at least monthly.
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD
#   VERIFY_DB             — name of the temp DB to create; default ec_verify
#   BACKUP_S3_BUCKET, BACKUP_S3_PREFIX
#
# Optional env:
#   BACKUP_KEY            — exact S3 key to verify; default = latest object
#   BACKUP_GPG_RECIPIENT  — if backups were encrypted; needs gpg-agent w/ key loaded
#   BACKUP_TMP_DIR        — default /var/lib/postgresql/backup-tmp
#   SLACK_WEBHOOK_URL     — alert on failure
#   MIN_USERS, MIN_TENANTS — sanity thresholds; defaults 1, 1

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit "${2:-1}"; }

: "${PGHOST:?}"; : "${PGUSER:?}"
: "${BACKUP_S3_BUCKET:?}"; : "${BACKUP_S3_PREFIX:?}"

PGPORT="${PGPORT:-5432}"
VERIFY_DB="${VERIFY_DB:-ec_verify}"
BACKUP_TMP_DIR="${BACKUP_TMP_DIR:-/var/lib/postgresql/backup-tmp}"
MIN_USERS="${MIN_USERS:-1}"
MIN_TENANTS="${MIN_TENANTS:-1}"
mkdir -p "$BACKUP_TMP_DIR"

# --- pick a backup -----------------------------------------------------------

if [[ -z "${BACKUP_KEY:-}" ]]; then
  log "Selecting most recent backup from s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}"
  BACKUP_KEY="$(aws s3 ls "s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX%/}/" \
    | grep -E 'ec-.*\.(pgc|pgc\.gpg)$' \
    | sort -k1,2 \
    | tail -1 | awk '{print $4}')" || die "no backups found"
fi

[[ -n "$BACKUP_KEY" ]] || die "no backup key resolved"

S3_URI="s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX%/}/${BACKUP_KEY}"
LOCAL="${BACKUP_TMP_DIR}/${BACKUP_KEY}"
log "Verifying $S3_URI"

aws s3 cp "$S3_URI" "$LOCAL" || die "download failed"

# --- decrypt -----------------------------------------------------------------

DUMP_PATH="$LOCAL"
if [[ "$LOCAL" == *.gpg ]]; then
  command -v gpg >/dev/null 2>&1 || die "gpg required"
  log "Decrypting"
  gpg --batch --yes --decrypt --output "${LOCAL%.gpg}" "$LOCAL"
  DUMP_PATH="${LOCAL%.gpg}"
fi

# --- unpack ------------------------------------------------------------------

UNPACK_DIR="${BACKUP_TMP_DIR}/verify.$$"
mkdir -p "$UNPACK_DIR"
tar -xf "$DUMP_PATH" -C "$UNPACK_DIR"
DUMP_DIR="$(find "$UNPACK_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)"
[[ -d "$DUMP_DIR" ]] || die "no directory in archive"

# --- restore into temp DB ----------------------------------------------------

cleanup() {
  log "Cleaning up"
  psql -d postgres -c "DROP DATABASE IF EXISTS \"${VERIFY_DB}\";" >/dev/null 2>&1 || true
  rm -rf "$UNPACK_DIR" "$DUMP_PATH" "$LOCAL"
}
trap cleanup EXIT

log "Creating $VERIFY_DB and restoring"
psql -d postgres -c "DROP DATABASE IF EXISTS \"${VERIFY_DB}\";"
psql -d postgres -c "CREATE DATABASE \"${VERIFY_DB}\";"

pg_restore --dbname="$VERIFY_DB" --no-owner --no-privileges \
  --jobs=4 "$DUMP_DIR" \
  || die "pg_restore failed"

# --- sanity queries ----------------------------------------------------------

q() { psql -d "$VERIFY_DB" -tAc "$1"; }

USERS="$(q 'SELECT count(*) FROM users')"
TENANTS="$(q 'SELECT count(*) FROM tenants')"
LATEST_AUDIT="$(q 'SELECT max(created_at) FROM audit_log')"
SCHEMA_HEAD="$(q "SELECT version_num FROM alembic_version" || echo unknown)"

log "users=$USERS tenants=$TENANTS latest_audit=$LATEST_AUDIT schema=$SCHEMA_HEAD"

(( USERS >= MIN_USERS )) || die "users count $USERS < $MIN_USERS"
(( TENANTS >= MIN_TENANTS )) || die "tenants count $TENANTS < $MIN_TENANTS"

log "VERIFY OK"
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  curl -fsS -X POST -H 'Content-Type: application/json' \
    -d "$(printf '{"text":"pg_backup_verify OK key=%s users=%s tenants=%s schema=%s"}' \
      "$BACKUP_KEY" "$USERS" "$TENANTS" "$SCHEMA_HEAD")" \
    "$SLACK_WEBHOOK_URL" >/dev/null || true
fi
