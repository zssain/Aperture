# Aperture demo kit

Everything here is sandbox data, generated deterministically from the same persona
scripts the demo seed uses (`backend/app/services/demo/personas.py`). Every file flows
through the REAL pipeline — parser, classifier, feature snapshot, four assessments,
policy engine. Nothing is stubbed and no number is fabricated.

## One-command reset

```bash
make demo-reset        # wipe + reseed the full demo book (~3 s) and regenerate files
```

Sign-in accounts (all use the password printed by the reset):

| Email | Role |
|---|---|
| credit-analyst@demo.aperture.test | Works the queue |
| credit-policy-owner@demo.aperture.test | Policy Studio + health |
| fraud-reviewer@demo.aperture.test | Fraud queue |
| auditor@demo.aperture.test | Read-only + replay |

## The seeded book (what the queue shows after reset)

| Ref | Name | Story | Decision |
|---|---|---|---|
| APL-1093 | Asha Pawar | Gig driver, 7 mo irregular platform income, rent/phone always paid, one missed power bill | APPROVE_STARTER |
| APL-1104 | Ravi Menon | Salaried, clean payroll, only a 2-mo uploaded statement | APPROVE_STARTER + recourse "add a verified source → Standard" |
| APL-1088 | Meera Joshi | Doctored statement: balance jump (D5) + pre-application transfer burst (D2) | FRAUD_REVIEW |
| APL-1076 | Kabir Shaikh | Shrinking volatile settlements, thin cash cover | DECLINE_RISK — the live newly-eligible flip target |
| APL-1112 | Nila Reddy | Declared salaried but only family transfers visible | REVIEW_EVIDENCE (evidence needed) |
| APL-1067 | Arjun Mehta | Commission salary, one missed bill | APPROVE_STANDARD |
| APL-1055 | Fatima Khan | Strong everything, asks ₹2.5 L (above review ceiling) | APPROVE_ENHANCED → human (rule 10) |
| APL-1081 | Dev Patel | Lumpy wholesale settlements | APPROVE_STANDARD |
| APL-1049 | Leela Nair | Modest salary, flawless utility/telecom streaks | APPROVE_ENHANCED |
| APL-1120 | Mohan Iyer | 4-mo urban-services gig history | APPROVE_STARTER |
| APL-1130 | Sara D'Souza | Part-time salary + swinging freelance payouts | APPROVE_STANDARD |
| APL-1042 | Vikram Rao | Asked far beyond cash flow → declined, then verified income arrived | DECLINE_AFFORDABILITY superseded by APPROVE_ENHANCED (newly eligible) |

## Statement files (`demo/statements/`)

Regenerate any time with `make demo-statements` (dates are anchored to today).

| File | Upload it as | What happens |
|---|---|---|
| `asha_gig_driver.csv` | New applicant, occupation Gig worker | Classifies via keyword rules (Swiggy/Zomato/Rapido payouts, BESCOM, Airtel), approves at the starter band |
| `ravi_salaried_thin.csv` | New applicant, Salaried | Bank-export style Withdrawal/Deposit columns, no balance column — thin coverage, starter + recourse |
| `fatima_clean.pdf` | New applicant, Salaried | Clean PDF statement, parses and approves |
| `meera_tampered.pdf` | New applicant, Salaried | **The fraud story**: editor-produced metadata (D6), a running-balance jump (D5), a pre-application inflow burst (D2) → FRAUD_REVIEW with findings citing the exact transactions |

Upload outcomes are decided by the live engines and may differ in band from the seeded
twins (uploads carry the lower DECLARED_DOCUMENT evidence tier — that difference is
itself demo-able on the Evidence tab).

## The live "newly eligible" flip

Kabir (APL-1076) is seeded as DECLINE_RISK. Fire six months of verified business
income at him and the system re-decides:

```bash
make demo-flip        # → fires the events, waits for the redecision job
```

Requires `DEMO_EVENTS_ENABLED=true` (set in `.env`) and the worker running
(`make dev` starts one). If Kabir's case is open in a browser tab, the "new events"
banner appears; the queue's **Newly eligible** view then picks him up with the change
explanation and the driving features.
