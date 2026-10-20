from dataclasses import replace
from pathlib import Path

import pytest

from src import integrated_controller as integrated
from src.decision_engine import CONFIG_PATH, load_config
from src.models import DecisionResult, NetworkInput
from src.policy_stability import (
    StabilityObjective,
    apply_policy_hysteresis,
    calculate_stability_aware_objective,
    switching_cost,
)
from src.risk_model import RiskAwareDecision, evaluate_risk_aware_policy


@pytest.fixture
def safe_input():
    return NetworkInput(
        traffic_type="Video Call",
        threat_level=1,
        congestion=1,
        bandwidth_available=100,
        application_priority=10,
        device_trust=95,
        latency=10,
    )


@pytest.fixture
def phase1_result():
    return DecisionResult(
        decision_score=91,
        priority="CRITICAL",
        qos_policy="CRITICAL PRIORITY",
        bandwidth_allocation=80,
        queue="Critical Queue",
        security_action="ALLOW",
        reason="Phase 1 baseline",
        factor_contributions={"priority": 1.0},
        normalized_factors={"application_priority": 100},
        dynamic_weights={"application_priority": 0.25},
    )


@pytest.fixture
def risk_result():
    return RiskAwareDecision(
        qos_utility=82,
        security_risk=20,
        combined_objective_score=73,
        r_max=65,
        security_constraint_satisfied=True,
        selected_policy="HIGH PRIORITY",
        reason="Risk-aware candidate selected.",
        utility_factors={"application_priority": 30},
        evaluations=(),
        raw_security_risk=20,
        smoothed_threat=24,
        threat_trend="TRENDING_UP",
        temporal_adjustment=10,
        effective_security_risk=30,
        risk_budget_status="SATISFIED",
        explanation="Temporal assessment.",
    )


def test_safe_scenario_produces_integrated_result(safe_input):
    result = integrated.run_integrated_controller(safe_input)

    assert result.network_input is safe_input
    assert isinstance(result.phase1_result, DecisionResult)
    assert isinstance(result.risk_aware_result, RiskAwareDecision)
    assert result.risk_budget_satisfied is True
    assert result.candidate_policy == result.risk_aware_result.selected_policy
    assert result.final_policy in {
        "CRITICAL PRIORITY", "HIGH PRIORITY", "NORMAL", "LOW / RATE LIMITED"
    }


def test_high_threat_low_trust_requires_quarantine():
    scenario = replace_input(threat_level=10, device_trust=0)

    result = integrated.run_integrated_controller(scenario)

    assert result.risk_budget_satisfied is False
    assert result.candidate_policy == "QUARANTINED"
    assert result.final_policy == "QUARANTINED"


def test_security_quarantine_cannot_be_downgraded_by_hysteresis(monkeypatch):
    scenario = replace_input(threat_level=10, device_trust=0)
    config = load_config()
    original_hysteresis = apply_policy_hysteresis
    observed = {}

    def inspect_hysteresis(candidate, previous, score, stability, **kwargs):
        observed.update(
            candidate=candidate,
            previous=previous,
            kwargs=kwargs,
        )
        return original_hysteresis(candidate, previous, score, stability, **kwargs)

    monkeypatch.setattr(integrated, "apply_policy_hysteresis", inspect_hysteresis)
    result = integrated.run_integrated_controller(
        scenario, previous_policy="CRITICAL PRIORITY"
    )

    assert observed["candidate"] == "QUARANTINED"
    assert observed["previous"] == "CRITICAL PRIORITY"
    assert observed["kwargs"]["effective_security_risk"] > config["risk_aware"]["r_max"]
    assert observed["kwargs"]["r_max"] == config["risk_aware"]["r_max"]
    assert result.final_policy == "QUARANTINED"
    assert "security constraint precedence" in result.explanation.lower()


def test_previous_smoothed_threat_is_passed_to_evaluator(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = {}
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)

    def evaluate(network_input, config, previous_smoothed_threat=None):
        observed["previous_smoothed_threat"] = previous_smoothed_threat
        return risk_result

    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", evaluate)
    result = integrated.run_integrated_controller(
        safe_input, previous_smoothed_threat=18.5
    )

    assert observed["previous_smoothed_threat"] == 18.5
    assert result.previous_smoothed_threat == 18.5


