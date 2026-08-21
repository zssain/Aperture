# Operations runbook

Deploy immutable SHA images, run `alembic upgrade head` as a gated task, publish a
catalogue if absent, run `verify_deployment.py`, then update ECS and wait for `/ready`.
Retain the prior task revision; rollback with `aws ecs update-service --cluster aperture
--service aperture-api --task-definition <previous>`.

For local production Compose, tag the last known-good API and frontend images as
`aperture-api:previous` and `aperture-frontend:previous` before updating. Roll back in one
command without rebuilding:

```bash
APERTURE_API_IMAGE=aperture-api:previous APERTURE_FRONTEND_IMAGE=aperture-frontend:previous \
  docker compose -f docker-compose.prod.yml up -d --no-build
```

The separate one-shot `migrate` service must complete successfully before API or worker
startup; neither application process runs migrations itself.

Migration failure stops deployment. Artifact/catalogue mismatch restores the recorded
version, never the expected hash. For backlog, inspect oldest job and scale workers. For
chain failure, make the tenant read-only and investigate from the first bad sequence.
Catalogue rebuild creates a draft and atomically publishes; never edit live entries.

Embedding outage makes misses `UNCLASSIFIED` and reduces coverage without failing a
decision. Bedrock outage uses templates. Disabling `LLM_NOTICES_ENABLED` is zero-impact.
