# Aperture — Pre-fix Bug Audit (Task 3) + Supabase Compatibility (Task 2)

Audited 2026-08-23 against the live local stack (API :8000, worker, SPA :5173, demo
seeded) plus a full code sweep. **No fixes applied yet — this is the prioritization
checkpoint.** Severity is by *demo* risk: P0 breaks/embarrasses the demo, P1 judges may
notice, P2 latent/correctness-hygiene.

Method: three code-sweep passes (frontend zero/null, backend zero/null, Supabase
compat) plus live API probing of every seeded persona as the analyst role, with each
flagged finding verified by hand (column nullability, actual rendered values, spec
consistency) before landing here. Several agent-flagged "critical" items were downgraded
after verification — noted explicitly so we don't fix non-bugs.

---

## A. Zero / null sweep

### A1. Confirmed masked-null bugs (fix)

| # | Pri | Location | Symptom | Root cause | Fix | Verified |
|---|-----|----------|---------|------------|-----|----------|
| Z1 | P1 | [EvidenceTab.tsx:44](frontend/src/features/case/tabs/EvidenceTab.tsx#L44) | Cash-flow chart/aggregate silently adds `0` for an event whose amount is unknown, while the transaction *table* right below honestly shows `—` for the same event. Inconsistent + dishonest. | `const amount = event.amount_paise ?? 0` in the aggregate reducer. `amount_paise` is a nullable column (verified in DB + model). | Skip null-amount events from the aggregate (they're a data-quality gap, not ₹0 of flow), matching the table's `—` treatment. | `ledger_events.amount_paise` is `nullable=YES` (DB + `models/ledger.py:66`). Non-null in current demo data, so **latent** — real once a malformed source lands. |
| Z2 | P2 | [orchestrator/assessments.py:178](backend/app/services/orchestrator/assessments.py#L178), [:234](backend/app/services/orchestrator/assessments.py#L234), [features/service.py:66](backend/app/services/features/service.py#L66) | Null `amount_paise` / `requested_amount_paise` coerced to `0` before affordability, manipulation detectors, and feature windows — a null loan amount would be assessed as a ₹0 loan; a null event amount becomes a ghost ₹0 transaction. | `x or 0` on nullable columns at the assessment boundary. | Guard: null requested amount → fail the decision (SYSTEM_UNAVAILABLE / reject at intake) rather than assess a phantom ₹0; drop null-amount events from detector/feature inputs explicitly. | Columns nullable (verified). Non-null in demo (intake schema requires amount; ingestion parses amounts) → **latent**, correctness-hygiene. |

### A2. Frontend display defaults to review (fix if truly optional)

| # | Pri | Location | Symptom | Assessment |
|---|-----|----------|---------|------------|
| Z3 | P2 | [QueuePage.tsx:178](frontend/src/features/queue/QueuePage.tsx#L178) | `"{auto_decided_24h ?? 0} decisions were made automatically"` shows "0 decisions" if the field is ever absent. | Needs backend-contract check: is `auto_decided_24h` always present? If yes, harmless; if optional, render `—`/"unknown". Low demo risk (empty-queue banner only). |
| Z4 | P2 | [PolicyStudioPage.tsx:50](frontend/src/features/policy/PolicyStudioPage.tsx#L50) | `n_snapshots ?? 0` in the publish modal. | If "no simulation run" vs "unknown count" — verify contract; likely legit 0. |

### A3. Verified NOT bugs (do not "fix" — would break honest behaviour or the spec)

- **Affordability null EMI / essential-expense → 0** ([affordability/service.py:118-119](backend/app/services/affordability/service.py#L118)). The backend sweep flagged this as its top "critical bug." **It is by design and matches the overview doc §30a verbatim** (`existing_emi = int(values.get("monthly_emi_paise") or 0)`). The invariant makes *income* INDETERMINATE when unobservable (correctly implemented, [:162-174](backend/app/services/affordability/service.py#L162)); obligations are cash-flow-observed, and "no EMI debits seen" is the honest ₹0 of debt service, not a masked null. Verified live: Nila (INDETERMINATE) returns `existing_emi_paise: 0` only because the whole affordability is already flagged INDETERMINATE and the DSR/disposable fields are `null`. **Leave as-is.** (Optional philosophical note for the team, not a fix.)
- **Queue sort coalesces** (`coalesce(pd,1.0)`, `coalesce(coverage,-1)`, `coalesce(amount,0)` in [queue/service.py](backend/app/services/queue/service.py)). These affect *sort order only*, never a displayed number — null PD sorts worst-case (fail-safe), which is intentional. Not display bugs.
- **`func.count(...) or 0`, `max(version) or 0`** — Postgres count/max are never null for these; dead-defensive, harmless.
- **`MetricValue` coverage** — verified: PD, coverage, DSR, approved-limit, contributions all render through `MetricValue`, which shows `—` + reason for null and the UNCAL chip for uncalibrated. The queue table and Assessment tab are correct. This is the core invariant and it holds.

### A4. Coverage completeness edge (verify)

- **`unclassified_inflow_share` default `0.0`** ([coverage/service.py:142](backend/app/services/coverage/service.py#L142)). For an applicant with **no income at all**, this feature is null and defaults to `0.0`, so the completeness penalty is skipped (treats unknown classification quality as perfect). Low impact (a no-income applicant already scores low on present-features), but worth a conservative guard. P2.

**Bottom line on zeros:** the headline invariant (MetricValue, UNCAL, null-with-reason) is *intact* in the UI. The real issues are (a) one genuine UI inconsistency (Z1: chart vs table), and (b) latent `or 0`/`?? 0` coercions on nullable columns that don't bite the current demo but violate the invariant and should be hardened. I did **not** find a blatant wrong-zero on the seeded happy path — if you saw a specific one, tell me which screen/persona and I'll target it.

---

## B. Functional / journey findings (probed live as analyst)

| # | Pri | Finding | Status |
|---|-----|---------|--------|
| F1 | — | Queue: all 7 views load; counts correct; `qa-sample` correctly 403s for analyst (role-gated). | ✅ working |
| F2 | — | Case file: all 12 personas return 200 with RISK/COVERAGE/AFFORDABILITY/MANIPULATION; INDETERMINATE (Nila) and fraud (Meera, D2+D5) render with proper null fields. | ✅ working |
| F3 | — | Live connect → decision, tampered-PDF upload → FRAUD_REVIEW, replay IDENTICAL, newly-eligible flip — all verified in prior session. | ✅ working |
| F4 | P2 | Not yet exercised this pass (need to test in fix phase): review/override reason validation, session-expiry mid-action, concurrent decide idempotency, GDPR export/delete, audit verify endpoint, health gated metrics as owner/auditor, Policy Studio mobile refusal, brand-new-tenant/zero-event empty states. | ⏳ to test |
| F5 | P2 | Browser console/PII-log hygiene on the full journey not yet captured (needs a real browser pass). | ⏳ to test |

No functional breakage found on the core path so far; F4/F5 are the untested surface I'll drive in the fix phase.

---

## C. Supabase migration compatibility (Task 2)

The inventory is clean and encouraging; **the recommended pooler mode from the automated sweep was wrong and I've corrected it** — this is the exact risk called out in the brief.

### C1. Compatible as-is (no code change)
- **pgvector**: `CREATE EXTENSION IF NOT EXISTS vector` + HNSW cosine index — Supabase supports (enable `vector` in the dashboard/SQL).
- **Immutability triggers / PL-pgSQL functions** (decisions, ledger, snapshots, catalogue) — all `LANGUAGE plpgsql`, no superuser DDL — run fine on Supabase.
- **SKIP LOCKED job claim** — `claim_job` sets RUNNING and **commits immediately**, releasing the row lock in a short transaction *before* running the handler ([jobs/runner.py:113-127](backend/app/jobs/runner.py#L113)). Lock lifecycle is one short tx.
- **Audit-chain sequence** under `SELECT … FOR UPDATE` on the tenant row — held for the caller's decision transaction; correct and Supabase-compatible.
- **Advisory locks** are all `pg_advisory_xact_lock` (transaction-scoped); no LISTEN/NOTIFY, no session `SET`, no long-lived cursors.

### C2. The correction — pooler mode + asyncpg (THE risk)
The automated sweep recommended the **transaction pooler (6543) for everything** and claimed "asyncpg default cache is safe on transaction mode." **That is wrong and would make the app silently misbehave:**
- **asyncpg uses prepared statements by default.** Through Supabase's transaction-mode pooler (Supavisor/PgBouncer), pooled server connections are shared across clients, so cached prepared-statement handles break → intermittent `prepared statement "__asyncpg_stmt__" does not exist` errors. Fix requires `connect_args={"statement_cache_size": 0}` (asyncpg) — the current engine ([db/session.py:20](backend/app/db/session.py#L20)) sets neither.
- **Alembic DDL** (CREATE EXTENSION / FUNCTION / multi-statement migrations, NullPool) needs a **direct/session** connection, not the transaction pooler.

**Corrected plan:**
| Process | Connection | Why |
|---|---|---|
| Alembic migrations | **Direct** (5432) | DDL, NullPool, session stability. |
| Worker | **Session pooler** (5432 session) or direct | Runs full pipeline transactions; keeps SKIP-LOCKED + row-lock semantics clean; low connection count. |
| API | **Session pooler** (simplest, safe) — *or* transaction pooler (6543) **only with** `statement_cache_size=0` | Avoids the prepared-statement landmine; demo concurrency is low so session mode is fine. |
| Any pooler + asyncpg | set `statement_cache_size=0` in `connect_args` regardless | Belt-and-suspenders against pooled prepared statements. |

Plus: tune SQLAlchemy `pool_size`/`max_overflow` to Supabase's connection cap; keep local Compose Postgres as the default dev target (env-selected).

### C3. Blocker
Running Alembic against Supabase and proving decision/replay/chain-verify green **needs a real Supabase project**: the **direct** connection string (5432) and the **session-pooler** string. I can't provision the project or connect without them. Everything else (config layer, `connect_args`, ADR, `.env.example`, runbook) I can build now and you drop the strings in.

---

## D. What I need from you (prioritization checkpoint)

1. **Supabase credentials** — create a project, enable the `vector` extension, and share the *direct* (5432) and *session-pooler* connection strings (or confirm you want me to wire the config + ADR + runbook now and you'll run the actual migration with your strings).
2. **Fix scope** — do you want me to fix only confirmed bugs (Z1 + the latent Z2 hardening + F4/F5 journey issues as found), or also apply the P2 hygiene guards (Z3/Z4/A4)?
3. **The specific zero you saw** — if there's a screen/persona where you saw a wrong 0, name it; I couldn't reproduce a blatant one on the seeded happy path (the UI's MetricValue path is honest), so pointing me at it beats me guessing.
