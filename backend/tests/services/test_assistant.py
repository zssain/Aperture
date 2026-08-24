"""Grounding + egress guarantees for the two AI assistants.

These are the properties the demo leans on: the architecture map only ever cites files that
really exist (no hallucinated paths), the decision explainer degrades to a truthful summary
without an LLM, and the shared egress guard lets grounded assistant payloads through while
still blocking raw ledger/PII fields at any nesting depth.
"""

from pathlib import Path

import pytest
from app.core.providers.base import ProviderResponseError, assert_llm_payload_safe
from app.services.assistant.architecture import (
    ARCHITECTURE,
    _candidates,
    _fallback,
    _score,
)
from app.services.assistant.decision_explainer import (
    _deterministic_answer,
    _top_contributions,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_every_architecture_path_is_real() -> None:
    """The map must never cite a file that does not exist — that is the whole point."""
    missing: list[str] = []
    for topic in ARCHITECTURE:
        for path in topic.paths:
            if not (REPO_ROOT / path).exists():
                missing.append(f"{topic.key}: {path}")
    assert not missing, f"architecture map references missing paths: {missing}"


def test_architecture_topic_keys_are_unique() -> None:
    keys = [t.key for t in ARCHITECTURE]
    assert len(keys) == len(set(keys))


def test_candidates_rank_relevant_topic_first() -> None:
    candidates = _candidates("where is the fraud manipulation detector code?")
    assert candidates[0].key == "manipulation"


def test_fallback_is_grounded_and_marked_deterministic() -> None:
    answer = _fallback(_candidates("how does the policy engine decide?"))
    assert answer.used_llm is False
    assert answer.citations
    # Every cited path resolves to a real file.
    for citation in answer.citations:
        for path in citation.paths:
            assert (REPO_ROOT / path).exists()


def test_score_rewards_keyword_hits() -> None:
    risk = next(t for t in ARCHITECTURE if t.key == "risk")
    assert _score(risk, "explain the scorecard and probability of default") > 0
    assert _score(risk, "unrelated question about lunch") == 0


def test_deterministic_answer_names_rule_and_pd() -> None:
    facts = {
        "outcome": "DECLINE",
        "decisive_rule": "pd_decline (DECLINE)",
        "risk": {
            "pd": 0.417,
            "calibration": "uncalibrated",
            "top_factors": [
                {"feature": "monthly_inflow_cv", "direction": "PD_UP", "contribution": 0.4},
            ],
        },
        "affordability": {"status": "PASS", "headroom": "₹12,000"},
        "coverage": {"score": 72, "band": "MODERATE"},
    }
    answer = _deterministic_answer(facts)
    assert "DECLINE" in answer
    assert "pd_decline" in answer
    assert "0.417" in answer
    assert "uncalibrated" in answer


def test_deterministic_answer_handles_no_decision() -> None:
    assert "No decision" in _deterministic_answer({})


def test_top_contributions_orders_by_absolute_value_and_skips_absent() -> None:
    payload = {
        "contributions": [
            {"feature": "a", "contribution": 0.1, "present": True},
            {"feature": "b", "contribution": -0.9, "present": True},
            {"feature": "c", "contribution": 5.0, "present": False},
        ]
    }
    top = _top_contributions(payload, limit=2)
    assert [c["feature"] for c in top] == ["b", "a"]


def test_egress_guard_allows_grounded_assistant_payloads() -> None:
    # Decision-explainer shape.
    assert_llm_payload_safe(
        {
            "question": "why declined?",
            "facts": {
                "outcome": "DECLINE",
                "risk": {"pd": 0.4, "top_factors": [{"feature": "x", "contribution": 0.1}]},
                "recourse": ["Add three months of salary evidence"],
            },
        }
    )
    # Architecture shape.
    assert_llm_payload_safe(
        {
            "question": "where is risk?",
            "candidates": [{"key": "risk", "paths": ["backend/app/services/risk/service.py"]}],
        }
    )


def test_egress_guard_blocks_forbidden_field_at_any_depth() -> None:
    with pytest.raises(ProviderResponseError):
        assert_llm_payload_safe({"outcome": "DECLINE", "normalized_narration": "private"})
    with pytest.raises(ProviderResponseError):
        assert_llm_payload_safe({"facts": {"ledger": [{"counterparty": "ACME"}]}})
    with pytest.raises(ProviderResponseError):
        assert_llm_payload_safe({"rows": [{"embedding": [0.1, 0.2]}]})


def test_egress_guard_keeps_notice_applicant_name() -> None:
    # A decision notice must be able to address the applicant by name.
    assert_llm_payload_safe({"applicant_display_name": "Asha Pawar", "outcome": "APPROVE"})
