from typing import Any, Dict, List

from src.models import NetworkInput
from src.decision_engine import make_decision


def run_adaptive_simulation(
    scenarios: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Run the Adaptive Smart QoS decision engine across
    a sequence of changing network conditions.

    Each scenario represents one point in time.
    """

    simulation_results = []

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

        result = make_decision(network_input)

        simulation_results.append({
            "Time Step": f"T{index}",
            "Traffic Type": scenario["traffic_type"],
            "Threat": scenario["threat_level"],
            "Congestion": scenario["congestion"],
            "Bandwidth (Mbps)": scenario["bandwidth_available"],
            "Latency (ms)": scenario["latency"],
            "Decision Score": result.decision_score,
            "Priority": result.priority,
            "QoS Policy": result.qos_policy,
            "Bandwidth Allocation": result.bandwidth_allocation,
            "Security Action": result.security_action,
            "Reason": result.reason,
        })

    return simulation_results