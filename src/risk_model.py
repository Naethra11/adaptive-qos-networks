"""Independent, explainable risk-aware policy evaluation for Phase 2."""

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from src.models import NetworkInput
from src.normalization import normalize_inputs
from src.decision_engine import get_traffic_type_score
from src.temporal_risk import assess_temporal_risk
from src.threat_trend import update_threat_trend


POLICY_ORDER = (
    "CRITICAL PRIORITY",
    "HIGH PRIORITY",
    "NORMAL",
    "LOW / RATE LIMITED",
    "QUARANTINED",
)
UTILITY_FACTOR_KEYS = (
    "application_priority",
    "traffic_type",
    "congestion",
    "bandwidth",
    "latency",
)


@dataclass(frozen=True)
class PolicyEvaluation:
    """Scores and constraint result for one candidate QoS policy."""

    policy: str
    utility_score: float
    combined_objective_score: float
    security_constraint_satisfied: bool
    admissible: bool
    selected: bool
    reason: str


@dataclass(frozen=True)
class RiskAwareDecision:
    """Explainable QoS utility, security risk, and selected policy."""

    qos_utility: float
    security_risk: float
    combined_objective_score: float
    r_max: float
    security_constraint_satisfied: bool
    selected_policy: str
    reason: str
    utility_factors: Mapping[str, float]
    evaluations: tuple[PolicyEvaluation, ...]
    raw_security_risk: float
    smoothed_threat: float
    threat_trend: str
    temporal_adjustment: float
    effective_security_risk: float
    risk_budget_status: str
    explanation: str


def calculate_security_risk(
    threat_level: float,
    device_trust: float,
    risk_weights: Mapping[str, float],
) -> float:
    """Calculate 0-100 risk from 0-10 threat and 0-100 device trust."""
    _validate_weights(risk_weights, {"threat", "untrusted_device"}, "risk")
    if not 0 <= threat_level <= 10:
        raise ValueError("Threat level must be between 0 and 10.")
    if not 0 <= device_trust <= 100:
        raise ValueError("Device trust must be between 0 and 100.")

    normalized_threat = threat_level * 10
    normalized_untrusted_device = 100 - device_trust
    risk = (
        risk_weights["threat"] * normalized_threat
        + risk_weights["untrusted_device"] * normalized_untrusted_device
    )
    return round(risk, 2)


def calculate_qos_utility(
    normalized_factors: Mapping[str, float],
    utility_weights: Mapping[str, float],
) -> float:
    """Calculate 0-100 QoS utility; high congestion is converted to low utility."""
    _validate_weights(utility_weights, set(UTILITY_FACTOR_KEYS), "QoS utility")
    missing_factors = set(UTILITY_FACTOR_KEYS) - set(normalized_factors)
    if missing_factors:
        raise ValueError(f"Missing normalized utility factors: {sorted(missing_factors)}")

    utility_values = {
        **normalized_factors,
        "congestion": 100 - normalized_factors["congestion"],
    }
    return round(
        sum(utility_weights[factor] * utility_values[factor] for factor in UTILITY_FACTOR_KEYS),
        2,
    )


