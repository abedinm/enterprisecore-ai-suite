# Runbook — Failed deployment rollback

## Symptoms

- Post-deploy alert: error rate or latency SLO violated within 10 minutes of deploy.
- `ec_build_info{version="<new>"}` is present but `ec_http_requests_total{status=~"5.."}` is elevated.
- Synthetic checks failing.

## Severity

- **Sev 1** during business hours, **Sev 2** if discovered overnight with no customer impact.

## Immediate mitigation

The rule: **rollback first, investigate after.** Do not try to roll forward unless the fix is trivial and verified in staging.

1. Identify the previous good version:

   ```bash
   # From git
   git tag --sort=-creatordate | head -5

   # Or from container registry
   aws ecr describe-images --repository-name ec-backend \
     --query 'sort_by(imageDetails,&imagePushedAt)[-5:].imageTags'
   ```

2. Roll back the backend:

   ```bash
   # Kubernetes
   kubectl rollout undo deploy/ec-backend
   kubectl rollout status deploy/ec-backend

   # ECS
   aws ecs update-service --cluster ec --service ec-backend \
     --task-definition ec-backend:$PREVIOUS_REVISION

   # systemd / SystemD-deployed VM
   sudo /opt/ec/bin/deploy.sh $PREVIOUS_TAG
   ```

3. Roll back the frontend if it was part of the same release:

   ```bash
   # CDN / S3
   aws s3 sync s3://ec-frontend-archive/$PREVIOUS_TAG/ s3://ec-frontend/
   aws cloudfront create-invalidation --distribution-id $CF_DIST --paths '/*'
   ```

4. **Database migrations** — this is the dangerous part. Check whether the failed deploy ran a migration:

   ```bash
   alembic current
   git diff $PREVIOUS_TAG...HEAD -- backend/alembic/versions/ | grep "^+++"
   ```

   - If no new migrations: nothing to do.
   - If new migrations BUT they are forward-compatible (additive — new columns/tables only), leave them. The previous version ignores the additions.
   - If destructive (dropped columns, renamed tables): you need the migration's `downgrade` path:

     ```bash
     alembic downgrade -1
     ```

     If `downgrade` is `pass`, restore from a backup taken before the deploy.

   The release-process doc requires every migration to either be additive-only or to have a verified `downgrade` — see `docs/RELEASE_PROCESS.md`.

5. Verify the rollback:

   ```bash
   curl -fsS https://app.example.com/api/v1/healthz | jq .
   curl -fsS https://app.example.com/api/v1/readyz | jq .
   curl -fsS https://app.example.com/metrics | grep ec_build_info
   ```

## Root cause investigation

After mitigation, isolate the failing change:

```bash
git log $PREVIOUS_TAG..$BAD_TAG --oneline
```

Triage:

- Code regression — reproduce locally, write a failing test, fix forward.
- Config / env regression — diff `deploy/` between tags.
- Migration regression — reproduce on a staging clone of production.
- Infra regression — image, base layer, or runtime change.

## Permanent fix

- Add a test that catches the regression.
- If migration safety was the issue, expand the pre-deploy checklist in `docs/RELEASE_PROCESS.md`.
- Tighten canary / progressive-rollout thresholds.

## Postmortem checklist

- [ ] Time from deploy → detection → mitigation. Each should be <10 minutes.
- [ ] Was rollback automatic or manual? Move toward automatic.
- [ ] Did migrations require a downgrade or restore?
- [ ] Was the customer impacted? If yes, status-page update and a follow-up email.
- [ ] Update SLO error budget consumption.
