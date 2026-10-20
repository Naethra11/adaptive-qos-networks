"""Reproducible software-level ablation runner for Phases 1–4."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from src.decision_engine import load_config, make_decision
from src.models import DecisionResult, NetworkInput
from src.policy_stability import (
    StabilityObjective,
    apply_policy_hysteresis,
    calculate_stability_aware_objective,
    switching_cost,
)
from src.risk_model import RiskAwareDecision, evaluate_risk_aware_policy


PHASE1_BASELINE = "PHASE1_BASELINE"
PHASE2_RISK_AWARE = "PHASE2_RISK_AWARE"
PHASE3_TEMPORAL = "PHASE3_TEMPORAL"
PHASE4_STABILITY = "PHASE4_STABILITY"

AblationVariant = Literal[
    "PHASE1_BASELINE",
    "PHASE2_RISK_AWARE",
    "PHASE3_TEMPORAL",
    "PHASE4_STABILITY",
]

_VARIANTS = {
    PHASE1_BASELINE,
    PHASE2_RISK_AWARE,
    PHASE3_TEMPORAL,
    PHASE4_STABILITY,
}
@dataclass(frozen=True)
class AblationResult:
    """Native controller output plus common fields for variant comparison."""

    variant: str
    native_result: DecisionResult | RiskAwareDecision
    scenario: NetworkInput
    decision_score: float | None
    policy: str
    priority: str | None
    security_action: str | None
    bandwidth_allocation: float | None
    raw_security_risk: float | None
    effective_security_risk: float | None
    qos_utility: float | None
    risk_budget_satisfied: bool | None
    threat_trend: str | None
    smoothed_threat: float | None
    temporal_adjustment: float | None
    previous_policy: str | None
    switching_cost: float | None
    stability_objective: StabilityObjective | None
    explanation: str
    candidate_policy: str | None = None


def run_ablation_scenario(
    network_input: NetworkInput,
    *,
    previous_smoothed_threat: float | None = None,
    previous_policy: str | None = None,
    variant: AblationVariant | str,
) -> AblationResult:
    """Evaluate one unchanged input using the requested Phase 1–4 variant.

    Phase 2 uses a deep in-memory copy of the normal configuration and disables
    only the temporal risk adjustment. The shared risk evaluator still computes
    and reports EWMA threat state internally.

    Phase 4 starts from the Phase 3 risk-aware result, applies the existing
    hysteresis helper, then records the existing stability-aware objective
    separately. That objective is not used to rank or replace the risk-aware
    evaluator's candidate policies.
    """
    if not isinstance(network_input, NetworkInput):
        raise TypeError("network_input must be a NetworkInput.")
    network_input.validate()
    if variant not in _VARIANTS:
        raise ValueError(
            f"Unknown ablation variant {variant!r}; choose one of "
            f"{', '.join(sorted(_VARIANTS))}."
        )

    if variant == PHASE1_BASELINE:
        native = make_decision(network_input)
        return AblationResult(
            variant=variant,
            native_result=native,
            scenario=network_input,
            decision_score=native.decision_score,
            policy=native.qos_policy,
            priority=native.priority,
            security_action=native.security_action,
            bandwidth_allocation=native.bandwidth_allocation,
            raw_security_risk=None,
            effective_security_risk=None,
            qos_utility=None,
            risk_budget_satisfied=None,
            threat_trend=None,
            smoothed_threat=None,
            temporal_adjustment=None,
            previous_policy=None,
            switching_cost=None,
            stability_objective=None,
            explanation=native.reason,
        )

    config = load_config()
    if variant == PHASE2_RISK_AWARE:
        config = deepcopy(config)
        config["temporal"]["enabled"] = False
        native = evaluate_risk_aware_policy(
            network_input,
            config,
            previous_smoothed_threat=previous_smoothed_threat,
        )
        return _risk_result(
            variant,
            network_input,
            native,
            previous_policy=None,
        )

    native = evaluate_risk_aware_policy(
        network_input,
        config,
        previous_smoothed_threat=previous_smoothed_threat,
    )
    if variant == PHASE3_TEMPORAL:
        return _risk_result(
            variant,
            network_input,
            native,
            previous_policy=None,
        )

    candidate_policy = native.selected_policy
    final_policy = apply_policy_hysteresis(
        candidate_policy,
        previous_policy,
        native.qos_utility,
        config["stability"],
        effective_security_risk=native.effective_security_risk,
        r_max=native.r_max,
    )
    stability_config = config["stability"]
    transition_cost = switching_cost(previous_policy, final_policy)
    objective = calculate_stability_aware_objective(
        qos_utility=native.qos_utility,
        policy_multiplier=config["risk_aware"]["policy_utility_multipliers"][
            final_policy
        ],
        risk_penalty_weight=config["risk_aware"]["risk_penalty_weight"],
        security_risk=native.raw_security_risk,
        switching_penalty=stability_config["switching_penalty"],
        previous_policy=previous_policy,
        candidate_policy=final_policy,
        enabled=stability_config["enabled"],
    )
    explanation = native.reason
    if final_policy != candidate_policy:
        explanation = (
            f"{native.reason} Hysteresis retained {final_policy} instead of "
            f"the risk-aware candidate {candidate_policy}."
        )

    return AblationResult(
        variant=variant,
        native_result=native,
        scenario=network_input,
        decision_score=None,
        policy=final_policy,
        priority=None,
        security_action=None,
        bandwidth_allocation=None,
        raw_security_risk=native.raw_security_risk,
        effective_security_risk=native.effective_security_risk,
        qos_utility=native.qos_utility,
        risk_budget_satisfied=native.security_constraint_satisfied,
        threat_trend=native.threat_trend,
        smoothed_threat=native.smoothed_threat,
        temporal_adjustment=native.temporal_adjustment,
        previous_policy=previous_policy,
        switching_cost=transition_cost,
        stability_objective=objective,
        explanation=explanation,
        candidate_policy=candidate_policy,
    )


def _risk_result(
    variant: str,
    network_input: NetworkInput,
    native: RiskAwareDecision,
    *,
    previous_policy: str | None,
) -> AblationResult:
    return AblationResult(
        variant=variant,
        native_result=native,
        scenario=network_input,
        decision_score=None,
        policy=native.selected_policy,
        priority=None,
        security_action=None,
        bandwidth_allocation=None,
        raw_security_risk=native.raw_security_risk,
        effective_security_risk=native.effective_security_risk,
        qos_utility=native.qos_utility,
        risk_budget_satisfied=native.security_constraint_satisfied,
        threat_trend=native.threat_trend,
        smoothed_threat=native.smoothed_threat,
        temporal_adjustment=native.temporal_adjustment,
        previous_policy=previous_policy,
        switching_cost=None,
        stability_objective=None,
        explanation=native.reason,
    )