def evaluate_risk_aware_policy(
    network_input: NetworkInput,
    config: Mapping[str, Any],
    previous_smoothed_threat: float | None = None,
) -> RiskAwareDecision:
    """Evaluate baseline policy levels under an explicit maximum-risk constraint.

    Ordinary QoS policies are admissible only when effective temporal risk is
    at most ``risk_aware.r_max``. QUARANTINED remains the protective fallback.
    The original Phase 2 raw security risk is retained for reporting and the
    established combined-objective calculation.
    """
    network_input.validate()
    risk_config = config["risk_aware"]
    r_max = _finite_config_number(risk_config, "r_max")
    risk_penalty_weight = _finite_config_number(risk_config, "risk_penalty_weight")
    if not 0 <= r_max <= 100:
        raise ValueError("risk_aware.r_max must be between 0 and 100.")
    if risk_penalty_weight < 0:
        raise ValueError("risk_aware.risk_penalty_weight cannot be negative.")

    normalized = normalize_inputs(
        threat_level=network_input.threat_level,
        congestion=network_input.congestion,
        bandwidth_available=network_input.bandwidth_available,
        application_priority=network_input.application_priority,
        device_trust=network_input.device_trust,
        latency=network_input.latency,
    )
    normalized["traffic_type"] = get_traffic_type_score(
        network_input.traffic_type,
        config["traffic_type_scores"],
    )
    utility_weights = risk_config["qos_utility_weights"]
    utility_values = {
        **normalized,
        "congestion": 100 - normalized["congestion"],
    }
    utility_factors = {
        factor: round(utility_values[factor] * utility_weights[factor], 2)
        for factor in UTILITY_FACTOR_KEYS
    }
    qos_utility = calculate_qos_utility(normalized, utility_weights)
    security_risk = calculate_security_risk(
        network_input.threat_level,
        network_input.device_trust,
        risk_config["risk_weights"],
    )
    temporal_config = config["temporal"]
    temporal_state = update_threat_trend(
        network_input.threat_level,
        previous_smoothed_threat,
        alpha=temporal_config["alpha"],
        trend_threshold=temporal_config["trend_threshold"],
    )
    temporal_risk = assess_temporal_risk(
        raw_security_risk=security_risk,
        smoothed_threat=temporal_state.smoothed_threat,
        threat_trend=temporal_state.trend,
        temporal_config=temporal_config,
        r_max=r_max,
    )
    constraint_satisfied = temporal_risk.effective_security_risk <= r_max

    policy_thresholds = config["policy_thresholds"]
    policy_multipliers = risk_config["policy_utility_multipliers"]
    evaluations: list[PolicyEvaluation] = []
    for policy in POLICY_ORDER:
        threshold_key = {
            "CRITICAL PRIORITY": "critical",
            "HIGH PRIORITY": "high",
            "NORMAL": "normal",
        }.get(policy)
        utility_threshold = policy_thresholds[threshold_key] if threshold_key else 0
        policy_utility = round(qos_utility * policy_multipliers[policy], 2)
        objective = round(policy_utility - risk_penalty_weight * security_risk, 2)
        admissible = policy == "QUARANTINED" or constraint_satisfied
        meets_utility_threshold = qos_utility >= utility_threshold

        if not admissible:
            reason = (
                f"Rejected: effective security risk "
                f"{temporal_risk.effective_security_risk:.2f} exceeds R_MAX "
                f"({r_max:.2f}); ordinary QoS policies are not admissible."
            )
        elif not meets_utility_threshold:
            reason = (
                f"Not selected: QoS utility {qos_utility:.2f} is below this "
                f"policy's utility threshold ({utility_threshold:.2f})."
            )
        elif policy == "QUARANTINED" and not constraint_satisfied:
            reason = (
                f"Protective fallback: effective risk "
                f"{temporal_risk.effective_security_risk:.2f} exceeds "
                f"R_MAX ({r_max:.2f}); ordinary QoS policies are rejected."
            )
        else:
            reason = (
                f"Eligible: effective risk "
                f"{temporal_risk.effective_security_risk:.2f} is within "
                f"R_MAX ({r_max:.2f}) and QoS utility meets the "
                f"{utility_threshold:.2f} policy threshold."
            )

        evaluations.append(
            PolicyEvaluation(
                policy=policy,
                utility_score=policy_utility,
                combined_objective_score=objective,
                security_constraint_satisfied=constraint_satisfied,
                admissible=admissible,
                selected=False,
                reason=reason,
            )
        )

    eligible = [
        index
        for index, evaluation in enumerate(evaluations)
        if evaluation.admissible
        and qos_utility
        >= (
            policy_thresholds[
                {
                    "CRITICAL PRIORITY": "critical",
                    "HIGH PRIORITY": "high",
                    "NORMAL": "normal",
                }[evaluation.policy]
            ]
            if evaluation.policy in {"CRITICAL PRIORITY", "HIGH PRIORITY", "NORMAL"}
            else 0
        )
    ]
    selected_index = max(
        eligible,
        key=lambda index: evaluations[index].combined_objective_score,
    )
    selected = evaluations[selected_index]
    evaluations[selected_index] = PolicyEvaluation(
        policy=selected.policy,
        utility_score=selected.utility_score,
        combined_objective_score=selected.combined_objective_score,
        security_constraint_satisfied=selected.security_constraint_satisfied,
        admissible=selected.admissible,
        selected=True,
        reason=selected.reason,
    )

    if not constraint_satisfied:
        reason = (
            f"{selected.policy} selected as a protective fallback: effective "
            f"security risk {temporal_risk.effective_security_risk:.2f} "
            f"exceeds R_MAX ({r_max:.2f}), so every ordinary QoS policy was "
            "rejected. "
            f"{temporal_risk.explanation}"
        )
    else:
        reason = (
            f"{selected.policy} selected with QoS utility {qos_utility:.2f}, "
            f"effective security risk "
            f"{temporal_risk.effective_security_risk:.2f} within R_MAX "
            f"({r_max:.2f}), and combined objective "
            f"{selected.combined_objective_score:.2f}. "
            f"{temporal_risk.explanation}"
        )

    return RiskAwareDecision(
        qos_utility=qos_utility,
        security_risk=security_risk,
        combined_objective_score=selected.combined_objective_score,
        r_max=r_max,
        security_constraint_satisfied=constraint_satisfied,
        selected_policy=selected.policy,
        reason=reason,
        utility_factors=utility_factors,
        evaluations=tuple(evaluations),
        raw_security_risk=security_risk,
        smoothed_threat=temporal_state.smoothed_threat,
        threat_trend=temporal_state.trend,
        temporal_adjustment=temporal_risk.temporal_adjustment,
        effective_security_risk=temporal_risk.effective_security_risk,
        risk_budget_status=temporal_risk.risk_budget_status,
        explanation=temporal_risk.explanation,
    )


def _validate_weights(
    weights: Mapping[str, float],
    expected_keys: set[str],
    label: str,
) -> None:
    if set(weights) != expected_keys:
        raise ValueError(
            f"{label} weights must have exactly these factors: {sorted(expected_keys)}"
        )
    if any(not isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError(f"{label} weights must be finite and non-negative.")
    if abs(sum(weights.values()) - 1.0) > 0.001:
        raise ValueError(f"{label} weights must sum to 1.0.")


def _finite_config_number(config: Mapping[str, Any], key: str) -> float:
    value = config[key]
    if not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"risk_aware.{key} must be a finite number.")
    return float(value)