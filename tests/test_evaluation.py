from src.decision_engine import make_decision
from src.evaluation import run_evaluation
from src.models import NetworkInput


def test_evaluation_preserves_adaptive_decision_and_static_comparison():
    scenario = {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 8,
        "bandwidth_available": 25,
        "application_priority": 9,
        "device_trust": 90,
        "latency": 80,
    }

    result = run_evaluation([scenario])[0]
    expected = make_decision(NetworkInput(**scenario))

    assert result["Scenario"] == "S1"
    assert result["Adaptive Score"] == expected.decision_score
    assert result["Adaptive Priority"] == expected.priority
    assert result["Adaptive Policy"] == expected.qos_policy
    assert result["Security Action"] == expected.security_action
    assert result["Static Priority"] == "NORMAL"
    assert result["Static Policy"] == "NORMAL"
    assert result["Adapted"] == (
        "Yes"
        if expected.priority != "NORMAL" or expected.qos_policy != "NORMAL"
        else "No"
    )
