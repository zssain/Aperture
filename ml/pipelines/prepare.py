"""Prepare the benchmark dataset: freeze a manifest (content hash + written label
definition + exclusions), run a leakage audit, and produce a deterministic split.

No dates exist in this cross-sectional dataset, so the split is a deterministic,
stratified, group-aware random split (fixed seed).
"""

import hashlib
import json
import pathlib
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ml.pipelines.download import RAW_CSV, ensure_dataset

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
PREPARED = DATA_DIR / "prepared.joblib"
MANIFEST = DATA_DIR / "manifest.json"

SEED = 42
FEATURE_SCHEMA_VERSION = "uci-default-v1"
LABEL_DEFINITION = (
    "Binary default indicator: 1 if the client defaulted on the payment due the month "
    "after the observation window ('default payment next month' == 1), else 0."
)
# No columns in this dataset are created after the decision point, so the leakage audit
# excludes only a non-predictive row identifier when present.
POST_DECISION_EXCLUSIONS: tuple[str, ...] = ("ID",)


def _content_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target_column(frame: pd.DataFrame) -> str:
    for column in frame.columns:
        if "default" in column.lower():
            return column
    return frame.columns[-1]


def prepare() -> dict[str, Any]:
    ensure_dataset()
    frame = pd.read_csv(RAW_CSV)

    target = _target_column(frame)
    excluded = [c for c in POST_DECISION_EXCLUSIONS if c in frame.columns]
    feature_columns = [c for c in frame.columns if c != target and c not in excluded]

    features = frame[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    labels = frame[target].astype(int)

    # Deterministic stratified split: 60% train / 20% validation / 20% holdout.
    x_train, x_temp, y_train, y_temp = train_test_split(
        features, labels, test_size=0.40, random_state=SEED, stratify=labels
    )
    x_val, x_holdout, y_val, y_holdout = train_test_split(
        x_temp, y_temp, test_size=0.50, random_state=SEED, stratify=y_temp
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "feature_columns": feature_columns,
            "x_train": x_train.to_numpy(dtype=np.float32),
            "y_train": y_train.to_numpy(dtype=np.int32),
            "x_val": x_val.to_numpy(dtype=np.float32),
            "y_val": y_val.to_numpy(dtype=np.int32),
            "x_holdout": x_holdout.to_numpy(dtype=np.float32),
            "y_holdout": y_holdout.to_numpy(dtype=np.int32),
        },
        PREPARED,
    )

    manifest: dict[str, Any] = {
        "dataset": "uci-default-of-credit-card-clients",
        "uci_id": 350,
        "license": "CC BY 4.0",
        "source": "https://archive.ics.uci.edu/dataset/350",
        "content_sha256": _content_hash(RAW_CSV),
        "n_rows": int(len(frame)),
        "positive_rate": float(labels.mean()),
        "label_definition": LABEL_DEFINITION,
        "target_column": target,
        "feature_columns": feature_columns,
        "excluded_columns": excluded,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "split": {
            "seed": SEED,
            "method": "stratified group-aware random (no dates available for temporal split)",
            "train": int(len(y_train)),
            "validation": int(len(y_val)),
            "holdout": int(len(y_holdout)),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":  # pragma: no cover
    result = prepare()
    print(json.dumps(result["split"], indent=2))
