from typing import Dict


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Restrict a value to a fixed range."""
    return max(minimum, min(value, maximum))


def normalize_0_to_10(value: float) -> float:
    """Convert a 0-10 value to 0-100."""
    return clamp(value, 0, 10) * 10


def normalize_0_to_100(value: float) -> float:
    """Ensure a 0-100 value remains in range."""
    return clamp(value, 0, 100)


def normalize_bandwidth(
    bandwidth_mbps: float,
    reference_bandwidth_mbps: float = 100.0
) -> float:
    """
    Convert available bandwidth to a 0-100 score.

    Example:
    50 Mbps out of a 100 Mbps reference = 50.
    """
    if reference_bandwidth_mbps <= 0:
        raise ValueError("Reference bandwidth must be greater than 0.")

    score = (bandwidth_mbps / reference_bandwidth_mbps) * 100
    return clamp(score, 0, 100)


def normalize_latency(
    latency_ms: float,
    max_latency_ms: float = 300.0
) -> float:
    """
    Convert latency into a quality score.

    Lower latency is better:
    0 ms   -> 100
    300 ms -> 0
    """
    if max_latency_ms <= 0:
        raise ValueError("Maximum latency must be greater than 0.")

    latency_ms = clamp(latency_ms, 0, max_latency_ms)

    score = 100 - ((latency_ms / max_latency_ms) * 100)
    return clamp(score, 0, 100)


def normalize_security(threat_level: float) -> float:
    """
    Convert threat level into a security score.

    Low threat is good:
    Threat 0  -> Security score 100
    Threat 10 -> Security score 0
    """
    threat_level = clamp(threat_level, 0, 10)
    return 100 - (threat_level * 10)


def normalize_inputs(
    threat_level: float,
    congestion: float,
    bandwidth_available: float,
    application_priority: float,
    device_trust: float,
    latency: float,
    reference_bandwidth_mbps: float = 100.0,
    max_latency_ms: float = 300.0
) -> Dict[str, float]:
    """
    Normalize all numeric decision factors to a 0-100 scale.
    """

    return {
        "threat_security": normalize_security(threat_level),
        "congestion": normalize_0_to_10(congestion),
        "bandwidth": normalize_bandwidth(
            bandwidth_available,
            reference_bandwidth_mbps
        ),
        "application_priority": normalize_0_to_10(
            application_priority
        ),
        "device_trust": normalize_0_to_100(device_trust),
        "latency": normalize_latency(
            latency,
            max_latency_ms
        )
    }