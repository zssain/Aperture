"""Train the benchmark PD model (Model A).

Pipeline: LR baseline (saved & reported) -> XGBoost (fixed seed, early stopping on the
validation set) -> isotonic calibration fitted on the VALIDATION set (disjoint from the
XGBoost training set) -> evaluate on the holdout -> write the artifact, a metrics JSON,
and a registry entry (with the artifact's SHA-256).

Reproducible: fixed seed, single-threaded fit.
"""

import hashlib
import json
import pathlib
from typing import Any

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ml.pipelines.evaluate import evaluate_scores
from ml.pipelines.prepare import MANIFEST, PREPARED, prepare
from ml.scorecard.cashflow_scorecard_v1 import (
    CALIBRATION_STATUS as SCORECARD_CALIBRATION,
)
from ml.scorecard.cashflow_scorecard_v1 import (
    FEATURE_SCHEMA_VERSION as SCORECARD_SCHEMA,
)
from ml.scorecard.cashflow_scorecard_v1 import (
    SCORECARD_VERSION,
    scorecard_fingerprint,
)

SEED = 42
ARTIFACT_DIR = pathlib.Path(__file__).resolve().parents[1] / "artifacts"
ARTIFACT = ARTIFACT_DIR / "benchmark_v1.joblib"
METRICS = ARTIFACT_DIR / "benchmark_v1.metrics.json"
REGISTRY = ARTIFACT_DIR / "registry.json"

BENCHMARK_VERSION = "benchmark-v1"
BENCHMARK_SCHEMA = "uci-default-v1"


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train() -> dict[str, Any]:
    if not PREPARED.exists():
        prepare()
    data = joblib.load(PREPARED)
    manifest = json.loads(MANIFEST.read_text())

    x_train, y_train = data["x_train"], data["y_train"]
    x_val, y_val = data["x_val"], data["y_val"]
    x_holdout, y_holdout = data["x_holdout"], data["y_holdout"]

    # --- Logistic Regression baseline (standardised) ---
    scaler = StandardScaler().fit(x_train)
    lr = LogisticRegression(max_iter=1000, random_state=SEED)
    lr.fit(scaler.transform(x_train), y_train)
    lr_holdout = lr.predict_proba(scaler.transform(x_holdout))[:, 1]
    lr_metrics = evaluate_scores(y_holdout, lr_holdout)

    # --- XGBoost (fixed seed, early stopping on validation) ---
    xgb = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        eval_metric="logloss",
        early_stopping_rounds=30,
        tree_method="hist",
        n_jobs=1,
        random_state=SEED,
    )
    xgb.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)

    # --- Isotonic calibration fitted on the VALIDATION set (disjoint from training) ---
    raw_val = xgb.predict_proba(x_val)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_val, y_val)

    raw_holdout = xgb.predict_proba(x_holdout)[:, 1]
    calibrated_holdout = calibrator.transform(raw_holdout)
    xgb_metrics = evaluate_scores(y_holdout, np.asarray(calibrated_holdout, dtype=np.float64))

    # --- Persist the artifact ---
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model_version": BENCHMARK_VERSION,
            "feature_schema_version": BENCHMARK_SCHEMA,
            "feature_columns": data["feature_columns"],
            "booster": xgb,
            "calibrator": calibrator,
            "lr_baseline": lr,
            "lr_scaler": scaler,
            "manifest_content_sha256": manifest["content_sha256"],
            "seed": SEED,
        },
        ARTIFACT,
    )

    metrics_report: dict[str, Any] = {
        "model_version": BENCHMARK_VERSION,
        "dataset_manifest_sha256": manifest["content_sha256"],
        "seed": SEED,
        "n_train": int(len(y_train)),
        "n_validation": int(len(y_val)),
        "n_holdout": int(len(y_holdout)),
        "calibration": {
            "method": "isotonic",
            "fitted_on": "validation",
            "disjoint_from_training": True,
            "n_calibration": int(len(y_val)),
        },
        "logistic_regression_baseline": lr_metrics,
        "xgboost_calibrated": xgb_metrics,
        "population_note": (
            "These metrics describe the UCI credit-card population. They do NOT apply "
            "to this product's thin-file cash-flow population."
        ),
    }
    METRICS.write_text(json.dumps(metrics_report, indent=2))

    _write_registry()
    return metrics_report


def _write_registry() -> None:
    registry = {
        "models": {
            BENCHMARK_VERSION: {
                "kind": "benchmark",
                "artifact_path": str(ARTIFACT.relative_to(ARTIFACT_DIR.parents[1])),
                "artifact_sha256": _sha256(ARTIFACT),
                "feature_schema_version": BENCHMARK_SCHEMA,
                "calibration_status": "CALIBRATED",
                "metrics_path": str(METRICS.relative_to(ARTIFACT_DIR.parents[1])),
            },
            SCORECARD_VERSION: {
                "kind": "scorecard",
                "artifact_path": "ml/scorecard/cashflow_scorecard_v1.py",
                "artifact_sha256": scorecard_fingerprint(),
                "feature_schema_version": SCORECARD_SCHEMA,
                "calibration_status": SCORECARD_CALIBRATION,
            },
        }
    }
    REGISTRY.write_text(json.dumps(registry, indent=2))


if __name__ == "__main__":  # pragma: no cover
    report = train()
    print(json.dumps({
        "lr_roc_auc": report["logistic_regression_baseline"]["roc_auc"],
        "xgb_roc_auc": report["xgboost_calibrated"]["roc_auc"],
        "xgb_brier": report["xgboost_calibrated"]["brier"],
    }, indent=2))
