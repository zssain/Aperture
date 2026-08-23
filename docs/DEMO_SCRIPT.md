# Demo walkthrough

For the full rehearsed 3-minute script, pre-demo checklist, measured timings and the
failure playbook, see **[DEMO_RUNBOOK.md](DEMO_RUNBOOK.md)**. The demo kit (seeded
personas, statement files, one-command reset) is documented in
**[../demo/README.md](../demo/README.md)**.

Quick version:

1. `make demo-reset` (~4.4 s); `make dev` (API + worker + SPA). Sign in with the
   **Credit analyst** demo button on `/signin`.
2. **Queue** → show the differentiated book (enhanced/standard/starter approvals, a risk
   decline, an evidence referral, a fraud referral) with honest UNCAL PD chips.
3. **Meera Joshi** → **Verification** → D5 balance-jump and D2 inflow-burst findings,
   each citing exact transactions (fraud logic is independent of the risk score).
4. **Ingest** → connect-a-bank flow: bank picker → consent artefact panel → fetching →
   import summary. The case opens itself with a real decision.
5. **Assessment** → click any number → evidence drawer shows formula, version and the
   exact events behind it.
6. `make demo-flip` → **Kabir Shaikh** re-decides DECLINE→APPROVE; find him in the
   queue's **Newly eligible** view with the change explanation.
7. As auditor, **Decision & Audit** → **Replay** → `IDENTICAL` with matching hashes
   (~30 ms).
8. (Optional) As policy owner, simulate v2 in Policy Studio, inspect diffs, publish.
