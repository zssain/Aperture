# APERTURE

APERTURE produces deterministic, traceable credit decisions for new-to-credit and
thin-file applicants from consented financial behaviour. Four independent assessments
(risk, affordability, coverage, manipulation) feed a versioned policy engine; only that
engine decides. Every decision is immutable, network-free to replay, and accompanied by
plain-language reasons and recourse.

See [the architecture](docs/ARCHITECTURE.md) for the six-layer diagram and lifecycle.

## Prerequisites

- Docker Desktop with Compose v2
- Python 3.11 and `uv`
- Node.js 20+ and npm
- 8 GB free disk space for the optional local embedding runtime

## Setup and run

```bash
cp .env.example .env
make install
make up
make migrate
make dev
```

The default developer install runs in the fully supported provider-disabled mode. Production
Compose builds the local embedding extra and model into the image, so narration does not leave
the deployment. To enable that path locally, run `cd backend && uv sync --extra embeddings`;
for a standalone image use
`docker build --build-arg UV_EXTRAS=embeddings -f deploy/Dockerfile.api .`.

Open `http://localhost:5173`; liveness is `/api/v1/health` and readiness is
`/api/v1/ready`. Migrations are a gated step and never run on app start.

```bash
make lint && make typecheck && make test
cd frontend && npm run test:e2e
make demo-reset          # seed the demo book + generate demo/statements (~5 s)
```

For a live demo, see [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) and
[demo/README.md](demo/README.md). `make demo-reset` / `make demo-flip` / `make demo-ids`
drive the rehearsed flow; `make dev` now also starts the job worker.

## Environment variables

| Variable | Required | Default / purpose |
|---|---:|---|
| `DATABASE_URL` | yes | Async PostgreSQL URL; managed secret in cloud |
| `FRONTEND_ORIGIN` | yes | Exact allowed SPA origin |
| `ENVIRONMENT` / `LOG_LEVEL` | no | `development` / `INFO` |
| `SESSION_COOKIE_SECURE` | no | `true` |
| `EMBEDDING_PROVIDER` | no | `noop`; production Compose uses bundled `local` embeddings |
| `EMBEDDING_MODEL_ID` / `EMBEDDING_DIMENSION` | no | MiniLM-L6-v2 / `384` |
| `VECTOR_SIMILARITY_FLOOR` | no | `0.82` |
| `ALLOW_EXTERNAL_EMBEDDINGS` | no | `false`; required true for Titan egress |
| `LLM_PROVIDER` / `LLM_NOTICES_ENABLED` | no | `noop` / `false` |
| `LLM_NOTICE_TIMEOUT_SECONDS` / `LLM_MAX_TOKENS` | no | `5` / `1200` |
| `AWS_REGION` | no | `ap-south-1` |
| `BEDROCK_MODEL_ID` | no | `amazon.nova-lite-v1:0` |
| `BEDROCK_EMBEDDING_MODEL_ID` | no | `amazon.titan-embed-text-v2:0` |
| `SECRET_PROVIDER` | no | `environment`; cloud uses `aws_secrets_manager` |
| `AWS_SECRET_ID` / `KMS_KEY_ARN` | cloud | Managed secret and KMS key ARNs |
| `UPLOAD_DIRECTORY` | no | `/tmp/aperture-uploads` |
| `UPLOAD_MAX_BYTES` / `UPLOAD_MAX_ROWS` | no | `10485760` / `20000` |
| `DEMO_SEED_ENABLED` / `DEMO_EVENTS_ENABLED` | no | `false` / `false` |

AWS credentials use the standard SDK chain and are never application values.

## Built vs designed

| Capability | State |
|---|---|
| Decision pipeline, security middleware, pgvector catalogue | BUILT |
| Local Compose, production images, deployment verifier | BUILT |
| Demo kit: seeded persona book, statement files, one-command reset/flip | BUILT (sandbox) |
| Connect-a-bank UX (bank picker + consent artefact panel) over the simulated AA | BUILT; real AA integration is ROADMAP |
| ECS task definition and AWS procedure | BUILT artifact |
| Provisioned ECR/ECS/RDS/S3/KMS/Secrets Manager | DESIGNED, not provisioned here |
| Real lender integrations, OIDC/SSO, automated retraining | ROADMAP |
