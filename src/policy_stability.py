"""Independent policy-switching cost, hysteresis, and stability metrics."""

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


POLICY_ORDER = (
    "CRITICAL PRIORITY",
    "HIGH PRIORITY",
    "NORMAL",
    "LOW / RATE LIMITED",
    "QUARANTINED",
)
_ORDINARY_POLICIES = POLICY_ORDER[:-1]


@dataclass(frozen=True)
class StabilityObjective:
    """Stability-aware objective together with its switching-cost terms."""

    base_objective: float
    switching_cost: float
    switching_penalty: float
    stability_aware_objective: float
    switch_required: bool


def is_policy_switch_required(
    previous_policy: str | None,
    candidate_policy: str,
) -> bool:
    """Return whether a selected policy would differ from the previous one."""
    _validate_policy(candidate_policy, "candidate_policy")
    if previous_policy is None:
        return False
    _validate_policy(previous_policy, "previous_policy")
    return previous_policy != candidate_policy


def switching_cost(
    previous_policy: str | None,
    candidate_policy: str,
) -> float:
    """Return zero for no change, otherwise the configured unit transition cost."""
    return 1.0 if is_policy_switch_required(previous_policy, candidate_policy) else 0.0


def calculate_stability_aware_objective(
    qos_utility: float,
    policy_multiplier: float,
    risk_penalty_weight: float,
    security_risk: float,
    switching_penalty: float,
    previous_policy: str | None,
    candidate_policy: str,
    *,
    enabled: bool = True,
) -> StabilityObjective:
    """Calculate the Phase 4 objective without changing the Phase 2 objective."""
    values = {
        "qos_utility": qos_utility,
        "policy_multiplier": policy_multiplier,
        "risk_penalty_weight": risk_penalty_weight,
        "security_risk": security_risk,
        "switching_penalty": switching_penalty,
    }
    for name, value in values.items():
        _validate_finite(value, name)
    if min(qos_utility, policy_multiplier, risk_penalty_weight, switching_penalty) < 0:
        raise ValueError("Objective inputs and penalty weights must be non-negative.")

    base_objective = qos_utility * policy_multiplier - risk_penalty_weight * security_risk
    switch_required = is_policy_switch_required(previous_policy, candidate_policy)
    cost = switching_cost(previous_policy, candidate_policy) if enabled else 0.0
    penalty = switching_penalty * cost
    return StabilityObjective(
        base_objective=round(base_objective, 2),
        switching_cost=cost,
        switching_penalty=round(penalty, 2),
        stability_aware_objective=round(base_objective - penalty, 2),
        switch_required=switch_required,
    )


def apply_policy_hysteresis(
    candidate_policy: str,
    previous_policy: str | None,
    score: float,
    stability_config: Mapping[str, Any],
    *,
    effective_security_risk: float | None = None,
    r_max: float | None = None,
) -> str:
    """Apply configurable ordinary-policy hysteresis to a candidate.

    A risk-budget breach or an explicit QUARANTINED candidate is returned
    immediately; hysteresis can never delay security quarantine.
    """
    _validate_policy(candidate_policy, "candidate_policy")
    _validate_finite(score, "score")
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100.")

    if (effective_security_risk is None) != (r_max is None):
        raise ValueError(
            "effective_security_risk and r_max must either both be provided or both be omitted."
        )
    if effective_security_risk is not None and r_max is not None:
        _validate_finite(effective_security_risk, "effective_security_risk")
        _validate_finite(r_max, "r_max")
        if effective_security_risk > r_max:
            return "QUARANTINED"

    if candidate_policy == "QUARANTINED":
        return candidate_policy
    if candidate_policy not in _ORDINARY_POLICIES:
        raise ValueError(f"Unsupported ordinary policy: {candidate_policy}")

    hysteresis = stability_config["hysteresis"]
    if not stability_config["enabled"] or not hysteresis["enabled"]:
        return candidate_policy

    thresholds = _validated_hysteresis_thresholds(hysteresis)
    if previous_policy is None:
        return candidate_policy
    _validate_policy(previous_policy, "previous_policy")
    if previous_policy == "QUARANTINED":
        return candidate_policy

    if previous_policy == "CRITICAL PRIORITY":
        if candidate_policy != previous_policy and score >= thresholds["critical_exit"]:
            return previous_policy
        return candidate_policy

    if previous_policy == "HIGH PRIORITY":
        if candidate_policy == "CRITICAL PRIORITY":
            return (
                candidate_policy
                if score >= thresholds["critical_enter"]
                else previous_policy
            )
        if candidate_policy != previous_policy and score >= thresholds["high_exit"]:
            return previous_policy
        return candidate_policy

    if previous_policy == "NORMAL":
        if candidate_policy == "CRITICAL PRIORITY":
            return (
                candidate_policy
                if score >= thresholds["critical_enter"]
                else previous_policy
            )
        if candidate_policy == "HIGH PRIORITY":
            return (
                candidate_policy
                if score >= thresholds["high_enter"]
                else previous_policy
            )
        if candidate_policy != previous_policy and score >= thresholds["normal_exit"]:
            return previous_policy
        return candidate_policy

    if previous_policy == "LOW / RATE LIMITED":
        if candidate_policy == "CRITICAL PRIORITY":
            return (
                candidate_policy
                if score >= thresholds["critical_enter"]
                else previous_policy
            )
        if candidate_policy == "HIGH PRIORITY":
            return (
                candidate_policy
                if score >= thresholds["high_enter"]
                else previous_policy
            )
        if candidate_policy == "NORMAL":
            return (
                candidate_policy
                if score >= thresholds["normal_enter"]
                else previous_policy
            )
        return candidate_policy

    return candidate_policy


