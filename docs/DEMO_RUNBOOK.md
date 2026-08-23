# Aperture — 3-minute demo runbook

Everything below was rehearsed against the live local stack. Timings are **measured**,
not estimated (local M-series Mac, warm Postgres). The demo is deterministic: the same
reset produces the same book every time.

---

## Pre-demo checklist (do this once, ~2 min before)

1. **Services up**
   ```bash
   make up          # Postgres (idempotent; skip if already running)
   make dev         # API :8000 + job worker + SPA :5173  ← the worker matters
   ```
   Confirm: `curl -s localhost:8000/api/v1/health` → `{"status":"ok"}`, SPA at
   http://localhost:5173.

   > The worker is now part of `make dev`. If you start pieces by hand, **you must run
   > `python -m app.worker`** — connect/upload/redecision all run as jobs. A stale
   > worker (old code) is the one thing that will silently ruin the demo; if in doubt,
   > kill all `app.worker` processes and let `make dev` own it.

2. **Flags** — `.env` already has `DEMO_SEED_ENABLED=true` and
   `DEMO_EVENTS_ENABLED=true`. `ENVIRONMENT=development`.

3. **Reset the book** (measured: **~4.4 s** total, budget is 30 s)
   ```bash
   make demo-reset
   ```
   Reseeds 12 personas + regenerates `demo/statements/`. Run this immediately before
   presenting, and again to recover from any mistake mid-demo.

3b. **Preflight the live path** (measured: **~1 s**)
   ```bash
   make demo-check
   ```
   Runs a real connect through the worker and asserts the decision is verification
   **CLEAR** — proving the worker is up and running *current* code. This is the guard
   for the demo's biggest risk: a stale worker still routes every connect to
   FRAUD_REVIEW. If this fails, restart `make dev` and kill any old `app.worker`
   processes, then re-run. (Leaves a probe applicant; the next `make demo-reset`
   clears it, so run reset once more before presenting.)

4. **Browser tabs, opened in this order** (all http://localhost:5173):
   - Tab 1 — `/signin` (use the **Credit analyst** demo button)
   - Tab 2 — `/queue` (leave on **All decisions**)
   - Tab 3 — `/cases/<Meera's id>` on the **Verification** tab (the fraud story)
   - Tab 4 — `/cases/<Kabir's id>` (the live-flip target, seeded DECLINE_RISK)
   - Tab 5 — `/ingest` (the connect-your-bank flow)

   Grab the two case ids after reset:
   ```bash
   make demo-ids     # prints Meera + Kabir application ids and URLs
   ```
   *(If you didn't add that helper, read them from the queue rows.)*

5. **Zoom** the browser to ~110–125% for projector legibility.

### Measured timings (so you know what "normal" looks like)

| Action | Measured |
|---|---|
| Sign in | ~100 ms |
| Queue load | ~180 ms |
| Case file load | ~170 ms |
| Connect-bank pipeline (fetch→decide) | ~2 s |
| Upload PDF pipeline | ~1.5 s |
| Replay (IDENTICAL) | ~30 ms |
| Live newly-eligible flip (`make demo-flip`) | ~8 s |
| Full `make demo-reset` | ~4.4 s |

---

## The 3-minute script (beat by beat)

**[0:00–0:20] The problem & the queue.** Start on Tab 2 (`/queue`, All decisions).
> "Aperture decides credit for people bureaus can't score — thin-file, new-to-credit.
> Here's a real book of decisions. Notice they're *different*: enhanced approvals,
> starter approvals, a risk decline, an evidence referral, a fraud referral. Every one
> is reproducible and fully traced."

Point at the columns: recommendation, PD (grey **UNCAL** chip — "we never dress an
uncalibrated score up as green"), coverage, verification band.

**[0:20–1:00] The fraud story.** Click Meera Joshi → or switch to Tab 3
(**Verification** tab).
> "Meera's statement looks like a clean salary account. But the system caught two
> things." Point to the D5 finding: "the running balance stops adding up — a hand-edit."
> Then D2: "and a burst of large transfers right before she applied."

Click a finding → it cites the **exact transactions**. 
> "This isn't a risk score guessing. Fraud detection never even sees the risk model —
> they're independent by construction. She's routed to a fraud reviewer."

**[1:00–1:40] Connect a bank, live.** Switch to Tab 5 (`/ingest`).
> "Let's onboard someone new." Fill the short form (name, ref, amounts). Choose
> **Connect financial accounts** → the **bank picker** appears. Pick HDFC.
> "This is the Account Aggregator sandbox — consented data, not an upload."

Show the **consent panel**: "This is exactly what the applicant approves — purpose,
scope, validity — and we hash those exact terms." Tick consent → **Connect and start
pipeline**. Watch the stages tick, then the **import summary**:
> "247-odd transactions, six months, AA-verified — and it's already decided." The case
> opens itself.

**[1:40–2:20] Trace one number.** On the new case → **Assessment** tab. Click any
feature value (e.g. median monthly inflow) → the **evidence drawer** opens.
> "Every displayed number is traceable: here's the formula, the window, the version,
> and the exact ledger events that produced it. If it can't be traced, we don't show
> it."

**[2:20–2:45] The newly-eligible flip.** Switch to Tab 4 (Kabir, DECLINE_RISK). In a
terminal:
```bash
make demo-flip
```
> "Kabir was declined — thin, volatile income. Now verified income lands." (~8 s.)
Refresh his case → the **new-events banner**; go to queue → **Newly eligible** view →
Kabir, with the change explanation and the features that moved.
> "The decision re-runs itself the moment the evidence changes."

**[2:45–3:00] Prove it's real — replay.** Open any decided case → **Decision & Audit**
→ **Replay**. (Sign in as Auditor if showing read-only.)
> "An auditor can replay any past decision. Same inputs, same policy version —
> byte-identical." Result: **IDENTICAL** with matching hashes, in ~30 ms.
> "That's the whole promise: every decision is honest, traceable, and reproducible
> forever."

---

## Failure playbook (what to do when something breaks live)

| If this breaks… | Do this |
|---|---|
| **Connect pipeline hangs / errors** | Don't wait. Switch to Tab 3/4 — the seeded book already shows every outcome. "Here's one we prepared." The seeded personas tell the same stories without live ingestion. |
| **Worker is down** (jobs stay PENDING) | New terminal: `cd backend && uv run python -m app.worker`. Meanwhile narrate off the seeded cases. This is the most likely failure — check the worker first. |
| **`make demo-flip` doesn't flip** | Kabir is only flippable once per reset. The script now detects this and prints "already approved — run `make demo-reset` to re-arm". Either reset, or show his already-superseded DECLINE→APPROVE pair on his case, or point at pre-flipped Vikram Rao in Newly eligible. |
| **Upload rejected** | Use `demo/statements/` files (regenerated by every reset) — they're verified to parse. Never hand-pick a random CSV live. |
| **Venue Wi-Fi down** | Everything is local — no internet needed. The only external dependency is Gemini embeddings for *novel* narrations; demo narrations all match keyword rules, so classification runs offline. Vector misses degrade to UNCLASSIFIED, never an error. |
| **Anything feels wrong** | `make demo-reset` (~4.4 s) restores the exact known state. Rehearse this reflex. |
| **Signed out unexpectedly** | The sign-in page has one-click demo-account buttons (dev builds only). |

---

## After the demo

`make demo-reset` leaves a clean book for the next run. Nothing here touches production
paths or external services.
