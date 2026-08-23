# Demo-Readiness UX Audit

Audited 2026-08-23 against a live local environment (Postgres + API + SPA up, demo book
seeded) from three perspectives: a credit analyst working the queue, a policy owner in
Policy Studio, and a first-time judge watching a 3-minute demo.

Priorities: **P0** breaks the demo · **P1** judges will notice · **P2** nice to have.
Effort: S (&lt; 1 h) · M (half day) · L (day+).

## Findings

| # | Pri | Finding | Evidence | Fix | Effort |
|---|-----|---------|----------|-----|--------|
| 1 | P0 | **Every live "connect bank" case routes to FRAUD_REVIEW.** The mock Account Aggregator computes running balances in generation order, then sorts transactions by date, so balances never reconcile and D5 (balance arithmetic, confidence 1.0) fires HIGH. Same-day transactions also share an identical `T10:00:00` timestamp, so D5's `(occurred_at, event_id)` ordering is unstable. | `mock_aa.py:101` vs `:163`; live case "Zohaib Hussain" → FRAUD_REVIEW with D5 drift ₹11,163 | Generate transactions first, sort by date, then assign strictly increasing timestamps and compute the running balance in final order | S |
| 2 | P0 | **The seeded book is monotone and self-contradicting.** 10 of 12 personas decide APPROVE_ENHANCED while their names promise stories they don't deliver: "Meera Manipulation Review" is approved-enhanced, "Nila Sparse Evidence" lands in FRAUD_REVIEW (D2 fires because 2 months of history dilutes the 180-day baseline), "Kabir High Risk" declines on affordability, not risk. A judge reading the queue sees a fake-looking wall of identical approvals. | DB query of `decisions` × `applicants`; `seed.py:53-66` (one shared 3-row/month template for all personas) | Rework the persona generator: realistic names, per-persona income/expense profiles, realistic Indian narrations, and differentiated target outcomes (starter, standard, enhanced, decline-risk, coverage-review, fraud-review) | M |
| 3 | P0 | **No one-command reset.** Rehearsal or a mid-demo mistake requires manual SQL or a full volume wipe + migrate + reseed. The seed also force-publishes its hash-embedding catalogue, retiring the live Gemini catalogue — reseeding silently degrades vector classification. | `Makefile` (no reset target); `seed.py:249-257` | `make demo-reset`: truncate tenant data, reseed, tolerate any existing LIVE catalogue; snapshot/restore variant for &lt; 10 s recovery | M |
| 4 | P0 | **Demo endpoint and seed flags are off in `.env`.** `POST /demo/events/income-consistency` 404s and the seed refuses unless flags are exported inline — easy to forget live. | `.env` (no `DEMO_EVENTS_ENABLED` / `DEMO_SEED_ENABLED`) | Add both flags to `.env`; pre-demo checklist verifies with a curl | S |
| 5 | P1 | **Sign-in offers no demo credentials.** Judges see a blank form; presenter types a long role email + strong password by hand (typo risk on stage). | `SignInPage.tsx` (no helper) | Dev-only "demo accounts" panel that pre-fills credentials per role with one click | S |
| 6 | P1 | **The "connect your bank" journey doesn't look like one.** It's a radio card + checkbox form; no bank picker, no fetching theater, no import summary. The words "simulated Account Aggregator" carry the whole story. | `SourceConnect.tsx:89-99`, `ConsentStep.tsx` | Sandbox AA flow: bank picker (initial-avatar tiles), consent panel that mirrors the real consent artefact (purpose/scope/validity), and an import success summary ("N transactions · M months") fed by real ingestion counts | M |
| 7 | P1 | **No demo statement files exist for the upload story.** Test fixtures are 6-row toy CSVs buried in `backend/tests`; nothing tells the fraud story (D5 + D2 + D6) via upload with realistic narrations. | `backend/tests/fixtures/statements/` | `demo/` folder: deterministic generator producing a clean gig CSV, a clean salaried CSV, and a doctored PDF (editor-produced metadata + balance jump + pre-application burst), plus a README mapping file → expected outcome | M |
| 8 | P1 | **Pipeline success is silent.** On completion the page instantly navigates away; the "247 transactions imported · 6 months" moment never lands, and counts are only visible mid-flight. | `IngestPage.tsx:89-93`; `PipelineProgress.tsx` | Success summary banner (ingested count, period, source tier) with a short pause before auto-open, plus an explicit "Open case" action | S |
| 9 | P1 | **Live-narration classification depends on Gemini at ingest time.** The live catalogue is `gemini-v1`; any narration missing keyword rules triggers a network embedding call. Venue Wi-Fi failure → UNCLASSIFIED (honest, but degrades coverage and slows the pipeline). | `merchant_catalog_versions` (live = gemini-embedding-001) | Author all demo narrations to match keyword rules (no network in the happy path); document the offline behaviour in the runbook | S |
| 10 | P1 | **The newly-eligible flip has no rehearsed live target.** Vikram is pre-flipped by the seed (good for showing the view), but firing the demo event live needs a second declined applicant verified to improve. | `seed.py:384-412` | Keep a second decline persona reserved for the live flip; verify the improvement end-to-end and script it in the runbook | S |
| 11 | P2 | Replay divergence table renders raw `JSON.stringify` values. Only visible if a replay DIVERGES, which the demo never shows. | `ReplayPanel.tsx:57-59` | Humanize per-field diffs | S |
| 12 | P2 | No toast system; confirmations are quiet inline text. Existing aria-live regions are honest and accessible — acceptable for the demo. | app-wide | Optional toast provider post-hackathon | M |
| 13 | P2 | Policy Studio hard-refuses mobile viewports ("Desktop required"). Fine for a projector demo. | `PolicyStudioPage` | Graceful read-only mobile view later | L |

## What already works well (don't touch)

- Case file five-tab structure, evidence drawer lineage, ReplayPanel, stale-check
  "re-decide" banner, recourse cards — the money moments all exist and work.
- Queue views with live counts (newly-eligible, fraud-review, …), skeleton loading,
  offline banners, keyboard accessibility, MetricValue/UNCAL labelling.
- Upload accounting (ingested/deduplicated/rejected with reasons) — honest and demo-able.
- Occupation and enum labels are already humanized in the intake form.

## Invariant check

Every fix above preserves the 11 invariants: seeded and uploaded data flow through the
real ingestion → classification → snapshot → assessment → policy path; nothing stubs a
number, and the D5 fix corrects the *simulator's* bookkeeping, not the detector.
