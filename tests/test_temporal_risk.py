import pytest

from src.decision_engine import load_config
from src.models import NetworkInput
from src.risk_model import evaluate_risk_aware_policy
from src.temporal_risk import calculate_effective_risk
from src.threat_trend import STABLE, TRENDING_DOWN, TRENDING_UP


@pytest.fixture
def config():
    return load_config()


def make_input(threat_level: float, device_trust: float) -> NetworkInput:
    return NetworkInput(
        traffic_type="Video Call",
        threat_level=threat_level,
        congestion=1,
        bandwidth_available=100,
        application_priority=10,
        device_trust=device_trust,
        latency=10,
    )


def test_stable_trend_does_not_change_raw_risk(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=4, device_trust=100),
        config,
        previous_smoothed_threat=40,
    )

    assert result.raw_security_risk == 28
    assert result.security_risk == result.raw_security_risk
    assert result.threat_trend == STABLE
    assert result.temporal_adjustment == 0
    assert result.effective_security_risk == result.raw_security_risk
    assert result.risk_budget_status == "SATISFIED"


def test_increasing_trend_adds_configured_adjustment(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=6, device_trust=40),
        config,
        previous_smoothed_threat=40,
    )

    assert result.raw_security_risk == 60
    assert result.threat_trend == TRENDING_UP
    assert result.temporal_adjustment == 10
    assert result.effective_security_risk == 70


def test_decreasing_trend_applies_configured_negative_adjustment(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=8, device_trust=60),
        config,
        previous_smoothed_threat=100,
    )

    assert result.raw_security_risk == 68
    assert result.threat_trend == TRENDING_DOWN
    assert result.temporal_adjustment == -5
    assert result.effective_security_risk == 63
    assert result.risk_budget_status == "SATISFIED"


@pytest.mark.parametrize(
    ("raw_risk", "trend", "expected"),
    [(98, TRENDING_UP, 100), (2, TRENDING_DOWN, 0)],
)
def test_effective_risk_is_clamped(raw_risk, trend, expected, config):
    adjustment, effective = calculate_effective_risk(
        raw_risk,
        trend,
        config["temporal"]["risk_adjustment"],
    )

    assert effective == expected
    assert adjustment == (10 if trend == TRENDING_UP else -5)


def test_effective_risk_above_r_max_violates_budget_and_rejects_ordinary_policies(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=6, device_trust=40),
        config,
        previous_smoothed_threat=40,
    )

    assert result.effective_security_risk == 70
    assert result.r_max == 65
    assert result.risk_budget_status == "VIOLATED"
    assert result.security_constraint_satisfied is False
    assert result.selected_policy == "QUARANTINED"
    assert all(
        not evaluation.admissible
        for evaluation in result.evaluations
        if evaluation.policy != "QUARANTINED"
    )


def test_effective_risk_at_or_below_r_max_keeps_ordinary_policies_eligible(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=8, device_trust=60),
        config,
        previous_smoothed_threat=100,
    )

    assert result.raw_security_risk == 68
    assert result.effective_security_risk == 63
    assert result.risk_budget_status == "SATISFIED"
    assert any(
        evaluation.admissible
        for evaluation in result.evaluations
        if evaluation.policy == "CRITICAL PRIORITY"
    )


def test_temporal_adjustment_explanation_exposes_risk_budget(config):
    result = evaluate_risk_aware_policy(
        make_input(threat_level=6, device_trust=40),
        config,
        previous_smoothed_threat=40,
    )

    assert "Raw security risk is 60.00" in result.explanation
    assert "TRENDING_UP" in result.explanation
    assert "increased risk by 10.00" in result.explanation
    assert "effective security risk 70.00" in result.explanation
    assert "risk budget R_MAX 65.00 is violated" in result.explanation