def test_previous_policy_is_passed_to_hysteresis(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = {}
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)

    def hysteresis(candidate, previous, score, config, **kwargs):
        observed.update(candidate=candidate, previous=previous)
        return candidate

    monkeypatch.setattr(integrated, "apply_policy_hysteresis", hysteresis)
    result = integrated.run_integrated_controller(
        safe_input, previous_policy="NORMAL"
    )

    assert observed == {"candidate": "HIGH PRIORITY", "previous": "NORMAL"}
    assert result.previous_policy == "NORMAL"


def test_temporal_fields_are_preserved(safe_input):
    result = integrated.run_integrated_controller(
        safe_input, previous_smoothed_threat=0.0
    )

    assert result.smoothed_threat == result.risk_aware_result.smoothed_threat
    assert result.threat_trend == result.risk_aware_result.threat_trend
    assert result.temporal_adjustment == result.risk_aware_result.temporal_adjustment


def test_raw_and_effective_security_risk_are_preserved(safe_input):
    result = integrated.run_integrated_controller(safe_input)

    assert result.raw_security_risk == result.risk_aware_result.raw_security_risk
    assert result.effective_security_risk == (
        result.risk_aware_result.effective_security_risk
    )


def test_r_max_status_is_preserved(safe_input):
    result = integrated.run_integrated_controller(safe_input)

    assert result.risk_budget_satisfied is (
        result.risk_aware_result.security_constraint_satisfied
    )


def test_switching_cost_uses_existing_helper(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = {}
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)
    original = switching_cost

    def inspect_cost(previous, candidate):
        observed.update(previous=previous, candidate=candidate)
        return original(previous, candidate)

    monkeypatch.setattr(integrated, "switching_cost", inspect_cost)
    result = integrated.run_integrated_controller(
        safe_input, previous_policy="NORMAL"
    )

    assert observed == {"previous": "NORMAL", "candidate": result.final_policy}
    assert result.switching_cost == original("NORMAL", result.final_policy)


def test_stability_objective_uses_existing_helper(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = {}
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)
    original = calculate_stability_aware_objective

    def inspect_objective(**kwargs):
        observed.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(
        integrated, "calculate_stability_aware_objective", inspect_objective
    )
    result = integrated.run_integrated_controller(
        safe_input, previous_policy="NORMAL"
    )

    assert isinstance(result.stability_objective, StabilityObjective)
    assert observed["qos_utility"] == risk_result.qos_utility
    assert observed["security_risk"] == risk_result.raw_security_risk
    assert observed["candidate_policy"] == result.final_policy


def test_candidate_and_final_policy_are_both_preserved(
    monkeypatch, safe_input, phase1_result, risk_result
):
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)
    monkeypatch.setattr(
        integrated,
        "apply_policy_hysteresis",
        lambda *a, **k: "NORMAL",
    )

    result = integrated.run_integrated_controller(safe_input, previous_policy="NORMAL")

    assert result.candidate_policy == "HIGH PRIORITY"
    assert result.final_policy == "NORMAL"
    assert "does not rerank" in result.explanation


def test_phase1_native_result_is_preserved(
    monkeypatch, safe_input, phase1_result, risk_result
):
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)

    result = integrated.run_integrated_controller(safe_input)

    assert result.phase1_result is phase1_result
    assert result.phase1_result.factor_contributions == {"priority": 1.0}
    assert result.phase1_result.normalized_factors == {"application_priority": 100}


def test_no_hidden_temporal_state_between_calls(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = []
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)

    def evaluate(network_input, config, previous_smoothed_threat=None):
        observed.append(previous_smoothed_threat)
        return risk_result

    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", evaluate)
    first = integrated.run_integrated_controller(safe_input)
    second = integrated.run_integrated_controller(safe_input)

    assert observed == [None, None]
    assert first.smoothed_threat == second.smoothed_threat


def test_no_hidden_previous_policy_state_between_calls(
    monkeypatch, safe_input, phase1_result, risk_result
):
    observed = []
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)

    def hysteresis(candidate, previous, score, config, **kwargs):
        observed.append(previous)
        return candidate

    monkeypatch.setattr(integrated, "apply_policy_hysteresis", hysteresis)
    integrated.run_integrated_controller(safe_input)
    integrated.run_integrated_controller(safe_input)

    assert observed == [None, None]


