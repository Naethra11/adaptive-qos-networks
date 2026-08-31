from typing import Dict


def select_policy(
    decision_score: float,
    threat_level: float,
    thresholds: Dict[str, float],
    security_thresholds: Dict[str, float],
) -> Dict[str, str]:
    """
    Select an adaptive QoS policy based on the decision score
    and security condition.

    Security has priority over normal QoS classification.
    """

    # ---------------------------------------------------------
    # SECURITY OVERRIDE
    # ---------------------------------------------------------

    if threat_level >= security_thresholds["quarantine"]:
        return {
            "priority": "RESTRICTED",
            "qos_policy": "QUARANTINED",
            "queue": "Security Queue",
            "security_action": "QUARANTINE",
        }

    if threat_level >= security_thresholds["restrict"]:
        return {
            "priority": "LOW",
            "qos_policy": "RATE LIMITED",
            "queue": "Restricted Queue",
            "security_action": "RESTRICT",
        }

    if threat_level >= security_thresholds["monitor"]:
        security_action = "MONITOR"
    else:
        security_action = "ALLOW"

    # ---------------------------------------------------------
    # NORMAL QoS CLASSIFICATION
    # ---------------------------------------------------------

    if decision_score >= thresholds["critical"]:
        priority = "CRITICAL"
        qos_policy = "CRITICAL PRIORITY"
        queue = "Priority Queue"

    elif decision_score >= thresholds["high"]:
        priority = "HIGH"
        qos_policy = "HIGH PRIORITY"
        queue = "High Priority Queue"

    elif decision_score >= thresholds["normal"]:
        priority = "NORMAL"
        qos_policy = "NORMAL"
        queue = "Normal Queue"

    else:
        priority = "LOW"
        qos_policy = "LOW / RATE LIMITED"
        queue = "Low Priority Queue"

    return {
        "priority": priority,
        "qos_policy": qos_policy,
        "queue": queue,
        "security_action": security_action,
    }