import pytest

from src.decision_engine import load_config
from src.models import NetworkInput
from src.risk_model import (
    calculate_security_risk,
    evaluate_risk_aware_policy,
)


@pytest.fixture
def risk_config():
    return load_config()


def make_input(
    threat_level: float,
    device_trust: float,
    *,
    traffic_type: str = "Video Call",
    congestion: float = 1,
    bandwidth_available: float = 100,
    application_priority: float = 10,
    latency: float = 10,
) -> NetworkInput:
    return NetworkInput(
        traffic_type=traffic_type,
        threat_level=threat_level,
        congestion=congestion,
        bandwidth_available=bandwidth_available,
        application_priority=application_priority,
        device_trust=device_trust,
        latency=latency,
    )


def test_low_threat_and_high_trust_produce_low_risk_and_allow_best_policy(risk_config):
    result = evaluate_risk_aware_policy(make_input(1, 95), risk_config)

    assert result.security_risk == 8.5
    assert result.security_constraint_satisfied is True
    assert result.selected_policy == "CRITICAL PRIORITY"
    assert result.qos_utility > 85
    assert "within R_MAX" in result.reason


def test_medium_threat_and_medium_trust_use_weighted_risk_formula():
    risk = calculate_security_risk(
        threat_level=5,
        device_trust=50,
        risk_weights={"threat": 0.70, "untrusted_device": 0.30},
    )

    assert risk == 50


def test_high_threat_and_low_trust_select_quarantine_fallback(risk_config):
    result = evaluate_risk_aware_policy(make_input(10, 0), risk_config)

    assert result.security_risk == 100
    assert result.selected_policy == "QUARANTINED"
    assert result.security_constraint_satisfied is False
    assert "exceeds R_MAX" in result.reason
    assert all(
        not evaluation.admissible
        for evaluation in result.evaluations
        if evaluation.policy != "QUARANTINED"
    )


def test_high_qos_candidate_is_rejected_when_risk_exceeds_constraint(risk_config):
    result = evaluate_risk_aware_policy(make_input(8, 60), risk_config)

    critical = next(
        item for item in result.evaluations if item.policy == "CRITICAL PRIORITY"
    )
    assert result.qos_utility > 85
    assert result.security_risk == 68
    assert critical.admissible is False
    assert critical.selected is False
    assert "Rejected" in critical.reason
    assert result.selected_policy == "QUARANTINED"


def test_safe_case_selects_best_eligible_qos_policy(risk_config):
    result = evaluate_risk_aware_policy(make_input(0, 100), risk_config)

    assert result.security_constraint_satisfied is True
    assert result.selected_policy == "CRITICAL PRIORITY"
    assert result.combined_objective_score == pytest.approx(
        next(
            item.combined_objective_score
            for item in result.evaluations
            if item.policy == result.selected_policy
        )
    )
    assert next(
        item for item in result.evaluations if item.policy == result.selected_policy
    ).selected is True
