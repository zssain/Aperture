# Model card

Registry source: `app.registries.credit_features`. The cash-flow scorecard is
`UNCALIBRATED`; it estimates relative risk inside policy and never acts. Fairness
attributes are monitoring-only. Narration, embeddings, similarity, manipulation findings
and protected attributes are excluded.

Determinism, monotonicity, registry isolation, classification and replay are measured in
CI. Calibration, discrimination, drift and subgroup outcome disparity are **not yet
measured** pending sufficient closed outcomes. Until then every PD is visibly
`UNCALIBRATED` in storage, API and UI.
