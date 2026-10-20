"""Phase 1–4 orchestration for the research controller.

This module integrates the already implemented Phase 1–4 mechanisms; it is an
orchestration layer, not a new decision algorithm. The research contribution
remains the evaluated combination of multi-factor QoS decision-making,
security-risk constraints, temporal threat awareness, and policy
stability/hysteresis. This software is not a claim of production readiness.
"""

from dataclasses import dataclass

from src.decision_engine import load_config, make_decision
from src.models import DecisionResult, NetworkInput
from src.policy_stability import (
    StabilityObjective,
    apply_policy_hysteresis,
    calculate_stability_aware_objective,
    switching_cost,
)
from src.risk_model import RiskAwareDecision, evaluate_risk_aware_policy


@dataclass(frozen=True)
class IntegratedDecisionResult:
    """Auditable native Phase 1 and Phase 2–4 outputs for one input."""

    network_input: NetworkInput
    phase1_result: DecisionResult
    risk_aware_result: RiskAwareDecision
    candidate_policy: str
    final_policy: str
    raw_security_risk: float
    effective_security_risk: float
    r_max: float
    qos_utility: float
    risk_budget_satisfied: bool
    smoothed_threat: float
    threat_trend: str
    temporal_adjustment: float
    previous_smoothed_threat: float | None
    previous_policy: str | None
    switching_cost: float
    stability_objective: StabilityObjective
    explanation: str


def run_integrated_controller(
    network_input: NetworkInput,
    *,
    previous_smoothed_threat: float | None = None,
    previous_policy: str | None = None,
) -> IntegratedDecisionResult:
    """Run the existing Phase 1→2→3→4 mechanisms with explicit caller state.

    Phase 1 provides the preserved baseline decision context. The Phase 2/3
    evaluator independently evaluates risk-aware utility and temporal state.
    Phase 4 applies existing hysteresis to that selected candidate and records
    switching cost and the stability objective separately; the objective does
    not rerank the candidate policy.
    """
    if not isinstance(network_input, NetworkInput):
        raise TypeError("network_input must be a NetworkInput.")
    network_input.validate()

    phase1_result = make_decision(network_input)
    config = load_config()
    risk_aware_result = evaluate_risk_aware_policy(
        network_input,
        config,
        previous_smoothed_threat=previous_smoothed_threat,
    )

    candidate_policy = risk_aware_result.selected_policy
    final_policy = apply_policy_hysteresis(
        candidate_policy,
        previous_policy,
        risk_aware_result.qos_utility,
        config["stability"],
        effective_security_risk=risk_aware_result.effective_security_risk,
        r_max=risk_aware_result.r_max,
    )

    transition_cost = switching_cost(previous_policy, final_policy)
    stability_objective = calculate_stability_aware_objective(
        qos_utility=risk_aware_result.qos_utility,
        policy_multiplier=config["risk_aware"]["policy_utility_multipliers"][
            final_policy
        ],
        risk_penalty_weight=config["risk_aware"]["risk_penalty_weight"],
        security_risk=risk_aware_result.raw_security_risk,
        switching_penalty=config["stability"]["switching_penalty"],
        previous_policy=previous_policy,
        candidate_policy=final_policy,
        enabled=config["stability"]["enabled"],
    )

    explanation = risk_aware_result.reason
    if not risk_aware_result.security_constraint_satisfied:
        explanation += (
            " Security constraint precedence: effective risk exceeds R_MAX, "
            "so quarantine is retained regardless of the previous policy."
        )
    elif final_policy != candidate_policy:
        explanation += (
            f" Phase 4 hysteresis retained {final_policy} instead of the "
            f"risk-aware candidate {candidate_policy}."
        )
    explanation += (
        f" Stability-aware objective is "
        f"{stability_objective.stability_aware_objective:.2f}; it is reported "
        "separately and does not rerank the candidate policy."
    )

    return IntegratedDecisionResult(
        network_input=network_input,
        phase1_result=phase1_result,
        risk_aware_result=risk_aware_result,
        candidate_policy=candidate_policy,
        final_policy=final_policy,
        raw_security_risk=risk_aware_result.raw_security_risk,
        effective_security_risk=risk_aware_result.effective_security_risk,
        r_max=risk_aware_result.r_max,
        qos_utility=risk_aware_result.qos_utility,
        risk_budget_satisfied=risk_aware_result.security_constraint_satisfied,
        smoothed_threat=risk_aware_result.smoothed_threat,
        threat_trend=risk_aware_result.threat_trend,
        temporal_adjustment=risk_aware_result.temporal_adjustment,
        previous_smoothed_threat=previous_smoothed_threat,
        previous_policy=previous_policy,
        switching_cost=transition_cost,
        stability_objective=stability_objective,
        explanation=explanation,
    )
