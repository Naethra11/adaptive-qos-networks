from copy import deepcopy
from dataclasses import replace

import pytest

from src import ablation
from src.decision_engine import load_config
from src.models import DecisionResult, NetworkInput
from src.policy_stability import StabilityObjective
from src.risk_model import RiskAwareDecision


@pytest.fixture
def scenario():
    return NetworkInput(
        traffic_type="Video Call",
        threat_level=2,
        congestion=3,
        bandwidth_available=50,
        application_priority=9,
        device_trust=90,
        latency=40,
    )


@pytest.fixture
def phase1_result():
    return DecisionResult(
        decision_score=81,
        priority="HIGH",
        qos_policy="HIGH PRIORITY",
        bandwidth_allocation=30,
        queue="High Priority Queue",
        security_action="ALLOW",
        reason="baseline decision",
        factor_contributions={},
        normalized_factors={},
        dynamic_weights={},
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
        reason="risk-aware decision",
        utility_factors={},
        evaluations=(),
        raw_security_risk=20,
        smoothed_threat=24,
        threat_trend="TRENDING_UP",
        temporal_adjustment=10,
        effective_security_risk=30,
        risk_budget_status="SATISFIED",
        explanation="risk explanation",
    )


def test_phase1_calls_only_make_decision_and_preserves_native_result(
    monkeypatch, scenario, phase1_result
):
    calls = []

    def make_decision(network_input):
        calls.append(network_input)
        return phase1_result

    monkeypatch.setattr(ablation, "make_decision", make_decision)
    monkeypatch.setattr(
        ablation,
        "evaluate_risk_aware_policy",
        lambda *args, **kwargs: pytest.fail("risk evaluator must not run"),
    )
    monkeypatch.setattr(
        ablation,
        "apply_policy_hysteresis",
        lambda *args, **kwargs: pytest.fail("stability helper must not run"),
    )

    result = ablation.run_ablation_scenario(
        scenario, variant=ablation.PHASE1_BASELINE
    )

    assert calls == [scenario]
    assert result.native_result is phase1_result
    assert result.scenario is scenario
    assert result.decision_score == 81
    assert result.policy == "HIGH PRIORITY"
    assert result.priority == "HIGH"
    assert result.raw_security_risk is None
    assert result.effective_security_risk is None


def test_phase2_disables_temporal_adjustment_on_deep_config_copy(
    monkeypatch, scenario, risk_result
):
    source_config = load_config()
    original = deepcopy(source_config)
    captured = {}

    monkeypatch.setattr(ablation, "load_config", lambda: source_config)

    def evaluate(network_input, config, previous_smoothed_threat=None):
        captured["network_input"] = network_input
        captured["config"] = config
        captured["previous_smoothed_threat"] = previous_smoothed_threat
        return replace(risk_result, temporal_adjustment=0)

    monkeypatch.setattr(ablation, "evaluate_risk_aware_policy", evaluate)

    result = ablation.run_ablation_scenario(
        scenario,
        previous_smoothed_threat=12,
        variant=ablation.PHASE2_RISK_AWARE,
    )

    assert captured["config"] is not source_config
    assert captured["config"]["temporal"] is not source_config["temporal"]
    assert captured["config"]["temporal"]["enabled"] is False
    assert captured["previous_smoothed_threat"] == 12
    assert source_config == original
    assert result.native_result.temporal_adjustment == 0
    assert result.temporal_adjustment == 0


def test_phase3_passes_previous_smoothed_threat_and_preserves_temporal_fields(
    monkeypatch, scenario, risk_result
):
    captured = {}
    monkeypatch.setattr(ablation, "load_config", load_config)

    def evaluate(network_input, config, previous_smoothed_threat=None):
        captured["network_input"] = network_input
        captured["config"] = config
        captured["previous_smoothed_threat"] = previous_smoothed_threat
        return risk_result

    monkeypatch.setattr(ablation, "evaluate_risk_aware_policy", evaluate)

    result = ablation.run_ablation_scenario(
        scenario,
        previous_smoothed_threat=14,
        variant=ablation.PHASE3_TEMPORAL,
    )

    assert captured["previous_smoothed_threat"] == 14
    assert captured["config"]["temporal"]["enabled"] is True
    assert result.native_result is risk_result
    assert result.threat_trend == "TRENDING_UP"
    assert result.smoothed_threat == 24
    assert result.temporal_adjustment == 10
    assert result.effective_security_risk == 30


