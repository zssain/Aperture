# ADR 0001 — Supabase for database hosting only (not Auth/SDK)

- Status: Accepted
- Date: 2026-08-23

## Context

We want a hosted Postgres so the app runs off a laptop without operating our own DB.
Supabase gives managed Postgres 16 with pgvector, backups, and a connection pooler.
Aperture already depends on a specific Postgres feature set:

- `pgvector` (merchant catalogue + KNN classification),
- PL/pgSQL immutability triggers on decisions/ledger/snapshots,
- `SELECT … FOR UPDATE SKIP LOCKED` for the job queue,
- a per-tenant row-lock sequence allocation for the hash-chained audit ledger,
- transaction-scoped advisory locks (rate limiting, tenant-salt init),
- Alembic-managed schema with custom DDL.

The security story also rests on our **own** Argon2id password hashing and
SHA-256-hashed session cookies (HttpOnly/Secure/SameSite=Strict, 8h sliding idle).

## Decision

Use Supabase **only as the Postgres host**. Keep FastAPI, SQLAlchemy (async, asyncpg),
Alembic, the custom auth, and every application/service unchanged. Do **not** adopt the
Supabase client SDK, Supabase Auth, Storage, or Realtime for this migration.

Connection topology (the load-bearing part):

| Process | Supabase connection | Why |
|---|---|---|
| Alembic migrations | **Direct** (`db.[ref].supabase.co:5432`), via `alembic -x db_url=…` | DDL + `CREATE EXTENSION`/`CREATE FUNCTION`/multi-statement migrations under `NullPool`; needs a stable, non-multiplexed session. |
| Worker | **Session pooler** (`…pooler.supabase.com:5432`, session mode) | Runs the full decision transaction (holds the audit-chain row lock); relies on clean SKIP-LOCKED semantics. Session mode avoids surprises. |
| API | **Session pooler** (default) — or transaction pooler (6543) **with `DB_STATEMENT_CACHE_SIZE=0`** | Session mode is the simplest safe choice at demo concurrency. |
| Any pooled connection | set `DB_STATEMENT_CACHE_SIZE=0` | asyncpg caches prepared statements per connection; a transaction-mode pooler shares server connections across clients and invalidates those handles. |

Code changes were limited to `app/core/config.py` (pool sizing + optional
`statement_cache_size`) and `app/db/session.py` (apply them). Local docker-compose
Postgres remains the default dev target; Supabase is selected purely by `DATABASE_URL`.

## Why not the transaction pooler for everything

An automated compatibility pass initially recommended the transaction pooler (6543)
for all processes and claimed asyncpg's default statement cache was safe there. It is
not: asyncpg + PgBouncer/Supavisor transaction mode raises intermittent
`prepared statement "__asyncpg_stmt__" does not exist` at runtime unless the statement
cache is disabled. That is the classic silent-misbehaviour trap for this stack, so the
default is session-mode/direct and `statement_cache_size=0` is mandatory whenever a
pooler is used.

## Why not Supabase Auth

Our auth is part of the product's security narrative: Argon2id, process-local **and**
DB rate limiting, constant-time work even for unknown emails, sessions stored only as
SHA-256 hashes with immediate revocation. Swapping to Supabase Auth would discard that
and couple decisioning to a third-party identity service. Out of scope.

## Compatibility (verified by code audit — see docs/BUG_AUDIT.md §C)

All Supabase-supported: pgvector + HNSW cosine index, PL/pgSQL immutability triggers
(no superuser DDL), SKIP-LOCKED claim (claims then commits immediately — short lock),
audit row lock, xact-scoped advisory locks. No LISTEN/NOTIFY, no session-level `SET`,
no long-lived cursors.

## Consequences

- One env var (`DATABASE_URL`) switches local ↔ Supabase; migrations take the direct
  URL via `-x db_url`.
- `DB_STATEMENT_CACHE_SIZE=0` is required for pooled connections; documented in
  `.env.example` and the runbook.
- Pool sizing must stay under the plan's connection cap across API + worker processes.

## Post-hackathon: a fuller Supabase adoption could add

- **Storage** for raw statement uploads (short-lived, KMS-encrypted, off the web root)
  instead of the local `UPLOAD_DIRECTORY`.
- **Realtime** to push queue/newly-eligible changes to analysts instead of polling.
- **Auth** *only* if we can preserve the current guarantees (or run it alongside as an
  IdP with our session layer on top). Not a like-for-like replacement.
- Row-Level Security as defence-in-depth behind the app's existing tenant scoping.
