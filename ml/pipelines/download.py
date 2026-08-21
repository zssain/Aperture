"""Download the benchmark dataset.

Default path: UCI "Default of Credit Card Clients" (CC BY 4.0), a direct download with
no competition sign-in. Home Credit Default Risk is an optional upgrade behind
``APERTURE_DATASET=home_credit`` and is intentionally NOT implemented here so the build
never blocks on Kaggle credentials.

Datasets are never committed (see ml/data/.gitignore).
"""

import os
import pathlib

import pandas as pd

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
RAW_CSV = DATA_DIR / "uci_default_of_credit_card_clients.csv"
UCI_DATASET_ID = 350


def download_uci() -> pathlib.Path:
    """Fetch the UCI dataset into ml/data/ (idempotent — skips if already present)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_CSV.exists():
        return RAW_CSV

    from ucimlrepo import fetch_ucirepo  # imported lazily (training-only dependency)

    dataset = fetch_ucirepo(id=UCI_DATASET_ID)
    features = dataset.data.features
    targets = dataset.data.targets
    frame = pd.concat([features, targets], axis=1)
    frame.to_csv(RAW_CSV, index=False)
    return RAW_CSV


def ensure_dataset() -> pathlib.Path:
    dataset = os.environ.get("APERTURE_DATASET", "uci")
    if dataset == "uci":
        return download_uci()
    raise NotImplementedError(
        f"dataset {dataset!r} is not wired up; the UCI path is the supported default"
    )


if __name__ == "__main__":  # pragma: no cover
    path = ensure_dataset()
    print(f"dataset ready at {path}")