def test_phase4_supplies_previous_policy_and_applies_hysteresis(
    monkeypatch, scenario, risk_result
):
    calls = {}
    monkeypatch.setattr(ablation, "load_config", load_config)
    monkeypatch.setattr(
        ablation,
        "evaluate_risk_aware_policy",
        lambda *args, **kwargs: risk_result,
    )

    def hysteresis(candidate, previous, score, config, **kwargs):
        calls["hysteresis"] = (candidate, previous, score, config, kwargs)
        return "NORMAL"

    monkeypatch.setattr(ablation, "apply_policy_hysteresis", hysteresis)
    monkeypatch.setattr(ablation, "switching_cost", lambda previous, candidate: 1.0)
    monkeypatch.setattr(
        ablation,
        "calculate_stability_aware_objective",
        lambda **kwargs: StabilityObjective(1, 1, 2, -1, True),
    )

    result = ablation.run_ablation_scenario(
        scenario,
        previous_policy="NORMAL",
        variant=ablation.PHASE4_STABILITY,
    )

    assert calls["hysteresis"][0:3] == ("HIGH PRIORITY", "NORMAL", 82)
    assert calls["hysteresis"][4] == {
        "effective_security_risk": 30,
        "r_max": 65,
    }
    assert result.candidate_policy == "HIGH PRIORITY"
    assert result.policy == "NORMAL"
    assert result.native_result is risk_result
    assert "Hysteresis retained NORMAL" in result.explanation


def test_phase4_calculates_switching_cost_and_objective_separately(
    monkeypatch, scenario, risk_result
):
    captured = {}
    monkeypatch.setattr(ablation, "load_config", load_config)
    monkeypatch.setattr(
        ablation,
        "evaluate_risk_aware_policy",
        lambda *args, **kwargs: risk_result,
    )
    monkeypatch.setattr(
        ablation,
        "apply_policy_hysteresis",
        lambda candidate, previous, score, config, **kwargs: candidate,
    )

    def cost(previous, candidate):
        captured["cost"] = (previous, candidate)
        return 1.0

    def objective(**kwargs):
        captured["objective"] = kwargs
        return StabilityObjective(73, 1, 2, 71, True)

    monkeypatch.setattr(ablation, "switching_cost", cost)
    monkeypatch.setattr(
        ablation, "calculate_stability_aware_objective", objective
    )

    result = ablation.run_ablation_scenario(
        scenario,
        previous_policy="NORMAL",
        variant=ablation.PHASE4_STABILITY,
    )

    assert captured["cost"] == ("NORMAL", "HIGH PRIORITY")
    assert result.switching_cost == 1
    assert result.stability_objective == StabilityObjective(73, 1, 2, 71, True)
    assert captured["objective"]["candidate_policy"] == "HIGH PRIORITY"
    assert captured["objective"]["security_risk"] == 20
    assert captured["objective"]["enabled"] is True
    assert result.native_result.selected_policy == "HIGH PRIORITY"


def test_phase4_risk_breach_forces_quarantine_over_hysteresis(
    monkeypatch, scenario, risk_result
):
    breached = replace(
        risk_result,
        selected_policy="NORMAL",
        security_constraint_satisfied=False,
        effective_security_risk=70,
        r_max=65,
    )
    monkeypatch.setattr(ablation, "load_config", load_config)
    monkeypatch.setattr(
        ablation,
        "evaluate_risk_aware_policy",
        lambda *args, **kwargs: breached,
    )
    result = ablation.run_ablation_scenario(
        scenario,
        previous_policy="HIGH PRIORITY",
        variant=ablation.PHASE4_STABILITY,
    )

    assert result.candidate_policy == "NORMAL"
    assert result.policy == "QUARANTINED"
    assert result.risk_budget_satisfied is False


def test_unknown_variant_raises_clear_error(scenario):
    with pytest.raises(ValueError, match="Unknown ablation variant"):
        ablation.run_ablation_scenario(scenario, variant="PHASE5")


def test_same_scenario_runs_through_all_four_variants(scenario):
    results = [
        ablation.run_ablation_scenario(scenario, variant=variant)
        for variant in (
            ablation.PHASE1_BASELINE,
            ablation.PHASE2_RISK_AWARE,
            ablation.PHASE3_TEMPORAL,
            ablation.PHASE4_STABILITY,
        )
    ]

    assert all(result.scenario is scenario for result in results)
    assert [result.variant for result in results] == [
        ablation.PHASE1_BASELINE,
        ablation.PHASE2_RISK_AWARE,
        ablation.PHASE3_TEMPORAL,
        ablation.PHASE4_STABILITY,
    ]
    assert isinstance(results[0].native_result, DecisionResult)
    assert all(
        isinstance(result.native_result, RiskAwareDecision)
        for result in results[1:]
    )
    assert results[0].decision_score is not None
    assert results[1].temporal_adjustment == 0
    assert results[2].temporal_adjustment is not None
    assert results[3].stability_objective is not None


def test_result_fields_are_none_when_unavailable(scenario):
    result = ablation.run_ablation_scenario(
        scenario, variant=ablation.PHASE2_RISK_AWARE
    )

    assert result.decision_score is None
    assert result.priority is None
    assert result.security_action is None
    assert result.bandwidth_allocation is None
    assert result.switching_cost is None
    assert result.stability_objective is None
