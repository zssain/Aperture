# Architecture

```text
[Frontend: React/Vite, MetricValue/GatedMetric]
             | TLS + session + CSRF
[Backend: FastAPI routes -> services -> policy/orchestrator -> jobs]
             | tenant-scoped async SQLAlchemy
[Database: PostgreSQL 16 + pgvector, immutable evidence/decision/audit ledgers]
             | provider protocols only
[AI layer: local embeddings | opt-in Titan; Bedrock -> prompts -> guardrails]
             | managed interfaces
[Cloud: ECR -> ECS Fargate -> RDS pgvector + S3; CloudWatch; TLS ingress]
             | Secrets Manager + KMS + IAM
[Security: RBAC/404 tenancy, CSP, CSRF, rate limits, PII logs, retention]
```

Consent gates ingestion. Adapters normalize evidence into immutable ledger events.
Rules classify first; only abstentions may use pgvector, and weak/disagreeing matches stay
`UNCLASSIFIED`. Features filter `occurred_at <= as_of`; hashes include events, schema,
classifier and catalogue. Four assessments feed policy. The orchestrator atomically
commits decision, reasons, recourse and audit entry. Replay uses recorded artifacts and
cached classifications with both AI providers disabled.

Similarity, embeddings and narration are barred from risk, policy and notices. Bedrock
receives only typed fields; every output passes seven guardrails or templates are used.

## Threat model

| Asset | Threat | Control | Gap / disposition |
|---|---|---|---|
| Ledger | cross-tenant IDOR | structural filters and 404 | Closed by route tests |
| Upload | malware/parser exhaustion | magic bytes, scan hook, subprocess, caps | Scanner supplied at deploy |
| Logs | PII/narration/vector leak | field allow-list | Closed by fixture grep |
| Embeddings | third-party narration egress | local default; external flag false | Titan requires explicit opt-in |
| Bedrock | injection/data egress | typed allow-list, no ledger path | Closed by corpus/assertion |
| Bedrock cost | abusive calls | 60/hour/tenant, token cap, timeout | Closed |
| Decisions | mutation/audit loss | DB triggers, hash chain, retention | Never purged |
| Credentials | source/bundle/log leak | Secrets Manager, IAM, scanners | Manager outage fails startup |

RDS and S3 are **DESIGNED** with TLS and KMS encryption via `KMS_KEY_ARN`.
Secrets Manager is production secret storage and CloudWatch receives JSON logs/metrics.
The task definition is runnable after documented substitutions; resources are not claimed
live. Merchant catalogue reference data is not applicant data and is retention-exempt.
