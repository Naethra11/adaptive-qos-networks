from pathlib import Path
from typing import Any, Dict

import yaml

from src.models import NetworkInput, DecisionResult
from src.normalization import normalize_inputs
from src.scoring import (
    calculate_decision_score,
    calculate_factor_contributions
)
from src.policy_selector import select_policy
from src.dynamic_weights import get_dynamic_weights 
# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config() -> Dict[str, Any]:
    """Load weights, thresholds and traffic scores from YAML."""

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


# ---------------------------------------------------------
# TRAFFIC TYPE SCORE
# ---------------------------------------------------------

def get_traffic_type_score(
    traffic_type: str,
    traffic_type_scores: Dict[str, float]
) -> float:
    """
    Return the importance score associated with a traffic type.
    """

    if traffic_type in traffic_type_scores:
        return float(traffic_type_scores[traffic_type])

    # Unknown traffic is treated conservatively.
    return 30.0


# ---------------------------------------------------------
# BANDWIDTH ALLOCATION
# ---------------------------------------------------------

def calculate_bandwidth_allocation(
    policy: str,
    available_bandwidth: float,
    application_priority: float,
    congestion: float
) -> float:
    """
    Recommend a bandwidth allocation in Mbps.

    This is currently a simulation-level recommendation.
    It does not directly control a real network interface.
    """

    if available_bandwidth <= 0:
        return 0.0

    if policy == "CRITICAL PRIORITY":
        percentage = 0.80

    elif policy == "HIGH PRIORITY":
        percentage = 0.60

    elif policy == "NORMAL":
        percentage = 0.40

    elif policy == "LOW / RATE LIMITED":
        percentage = 0.20

    else:
        # Restricted / quarantined traffic
        percentage = 0.05

    # Under severe congestion, resource allocation becomes
    # more conservative.
    if congestion >= 8:
        percentage *= 0.90

    allocation = available_bandwidth * percentage

    return round(allocation, 2)


# ---------------------------------------------------------
# REASON GENERATOR
# ---------------------------------------------------------

def generate_reason(
    traffic_type: str,
    threat_level: float,
    congestion: float,
    application_priority: float,
    device_trust: float,
    latency: float,
    policy: str,
    security_action: str
) -> str:
    """Generate a human-readable explanation of the decision."""

    if security_action == "QUARANTINE":
        return (
            f"{traffic_type} was assigned a security restriction because "
            f"the detected threat level is {threat_level}/10. "
            f"Security override takes precedence over normal QoS priority."
        )

    if security_action == "RESTRICT":
        return (
            f"{traffic_type} was rate limited because the threat level "
            f"is {threat_level}/10. Security restrictions prevent "
            f"normal high-priority QoS treatment."
        )

    if policy == "CRITICAL PRIORITY":
        return (
            f"{traffic_type} received critical priority because of its "
            f"high application priority ({application_priority}/10), "
            f"combined with current network conditions."
        )

    if policy == "HIGH PRIORITY":
        return (
            f"{traffic_type} received high priority because its "
            f"application priority is {application_priority}/10 and "
            f"the current network conditions favor prioritized traffic."
        )

    if policy == "NORMAL":
        return (
            f"{traffic_type} received normal QoS treatment. "
            f"The combined network, security and application factors "
            f"did not justify critical or restricted treatment."
        )

    return (
        f"{traffic_type} received low/rate-limited treatment based on "
        f"the combined decision factors. Current congestion is "
        f"{congestion}/10 and device trust is {device_trust}/100."
    )


# ---------------------------------------------------------
# MAIN DECISION FUNCTION
# ---------------------------------------------------------

def make_decision(network_input: NetworkInput) -> DecisionResult:
    """
    Main entry point for the Multi-Factor Decision Engine.
    """

    # 1. Validate input
    network_input.validate()

    # 2. Load configuration
    config = load_config()

    policy_thresholds = config["policy_thresholds"]
    security_thresholds = config["security_thresholds"]
    traffic_type_scores = config["traffic_type_scores"]

    # 3. Normalize numeric factors
    normalized = normalize_inputs(
        threat_level=network_input.threat_level,
        congestion=network_input.congestion,
        bandwidth_available=network_input.bandwidth_available,
        application_priority=network_input.application_priority,
        device_trust=network_input.device_trust,
        latency=network_input.latency,
    )

    # 4. Add traffic type score
    normalized["traffic_type"] = get_traffic_type_score(
        network_input.traffic_type,
        traffic_type_scores
    )

    # 5. Generate dynamic weights
    dynamic_weights = get_dynamic_weights(
        threat_level=network_input.threat_level,
        congestion=network_input.congestion,
        latency=network_input.latency,
    )

    # 6. Calculate weighted decision score
    decision_score = calculate_decision_score(
        normalized_factors=normalized,
        weights=dynamic_weights
    )
    factor_contributions = calculate_factor_contributions(
    normalized_factors=normalized,
    weights=dynamic_weights
)
    # 7. Select QoS policy
    policy_result = select_policy(
        decision_score=decision_score,
        threat_level=network_input.threat_level,
        thresholds=policy_thresholds,
        security_thresholds=security_thresholds,
    )

    # 8. Calculate recommended bandwidth
    bandwidth_allocation = calculate_bandwidth_allocation(
        policy=policy_result["qos_policy"],
        available_bandwidth=network_input.bandwidth_available,
        application_priority=network_input.application_priority,
        congestion=network_input.congestion,
    )

    # 9. Generate explanation
    reason = generate_reason(
        traffic_type=network_input.traffic_type,
        threat_level=network_input.threat_level,
        congestion=network_input.congestion,
        application_priority=network_input.application_priority,
        device_trust=network_input.device_trust,
        latency=network_input.latency,
        policy=policy_result["qos_policy"],
        security_action=policy_result["security_action"],
    )

    # 10. Return final decision
    return DecisionResult(
    decision_score=decision_score,
    priority=policy_result["priority"],
    qos_policy=policy_result["qos_policy"],
    bandwidth_allocation=bandwidth_allocation,
    queue=policy_result["queue"],
    security_action=policy_result["security_action"],
    reason=reason,
    factor_contributions=factor_contributions,
    normalized_factors=normalized,
    dynamic_weights=dynamic_weights,
)