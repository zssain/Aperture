# APERTURE — ML (benchmark model + cash-flow scorecard)

## Why there are two models (read this first)

**No public dataset links Indian cash-flow evidence to loan outcomes.** The model that
scores this product's actual feature space therefore *cannot be trained yet*. Training
XGBoost on a foreign dataset and then displaying explanations for features that dataset
does not contain would be fabrication. Instead:

- **Model A — benchmark.** An honestly trained, calibrated PD model on a public labelled
  dataset. Its metrics describe *that* population and are **not** claimed to apply to this
  product's thin-file population.
- **Model B — cash-flow scorecard.** A transparent additive points model over the
  features the product actually observes, published in full and marked **UNCALIBRATED**
  everywhere (DB, API, UI). It has **no accuracy claim** — there is no outcome data yet.
  Real calibration is earned over time as outcomes arrive (Prompts 09 and 15).

## Model A dataset provenance

- **Dataset:** UCI *Default of Credit Card Clients* (`id=350`).
- **License:** CC BY 4.0 — direct download, no competition sign-in.
- **Source:** https://archive.ics.uci.edu/dataset/350
- **Label definition:** binary default indicator — `1` if the client defaulted on the
  payment due the month after the observation window (`default payment next month == 1`),
  else `0`.
- **Leakage audit:** this cross-sectional dataset contains no columns created after the
  decision point; only a non-predictive row identifier (`ID`) is excluded. Exclusions are
  recorded in `ml/data/manifest.json`.
- **Split:** deterministic, stratified, group-aware random split (seed 42) — 60% train /
  20% validation / 20% holdout (no dates exist for a temporal split).
- **Calibration:** isotonic, fitted on the **validation** set (disjoint from the XGBoost
  training set), evaluated on the holdout.

Home Credit Default Risk is an optional upgrade behind `APERTURE_DATASET=home_credit`
and is intentionally not wired up, so the build never blocks on Kaggle credentials.

## Reproduce

```bash
# from the repo root, using the backend venv (xgboost needs libomp: `brew install libomp`)
./backend/.venv/bin/python -m ml.pipelines.train_benchmark
```

Writes: `ml/data/` (raw + manifest + splits), `ml/artifacts/benchmark_v1.joblib`,
`ml/artifacts/benchmark_v1.metrics.json` (measured metrics with bootstrap CIs + the
dataset manifest hash), and `ml/artifacts/registry.json` (SHA-256 of every artifact).

**Datasets and artifacts are never committed** (`ml/data/.gitignore`,
`ml/artifacts/.gitignore`). The backend registry refuses to load a model whose artifact
hash does not match the registry.

## Model B is published in full

Every scorecard weight, transform and monotonic direction — with a written rationale —
is in `ml/scorecard/cashflow_scorecard_v1.py`. Contributions are exact and closed-form;
SHAP is deliberately not used on the additive model.
