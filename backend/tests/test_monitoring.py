import pytest
from app.services.monitoring.calibration import calibration_metrics
from app.services.monitoring.disparity import disparity_metrics
from app.services.monitoring.drift import population_stability_index, score_bins
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


def test_score_bins_are_proportions() -> None:
    bins = score_bins([0.05, 0.15, 0.15, 0.95])
    assert len(bins) == 10
    assert bins[0] == pytest.approx(0.25)
    assert bins[1] == pytest.approx(0.5)
    assert bins[9] == pytest.approx(0.25)
    assert sum(bins) == pytest.approx(1.0)


def test_score_bins_empty_is_all_zero() -> None:
    assert score_bins([]) == [0.0] * 10


def test_score_drift_measures_a_real_shift() -> None:
    reference = score_bins([0.05] * 100)
    recent = score_bins([0.75] * 100)
    assert population_stability_index(recent, reference) > 0.2
    assert population_stability_index(reference, reference) == pytest.approx(0)


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


def test_model_card_pdf_is_a_valid_multi_line_document() -> None:
    # A long feature list forces the layout across many wrapped lines; the export must be a
    # laid-out, paginated document (a real xref + multiple text runs), not a single JSON line.
    card = build_model_card(
        [f"feature_{i}_paise" for i in range(120)],
        {
            "calibration": {"status": "MEASURED", "value": 0.16, "ci_low": 0.11,
                            "ci_high": 0.21, "n": 240, "minimum_n": 200},
            "drift": {"status": "MEASURED", "value": 0.1, "n": 253, "minimum_n": 100},
        },
    )
    pdf = model_card_pdf(card)
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"\nxref\n" in pdf and b"startxref" in pdf
    assert pdf.count(b" Tj") > 10  # many positioned text runs, not one overflowing line
    assert pdf.count(b"/Type /Page ") >= 1
