# AWS deployment

The checked-in ECS Fargate task definition is complete after replacing its clearly named
values. Build SHA-tagged images to ECR; provision RDS PostgreSQL 16 with pgvector enabled,
private subnets/security groups, an S3 upload bucket, customer-managed KMS encryption,
Secrets Manager, CloudWatch log groups, an ALB TLS listener/certificate, ECS cluster and
IAM roles. Run Alembic as a one-off gated task, then `verify_deployment.py`, before service
update. Use RDS parameter/extension SQL `CREATE EXTENSION vector` during provisioning.
Build the API image with `--build-arg UV_EXTRAS=embeddings`; the task definition defaults to
that bundled local model so applicant narration has no external embedding egress.

The task definition, images and procedure are **BUILT**. The AWS account resources above
are **DESIGNED, not provisioned by this repository**. Uploads use the existing storage
interface; the S3 implementation is a deployment adapter. Rollback selects the prior ECS
task revision/image SHA. Local `docker-compose.prod.yml` is the independently supported path.
