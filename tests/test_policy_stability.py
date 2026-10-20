import pytest

from src.decision_engine import load_config
from src.policy_stability import (
    POLICY_ORDER,
    apply_policy_hysteresis,
    calculate_policy_stability_index,
    calculate_policy_switch_rate,
    calculate_stability_aware_objective,
    count_policy_switches,
    is_policy_switch_required,
    switching_cost,
)


@pytest.fixture
def stability_config():
    return load_config()["stability"]


def test_same_policy_requires_no_switch_and_has_zero_cost():
    assert is_policy_switch_required("NORMAL", "NORMAL") is False
    assert switching_cost("NORMAL", "NORMAL") == 0.0


def test_different_policy_requires_switch_and_has_unit_cost():
    assert is_policy_switch_required("NORMAL", "HIGH PRIORITY") is True
    assert switching_cost("NORMAL", "HIGH PRIORITY") == 1.0


def test_switching_penalty_only_applies_when_policy_changes():
    unchanged = calculate_stability_aware_objective(
        80, 0.9, 0.25, 40, 2, "NORMAL", "NORMAL"
    )
    changed = calculate_stability_aware_objective(
        80, 0.9, 0.25, 40, 2, "NORMAL", "HIGH PRIORITY"
    )

    assert unchanged.base_objective == 62
    assert unchanged.switching_penalty == 0
    assert unchanged.stability_aware_objective == 62
    assert changed.switching_cost == 1
    assert changed.switching_penalty == 2
    assert changed.stability_aware_objective == 60


def test_disabled_stability_does_not_apply_switching_penalty():
    result = calculate_stability_aware_objective(
        80, 0.9, 0.25, 40, 2, "NORMAL", "HIGH PRIORITY", enabled=False
    )

    assert result.switch_required is True
    assert result.switching_cost == 0
    assert result.stability_aware_objective == result.base_objective


def test_stable_policy_sequence_has_zero_switches():
    policies = ["NORMAL"] * 6
    assert count_policy_switches(policies) == 0


def test_fluctuating_policy_sequence_has_measurable_switches():
    policies = [
        "NORMAL",
        "HIGH PRIORITY",
        "NORMAL",
        "HIGH PRIORITY",
        "NORMAL",
        "HIGH PRIORITY",
    ]
    assert count_policy_switches(policies) == 5


def test_policy_switch_rate_and_stability_index():
    assert calculate_policy_switch_rate(10, 2) == 0.2
    assert calculate_policy_stability_index(10, 2) == 0.8


def test_zero_decisions_have_safe_metric_values():
    assert calculate_policy_switch_rate(0, 0) == 0.0
    assert calculate_policy_stability_index(0, 0) == 1.0


def test_high_hysteresis_prevents_immediate_downgrade(stability_config):
    result = apply_policy_hysteresis(
        "NORMAL", "HIGH PRIORITY", 69, stability_config
    )

    assert result == "HIGH PRIORITY"


def test_high_can_downgrade_below_exit_threshold(stability_config):
    result = apply_policy_hysteresis(
        "NORMAL", "HIGH PRIORITY", 64, stability_config
    )

    assert result == "NORMAL"


def test_normal_enters_high_only_after_high_enter_threshold(stability_config):
    assert (
        apply_policy_hysteresis("HIGH PRIORITY", "NORMAL", 69, stability_config)
        == "NORMAL"
    )
    assert (
        apply_policy_hysteresis("HIGH PRIORITY", "NORMAL", 70, stability_config)
        == "HIGH PRIORITY"
    )


def test_critical_hysteresis_uses_enter_and_exit_thresholds(stability_config):
    assert (
        apply_policy_hysteresis("CRITICAL PRIORITY", "HIGH PRIORITY", 84, stability_config)
        == "HIGH PRIORITY"
    )
    assert (
        apply_policy_hysteresis("CRITICAL PRIORITY", "HIGH PRIORITY", 85, stability_config)
        == "CRITICAL PRIORITY"
    )
    assert (
        apply_policy_hysteresis("HIGH PRIORITY", "CRITICAL PRIORITY", 82, stability_config)
        == "CRITICAL PRIORITY"
    )
    assert (
        apply_policy_hysteresis("HIGH PRIORITY", "CRITICAL PRIORITY", 79, stability_config)
        == "HIGH PRIORITY"
    )


def test_quarantined_candidate_is_never_blocked_by_hysteresis(stability_config):
    result = apply_policy_hysteresis(
        "QUARANTINED", "CRITICAL PRIORITY", 95, stability_config
    )

    assert result == "QUARANTINED"


def test_risk_budget_breach_forces_quarantine_even_when_candidate_is_ordinary(stability_config):
    result = apply_policy_hysteresis(
        "HIGH PRIORITY",
        "NORMAL",
        70,
        stability_config,
        effective_security_risk=66,
        r_max=65,
    )

    assert result == "QUARANTINED"


def test_hysteresis_reduces_switches_in_boundary_sequence(stability_config):
    scores = [69, 71, 69, 71, 69, 71]
    baseline = ["HIGH PRIORITY" if score >= 70 else "NORMAL" for score in scores]
    stabilized = []
    previous = None

    for candidate, score in zip(baseline, scores):
        selected = apply_policy_hysteresis(
            candidate, previous, score, stability_config
        )
        stabilized.append(selected)
        previous = selected

    assert baseline == [
        "NORMAL",
        "HIGH PRIORITY",
        "NORMAL",
        "HIGH PRIORITY",
        "NORMAL",
        "HIGH PRIORITY",
    ]
    assert stabilized == [
        "NORMAL",
        "HIGH PRIORITY",
        "HIGH PRIORITY",
        "HIGH PRIORITY",
        "HIGH PRIORITY",
        "HIGH PRIORITY",
    ]
    assert count_policy_switches(stabilized) == 1
    assert count_policy_switches(baseline) == 5


def test_policy_order_matches_specification():
    assert POLICY_ORDER == (
        "CRITICAL PRIORITY",
        "HIGH PRIORITY",
        "NORMAL",
        "LOW / RATE LIMITED",
        "QUARANTINED",
    )


@pytest.mark.parametrize("count", [-1, 1.5])
def test_invalid_metric_counts_are_rejected(count):
    with pytest.raises((ValueError, TypeError)):
        calculate_policy_switch_rate(count, 0)
