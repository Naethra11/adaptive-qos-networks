from typing import Any, Dict, List

from src.models import NetworkInput
from src.decision_engine import make_decision


def run_evaluation(
    scenarios: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compare the adaptive QoS decision engine
    against a fixed static QoS baseline.
    """

    results = []

    for index, scenario in enumerate(scenarios, start=1):

        network_input = NetworkInput(
            traffic_type=scenario["traffic_type"],
            threat_level=scenario["threat_level"],
            congestion=scenario["congestion"],
            bandwidth_available=scenario["bandwidth_available"],
            application_priority=scenario["application_priority"],
            device_trust=scenario["device_trust"],
            latency=scenario["latency"],
        )

        adaptive_result = make_decision(network_input)

        # Static QoS baseline:
        # A fixed NORMAL policy is applied regardless
        # of changing network conditions.
        static_priority = "NORMAL"
        static_policy = "NORMAL"

        # Check whether the adaptive system changed
        # its decision according to the conditions.
        adapted = (
            adaptive_result.priority != static_priority
            or adaptive_result.qos_policy != static_policy
        )

        results.append({
            "Scenario": f"S{index}",
            "Traffic Type": scenario["traffic_type"],
            "Threat Level": scenario["threat_level"],
            "Congestion": scenario["congestion"],
            "Bandwidth (Mbps)": scenario["bandwidth_available"],
            "Latency (ms)": scenario["latency"],
            "Adaptive Score": adaptive_result.decision_score,
            "Adaptive Priority": adaptive_result.priority,
            "Adaptive Policy": adaptive_result.qos_policy,
            "Security Action": adaptive_result.security_action,
            "Static Priority": static_priority,
            "Static Policy": static_policy,
            "Adapted": "Yes" if adapted else "No",
        })

    return results