#!/usr/bin/env bash
# point_in_time_recovery.sh — PITR via the cloud provider's managed Postgres.
#
# This script is a thin wrapper that calls aws / gcloud / az CLIs depending on
# the provider. It does NOT perform PITR on self-managed Postgres — for that
# you must restore from a basebackup and replay WAL manually.
#
# Required env:
#   PROVIDER             — aws | gcp | azure
#   SOURCE_INSTANCE      — provider-specific identifier of the existing instance
#   TARGET_INSTANCE      — name of the new instance to create
#   TARGET_TIMESTAMP     — ISO 8601 UTC timestamp to recover to
#
# Optional env:
#   AWS_REGION           — for aws
#   GCP_PROJECT          — for gcp
#   GCP_REGION           — for gcp
#   AZURE_RG             — for azure
#   AZURE_SERVER         — for azure (existing server name)
#   AZURE_LOCATION       — for azure
#
# This script prints the provider command before running it so the on-call
# can copy/paste to adjust.

set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

: "${PROVIDER:?PROVIDER required (aws|gcp|azure)}"
: "${SOURCE_INSTANCE:?}"; : "${TARGET_INSTANCE:?}"; : "${TARGET_TIMESTAMP:?}"

case "$PROVIDER" in

  aws)
    : "${AWS_REGION:?AWS_REGION required}"
    log "AWS RDS PITR: source=$SOURCE_INSTANCE target=$TARGET_INSTANCE at=$TARGET_TIMESTAMP"
    CMD=(aws rds restore-db-instance-to-point-in-time
      --region "$AWS_REGION"
      --source-db-instance-identifier "$SOURCE_INSTANCE"
      --target-db-instance-identifier "$TARGET_INSTANCE"
      --restore-time "$TARGET_TIMESTAMP"
      --no-publicly-accessible)
    log "Command: ${CMD[*]}"
    "${CMD[@]}"
    log "RDS instance creation initiated. Poll status with:"
    log "  aws rds describe-db-instances --db-instance-identifier $TARGET_INSTANCE"
    ;;

  gcp)
    : "${GCP_PROJECT:?GCP_PROJECT required}"
    log "GCP Cloud SQL PITR: source=$SOURCE_INSTANCE target=$TARGET_INSTANCE at=$TARGET_TIMESTAMP"
    CMD=(gcloud sql instances clone "$SOURCE_INSTANCE" "$TARGET_INSTANCE"
      --project="$GCP_PROJECT"
      --point-in-time="$TARGET_TIMESTAMP")
    log "Command: ${CMD[*]}"
    "${CMD[@]}"
    log "Cloud SQL clone initiated. Poll status with:"
    log "  gcloud sql instances describe $TARGET_INSTANCE --project=$GCP_PROJECT"
    ;;

  azure)
    : "${AZURE_RG:?AZURE_RG required}"
    : "${AZURE_SERVER:=$SOURCE_INSTANCE}"
    : "${AZURE_LOCATION:?AZURE_LOCATION required}"
    log "Azure Postgres PITR: source=$AZURE_SERVER target=$TARGET_INSTANCE at=$TARGET_TIMESTAMP"
    CMD=(az postgres flexible-server restore
      --resource-group "$AZURE_RG"
      --name "$TARGET_INSTANCE"
      --source-server "$AZURE_SERVER"
      --restore-time "$TARGET_TIMESTAMP"
      --location "$AZURE_LOCATION")
    log "Command: ${CMD[*]}"
    "${CMD[@]}"
    log "Azure restore initiated. Poll status with:"
    log "  az postgres flexible-server show -g $AZURE_RG -n $TARGET_INSTANCE"
    ;;

  *)
    die "unknown provider: $PROVIDER"
    ;;
esac

log "PITR command submitted. Next steps:"
log "  1. Wait for the new instance to be available."
log "  2. Cut DNS / connection string to the new instance."
log "  3. Run the post-restore smoke test (see docs/runbooks/database-restore.md)."
log "  4. Decommission the old instance only after a clean window."
