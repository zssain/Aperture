import pytest
from app.services.monitoring.calibration import calibration_metrics
from app.services.monitoring.disparity import disparity_metrics
from app.services.monitoring.drift import population_stability_index
from app.services.monitoring.model_card import build_model_card, model_card_pdf
from app.services.monitoring.overrides import override_metrics


def test_zero_outcomes_names_required_sample() -> None:
    result = calibration_metrics([], "Model B")["brier"]
    assert result["status"] == "NOT_YET_MEASURABLE"
    assert "requires 200 closed outcomes; 0 exist" in result["reason"]


def test_subgroup_n_three_is_gated() -> None:
    result = disparity_metrics([("age_band", "18-25", 0)] * 3)
    metric = result["age_band"]["18-25"]
    assert metric.status == "INSUFFICIENT_SAMPLE"
    assert metric.value is None


def test_psi_fixture() -> None:
    assert population_stability_index([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0)
    assert population_stability_index([0.8, 0.2], [0.5, 0.5]) > 0


def test_override_counts_match_rows_without_outcomes() -> None:
    result = override_metrics([("POLICY_EXCEPTION", "A"), ("POLICY_EXCEPTION", "B")], 10)
    assert result["by_reason"] == {"POLICY_EXCEPTION": 2}
    assert result["rate"]["value"] == pytest.approx(0.2)


def test_model_card_lists_unmeasured_metrics_and_exports_pdf() -> None:
    card = build_model_card(
        ["income_months_observed"],
        {"calibration": calibration_metrics([], "Model B")["brier"]},
    )
    assert card["not_yet_measured"][0]["metric"] == "calibration"
    assert "requires 200 closed outcomes" in card["not_yet_measured"][0]["reason"]
    assert model_card_pdf(card).startswith(b"%PDF-1.4")