def test_configuration_defaults_are_unchanged():
    config = load_config()

    assert config["risk_aware"]["r_max"] == 65
    assert config["temporal"]["enabled"] is True
    assert config["temporal"]["alpha"] == 0.4
    assert config["temporal"]["trend_threshold"] == 5.0
    assert config["stability"]["switching_penalty"] == 2.0
    assert config["stability"]["hysteresis"] == {
        "enabled": True,
        "high_enter": 70,
        "high_exit": 65,
        "critical_enter": 85,
        "critical_exit": 80,
        "normal_enter": 50,
        "normal_exit": 45,
    }


def test_controller_does_not_modify_config_file(safe_input):
    before = Path(CONFIG_PATH).read_bytes()

    integrated.run_integrated_controller(safe_input)

    assert Path(CONFIG_PATH).read_bytes() == before


def test_controller_delegates_to_phase1_evaluator_and_phase4_helpers(
    monkeypatch, safe_input, phase1_result, risk_result
):
    calls = []
    monkeypatch.setattr(
        integrated,
        "make_decision",
        lambda value: calls.append(("phase1", value)) or phase1_result,
    )
    monkeypatch.setattr(
        integrated,
        "evaluate_risk_aware_policy",
        lambda *args, **kwargs: calls.append(("risk", args[0])) or risk_result,
    )
    monkeypatch.setattr(
        integrated,
        "apply_policy_hysteresis",
        lambda *args, **kwargs: calls.append(("hysteresis", args[0])) or args[0],
    )
    monkeypatch.setattr(
        integrated,
        "switching_cost",
        lambda *args: calls.append(("switching_cost", args)) or 0.0,
    )
    monkeypatch.setattr(
        integrated,
        "calculate_stability_aware_objective",
        lambda **kwargs: calls.append(("objective", kwargs))
        or StabilityObjective(1, 0, 0, 1, False),
    )

    integrated.run_integrated_controller(safe_input)

    assert [name for name, _ in calls] == [
        "phase1", "risk", "hysteresis", "switching_cost", "objective"
    ]


def test_explicit_state_sequence_is_deterministic(safe_input):
    state = {"threat": None, "policy": None}
    outcomes = []
    for _ in range(2):
        current_state = {"threat": None, "policy": None}
        sequence = []
        for threat in (1, 2, 3):
            scenario = replace_input(safe_input, threat_level=threat)
            result = integrated.run_integrated_controller(
                scenario,
                previous_smoothed_threat=current_state["threat"],
                previous_policy=current_state["policy"],
            )
            sequence.append((result.smoothed_threat, result.final_policy))
            current_state["threat"] = result.smoothed_threat
            current_state["policy"] = result.final_policy
        outcomes.append(sequence)
    assert outcomes[0] == outcomes[1]
    assert state == {"threat": None, "policy": None}


def test_invalid_network_input_uses_existing_validation():
    with pytest.raises(ValueError, match="Threat level"):
        integrated.run_integrated_controller(replace_input(threat_level=11))


def test_non_network_input_is_rejected():
    with pytest.raises(TypeError, match="NetworkInput"):
        integrated.run_integrated_controller(object())  # type: ignore[arg-type]


def test_hysteresis_and_switching_are_based_on_final_policy(
    monkeypatch, safe_input, phase1_result, risk_result
):
    monkeypatch.setattr(integrated, "make_decision", lambda _: phase1_result)
    monkeypatch.setattr(integrated, "evaluate_risk_aware_policy", lambda *a, **k: risk_result)
    monkeypatch.setattr(
        integrated, "apply_policy_hysteresis", lambda *a, **k: "NORMAL"
    )
    monkeypatch.setattr(
        integrated, "switching_cost",
        lambda previous, candidate: 1.0 if (previous, candidate) == ("HIGH PRIORITY", "NORMAL") else 0.0,
    )

    result = integrated.run_integrated_controller(
        safe_input, previous_policy="HIGH PRIORITY"
    )

    assert result.candidate_policy == "HIGH PRIORITY"
    assert result.final_policy == "NORMAL"
    assert result.switching_cost == 1.0


def replace_input(network_input=None, **changes):
    if network_input is None:
        network_input = NetworkInput(
            traffic_type="Video Call",
            threat_level=1,
            congestion=1,
            bandwidth_available=100,
            application_priority=10,
            device_trust=95,
            latency=10,
        )
    return replace(network_input, **changes)