def count_policy_switches(policy_sequence: Sequence[str]) -> int:
    """Count adjacent policy changes in a sequence of decisions."""
    for policy in policy_sequence:
        _validate_policy(policy, "policy")
    return sum(
        previous != current
        for previous, current in zip(policy_sequence, policy_sequence[1:])
    )


def calculate_policy_switch_rate(
    number_of_decisions: int,
    number_of_policy_changes: int,
) -> float:
    """Calculate PSR; returns 0.0 when there are no decisions."""
    _validate_counts(number_of_decisions, number_of_policy_changes)
    if number_of_decisions == 0:
        return 0.0
    return round(number_of_policy_changes / number_of_decisions, 4)


def calculate_policy_stability_index(
    number_of_decisions: int,
    number_of_policy_changes: int,
) -> float:
    """Calculate PSI; with no decisions, returns the neutral-safe value 1.0."""
    _validate_counts(number_of_decisions, number_of_policy_changes)
    if number_of_decisions == 0:
        return 1.0
    return round(1 - number_of_policy_changes / number_of_decisions, 4)


def _validated_hysteresis_thresholds(
    hysteresis: Mapping[str, Any],
) -> dict[str, float]:
    names = (
        "high_enter",
        "high_exit",
        "critical_enter",
        "critical_exit",
        "normal_enter",
        "normal_exit",
    )
    thresholds = {name: _validate_finite(hysteresis[name], name) for name in names}
    if any(not 0 <= value <= 100 for value in thresholds.values()):
        raise ValueError("Hysteresis thresholds must be between 0 and 100.")
    if not (
        thresholds["high_exit"] <= thresholds["high_enter"]
        and thresholds["critical_exit"] <= thresholds["critical_enter"]
        and thresholds["normal_exit"] <= thresholds["normal_enter"]
        and thresholds["normal_enter"] <= thresholds["high_enter"]
        and thresholds["high_enter"] <= thresholds["critical_enter"]
    ):
        raise ValueError("Hysteresis exit/entry thresholds are inconsistently ordered.")
    return thresholds


def _validate_policy(policy: str, name: str) -> None:
    if policy not in POLICY_ORDER:
        raise ValueError(f"{name} must be one of {', '.join(POLICY_ORDER)}.")


def _validate_finite(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    return float(value)


def _validate_counts(number_of_decisions: int, number_of_policy_changes: int) -> None:
    counts = {
        "number_of_decisions": number_of_decisions,
        "number_of_policy_changes": number_of_policy_changes,
    }
    for name, value in counts.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if value < 0:
            raise ValueError("Decision and policy-change counts cannot be negative.")
    if number_of_policy_changes > number_of_decisions:
        raise ValueError("Policy changes cannot exceed the number of decisions.")
