"""Attribution: exact closed-form for the additive scorecard (Model B); TreeSHAP
(xgboost's native ``pred_contribs``) for the benchmark (Model A).

We deliberately do NOT approximate the scorecard's exact contributions with SHAP.
"""

from typing import Any

from numpy.typing import NDArray


def additive_contributions(scorecard_output: Any) -> list[tuple[str, float]]:
    """Exact log-odds contribution per present feature, from the scorecard output."""
    return [
        (contribution.feature, float(contribution.contribution))
        for contribution in scorecard_output.contributions
        if contribution.present
    ]


def treeshap_contributions(
    booster: Any, feature_row: NDArray[Any], feature_names: list[str]
) -> list[tuple[str, float]]:
    """Exact TreeSHAP contributions for one row (log-odds), excluding the bias term."""
    import numpy as np
    import xgboost as xgb

    matrix = xgb.DMatrix(
        np.asarray(feature_row, dtype=np.float32).reshape(1, -1),
        feature_names=feature_names,
    )
    contributions = booster.get_booster().predict(matrix, pred_contribs=True)[0]
    # The last column is the bias/base value; drop it.
    return [
        (name, float(value)) for name, value in zip(feature_names, contributions[:-1], strict=True)
    ]
