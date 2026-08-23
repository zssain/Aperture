# Supabase migration runbook (DB-hosting only)

Aperture runs on plain Postgres 16 + pgvector. Supabase is an **env-selected host** —
the local docker-compose Postgres remains the default dev target. See
[adr/0001-supabase-db-hosting-only.md](adr/0001-supabase-db-hosting-only.md) for the why
and [BUG_AUDIT.md §C](BUG_AUDIT.md) for the compatibility audit.

## Local dev (unchanged, default)

```bash
make up            # docker-compose Postgres on :5432
make migrate       # alembic upgrade head
make demo-reset    # seed the demo book
make dev           # API + worker + SPA
```
`DATABASE_URL=postgresql+asyncpg://aperture:aperture@localhost:5432/aperture` (no pooler,
no `DB_STATEMENT_CACHE_SIZE`).

## Supabase target

### 1. Create the project + enable pgvector
- New Supabase project (note the project ref, region, DB password).
- SQL editor: `create extension if not exists vector;` (readiness also runs
  `CREATE EXTENSION IF NOT EXISTS vector`, but enable it explicitly first).

### 2. Grab the three connection strings (Project Settings → Database)
Convert each scheme to `postgresql+asyncpg://`.
- **Direct** (migrations): `...@db.[REF].supabase.co:5432/postgres`
- **Session pooler** (app + worker): `...@aws-0-[REGION].pooler.supabase.com:5432/postgres`
- Transaction pooler (6543) — only if you must; then set `DB_STATEMENT_CACHE_SIZE=0`.

### 3. Point the app at the session pooler
In `.env`:
```
DATABASE_URL=postgresql+asyncpg://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
# only if using the 6543 transaction pooler:
# DB_STATEMENT_CACHE_SIZE=0
```

### 4. Migrate with the DIRECT connection (never through a pooler)
```bash
cd backend
uv run alembic -x db_url="postgresql+asyncpg://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres" upgrade head
```

### 5. Publish the catalogue + seed the demo book
```bash
# uses DATABASE_URL (session pooler)
DEMO_SEED_ENABLED=true uv run python scripts/demo_reset.py
```
(If you use a real embedding provider, `build_catalog.py` publishes a live catalogue;
otherwise the seed publishes the deterministic demo catalogue.)

### 6. Start the app against Supabase
```bash
make dev     # API + worker + SPA, all on the session pooler
```

## Proof checklist (all must be green on Supabase)

Run against the Supabase-backed API (uses the same probes as local):

```bash
cd backend
make demo-check          # live connect -> decision through the worker, verification CLEAR
make demo-flip           # verified-income events -> newly-eligible re-decision (SKIP-LOCKED worker)
```
Then, as the auditor:
- **Decision + replay**: open any case → Decision & Audit → Replay → **IDENTICAL** with
  matching hashes (proves determinism survives the host change).
- **Audit chain verify**: `GET /api/v1/audit/verify` → `{"valid": true}` (proves the
  row-lock sequence allocation is intact under the pooler).
- **Vector classification**: Evidence tab shows `RULE`/`VECTOR_KNN` badges (pgvector KNN
  works on Supabase).
- **Job queue**: `make demo-flip` completing proves `FOR UPDATE SKIP LOCKED` claims and
  the worker drains jobs.

If `demo-check` returns FRAUD_REVIEW or a `prepared statement … does not exist` error
appears in logs, you are on the transaction pooler without `DB_STATEMENT_CACHE_SIZE=0`
— fix the env and restart.

## Rollback
Set `DATABASE_URL` back to the local compose string and `make dev`. Supabase data is
untouched; nothing about the app is Supabase-specific beyond the connection string.
