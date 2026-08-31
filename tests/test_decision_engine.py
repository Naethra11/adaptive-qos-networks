from src.models import NetworkInput
from src.decision_engine import make_decision


def test_high_priority_video_call():
    traffic = NetworkInput(
        traffic_type="Video Call",
        threat_level=2,
        congestion=8,
        bandwidth_available=25,
        application_priority=9,
        device_trust=90,
        latency=80,
    )

    result = make_decision(traffic)

    assert result.priority in ["HIGH", "CRITICAL"]
    assert result.security_action == "ALLOW"
    assert result.decision_score >= 0
    assert result.decision_score <= 100


def test_high_threat_traffic_is_restricted():
    traffic = NetworkInput(
        traffic_type="Suspicious Traffic",
        threat_level=9,
        congestion=5,
        bandwidth_available=50,
        application_priority=10,
        device_trust=20,
        latency=100,
    )

    result = make_decision(traffic)

    # Security must override application priority.
    assert result.security_action == "QUARANTINE"
    assert result.priority == "RESTRICTED"
    assert result.qos_policy == "QUARANTINED"


def test_low_priority_file_download():
    traffic = NetworkInput(
        traffic_type="File Download",
        threat_level=1,
        congestion=3,
        bandwidth_available=80,
        application_priority=3,
        device_trust=80,
        latency=150,
    )

    result = make_decision(traffic)

    assert result.decision_score >= 0
    assert result.decision_score <= 100
    assert result.security_action == "ALLOW"


def test_untrusted_device():
    traffic = NetworkInput(
        traffic_type="Web Browsing",
        threat_level=3,
        congestion=5,
        bandwidth_available=50,
        application_priority=5,
        device_trust=10,
        latency=100,
    )

    result = make_decision(traffic)

    assert result.decision_score >= 0
    assert result.decision_score <= 100


def test_low_bandwidth():
    traffic = NetworkInput(
        traffic_type="Video Call",
        threat_level=1,
        congestion=8,
        bandwidth_available=5,
        application_priority=9,
        device_trust=90,
        latency=80,
    )

    result = make_decision(traffic)

    assert result.bandwidth_allocation >= 0
    assert result.bandwidth_allocation <= 5


def test_high_latency():
    traffic = NetworkInput(
        traffic_type="Voice Call",
        threat_level=1,
        congestion=4,
        bandwidth_available=50,
        application_priority=9,
        device_trust=90,
        latency=280,
    )

    result = make_decision(traffic)

    assert result.decision_score >= 0
    assert result.decision_score <= 100


def test_result_always_has_policy():
    traffic = NetworkInput(
        traffic_type="Gaming",
        threat_level=2,
        congestion=4,
        bandwidth_available=40,
        application_priority=8,
        device_trust=75,
        latency=60,
    )

    result = make_decision(traffic)

    valid_policies = [
        "CRITICAL PRIORITY",
        "HIGH PRIORITY",
        "NORMAL",
        "LOW / RATE LIMITED",
        "QUARANTINED",
    ]

    assert result.qos_policy in valid_policies