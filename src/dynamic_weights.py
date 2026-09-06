from typing import Dict


def get_dynamic_weights(
    threat_level: float,
    congestion: float,
    latency: float
) -> Dict[str, float]:
    """
    Generate adaptive weights based on current network conditions.

    The returned weights correspond to all 7 decision factors
    used by the Multi-Factor Decision Engine.
    """

    # --------------------------------------------------
    # BASE WEIGHTS
    # --------------------------------------------------

    weights = {
        "application_priority": 0.25,
        "threat_security": 0.20,
        "congestion": 0.15,
        "bandwidth": 0.15,
        "traffic_type": 0.10,
        "device_trust": 0.10,
        "latency": 0.05,
    }

    # --------------------------------------------------
    # HIGH THREAT
    # --------------------------------------------------

    if threat_level >= 8:
        weights["threat_security"] += 0.15
        weights["device_trust"] += 0.05

        weights["application_priority"] -= 0.10
        weights["traffic_type"] -= 0.05
        weights["latency"] -= 0.05

    # --------------------------------------------------
    # HIGH CONGESTION
    # --------------------------------------------------

    elif congestion >= 8:
        weights["congestion"] += 0.10
        weights["latency"] += 0.05
        weights["application_priority"] += 0.05

        weights["traffic_type"] -= 0.05
        weights["device_trust"] -= 0.05
        weights["threat_security"] -= 0.05

    # --------------------------------------------------
    # HIGH LATENCY
    # --------------------------------------------------

    elif latency >= 150:
        weights["latency"] += 0.10
        weights["application_priority"] += 0.05
        weights["traffic_type"] += 0.05

        weights["bandwidth"] -= 0.05
        weights["device_trust"] -= 0.05
        weights["congestion"] -= 0.05

    # --------------------------------------------------
    # PREVENT NEGATIVE WEIGHTS
    # --------------------------------------------------

    weights = {
        factor: max(weight, 0.0)
        for factor, weight in weights.items()
    }

    # --------------------------------------------------
    # NORMALIZE WEIGHTS TO TOTAL 1.0
    # --------------------------------------------------

    total = sum(weights.values())

    if total == 0:
        raise ValueError("Dynamic weights cannot all be zero.")

    weights = {
        factor: weight / total
        for factor, weight in weights.items()
    }

    return weights