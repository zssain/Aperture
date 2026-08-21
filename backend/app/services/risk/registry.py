"""Risk model registry: load artifacts once, verify their SHA-256 against the recorded
hash, and cache in memory. A hash mismatch (a silently swapped model) is fatal.

The benchmark (Model A) is a joblib artifact; the cash-flow scorecard (Model B) is the
published Python module, verified against the fingerprint recorded at registration.
"""

import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.scorecard import cashflow_scorecard_v1 as scorecard  # noqa: E402

REGISTRY_PATH = _REPO_ROOT / "ml" / "artifacts" / "registry.json"


class RegistryError(Exception):
    """The registry is inconsistent — never fall back, never fabricate a score."""


@dataclass(frozen=True)
class BenchmarkModel:
    model_version: str
    feature_schema_version: str
    feature_columns: list[str]
    booster: Any  # xgboost.XGBClassifier
    calibrator: Any  # sklearn IsotonicRegression
    calibration_status: str


@dataclass(frozen=True)
class ScorecardModel:
    model_version: str
    feature_schema_version: str
    feature_order: tuple[str, ...]
    calibration_status: str
    module: Any  # ml.scorecard.cashflow_scorecard_v1


@dataclass(frozen=True)
class LoadedRegistry:
    benchmark: BenchmarkModel | None
    scorecard: ScorecardModel


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(registry_path: pathlib.Path = REGISTRY_PATH) -> LoadedRegistry:
    """Load + hash-verify every referenced artifact. Raises on any mismatch/absence."""
    if not registry_path.exists():
        raise RegistryError(
            f"model registry not found at {registry_path}; run "
            "`python -m ml.pipelines.train_benchmark` to build the artifacts"
        )
    manifest = json.loads(registry_path.read_text())
    models: dict[str, dict[str, Any]] = manifest["models"]

    # --- Scorecard (Model B): verify the published weights fingerprint ---
    scorecard_entry = _find(models, "scorecard")
    live_fingerprint = scorecard.scorecard_fingerprint()
    if live_fingerprint != scorecard_entry["artifact_sha256"]:
        raise RegistryError(
            "cash-flow scorecard fingerprint does not match the registry "
            f"({live_fingerprint} != {scorecard_entry['artifact_sha256']}); "
            "the scorecard was changed without re-registration"
        )
    scorecard_model = ScorecardModel(
        model_version=scorecard.SCORECARD_VERSION,
        feature_schema_version=scorecard.FEATURE_SCHEMA_VERSION,
        feature_order=scorecard.FEATURE_ORDER,
        calibration_status=scorecard.CALIBRATION_STATUS,
        module=scorecard,
    )

    # --- Benchmark (Model A): verify the artifact file hash, then load ---
    benchmark_model: BenchmarkModel | None = None
    benchmark_entry = _find_optional(models, "benchmark")
    if benchmark_entry is not None:
        artifact_path = _REPO_ROOT / benchmark_entry["artifact_path"]
        if not artifact_path.exists():
            raise RegistryError(f"benchmark artifact missing: {artifact_path}")
        actual = _sha256_file(artifact_path)
        if actual != benchmark_entry["artifact_sha256"]:
            raise RegistryError(
                f"benchmark artifact hash mismatch for {artifact_path} "
                f"({actual} != {benchmark_entry['artifact_sha256']})"
            )
        import joblib

        payload = joblib.load(artifact_path)
        benchmark_model = BenchmarkModel(
            model_version=payload["model_version"],
            feature_schema_version=payload["feature_schema_version"],
            feature_columns=list(payload["feature_columns"]),
            booster=payload["booster"],
            calibrator=payload["calibrator"],
            calibration_status=benchmark_entry["calibration_status"],
        )

    return LoadedRegistry(benchmark=benchmark_model, scorecard=scorecard_model)


def _find(models: dict[str, dict[str, Any]], kind: str) -> dict[str, Any]:
    entry = _find_optional(models, kind)
    if entry is None:
        raise RegistryError(f"registry has no {kind!r} model")
    return entry


def _find_optional(models: dict[str, dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for entry in models.values():
        if entry.get("kind") == kind:
            return entry
    return None


_CACHE: LoadedRegistry | None = None


def get_registry() -> LoadedRegistry:
    """Load once, cache in memory (never per request)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_registry()
    return _CACHE


def reset_cache() -> None:
    """Test hook: drop the cached registry."""
    global _CACHE
    _CACHE = None
