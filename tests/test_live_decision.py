from dataclasses import replace

import pytest

from src import live_decision
from src.decision_engine import make_decision
from src.models import DecisionResult, NetworkInput
from src.network_telemetry import NetworkTelemetry


@pytest.fixture
def telemetry():
    return NetworkTelemetry(
        interface="s1-eth3",
        qdisc_sent_bytes=12_000,
        qdisc_sent_packets=100,
        qdisc_dropped_packets=0,
        qdisc_overlimits=0,
        qdisc_backlog_bytes=0,
        qdisc_backlog_packets=0,
        htb_configured_rate="10Mbit",
        interface_rx_bytes=11_000,
        interface_rx_packets=100,
        interface_rx_errors=0,
        interface_rx_drops=0,
        interface_tx_bytes=12_000,
        interface_tx_packets=100,
        interface_tx_errors=0,
        interface_tx_drops=0,
    )


def run(traffic, *, rtt=30, priority=9, threat=2, trust=90):
    return live_decision.run_live_decision(
        interface="s1-eth3",
        measured_rtt_ms=rtt,
        traffic_type=traffic,
        application_priority=priority,
        threat_level=threat,
        device_trust=trust,
    )


def test_normal_network_conditions_flow_to_existing_decision_engine(
    monkeypatch, telemetry
):
    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", lambda interface: telemetry
    )

    result = run("Web Browsing", rtt=45, priority=5)

    assert isinstance(result, DecisionResult)
    assert result.decision_score >= 0


def test_congested_telemetry_is_adapted_before_decision(
    monkeypatch, telemetry
):
    congested = replace(
        telemetry,
        qdisc_sent_packets=100,
        qdisc_dropped_packets=20,
        qdisc_overlimits=30,
        qdisc_backlog_bytes=125_000,
        qdisc_backlog_packets=150,
    )
    monkeypatch.setattr(
        live_decision,
        "collect_network_telemetry",
        lambda interface: congested,
    )
    received = []
    real_make_decision = make_decision

    def capture_input(network_input):
        received.append(network_input)
        return real_make_decision(network_input)

    monkeypatch.setattr(live_decision, "make_decision", capture_input)

    result = run("Video Call")

    assert isinstance(result, DecisionResult)
    assert received[0].congestion > 0
    assert received[0].latency == 30


def test_high_threat_context_reaches_existing_engine(monkeypatch, telemetry):
    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", lambda interface: telemetry
    )
    received = []
    real_make_decision = make_decision

    def capture_input(network_input):
        received.append(network_input)
        return real_make_decision(network_input)

    monkeypatch.setattr(live_decision, "make_decision", capture_input)

    result = run("Suspicious Traffic", threat=9, trust=15)

    assert isinstance(result, DecisionResult)
    assert received[0].threat_level == 9
    assert received[0].device_trust == 15
    assert result.security_action == "QUARANTINE"


def test_high_priority_traffic_is_passed_through_to_engine(
    monkeypatch, telemetry
):
    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", lambda interface: telemetry
    )
    received = []
    real_make_decision = make_decision

    def capture_input(network_input):
        received.append(network_input)
        return real_make_decision(network_input)

    monkeypatch.setattr(live_decision, "make_decision", capture_input)

    result = run("Video Call", priority=10)

    assert isinstance(result, DecisionResult)
    assert received[0].application_priority == 10


def test_live_decision_calls_existing_engine_and_returns_its_result(
    monkeypatch, telemetry
):
    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", lambda interface: telemetry
    )
    expected = make_decision(
        NetworkInput(
            traffic_type="Video Call",
            threat_level=2,
            congestion=0,
            bandwidth_available=10,
            application_priority=9,
            device_trust=90,
            latency=30,
        )
    )
    calls = []

    def engine_spy(network_input):
        calls.append(network_input)
        return expected

    monkeypatch.setattr(live_decision, "make_decision", engine_spy)

    result = run("Video Call")

    assert len(calls) == 1
    assert isinstance(calls[0], NetworkInput)
    assert result is expected
    assert isinstance(result, DecisionResult)


def test_invalid_interface_error_propagates_without_engine_call(monkeypatch):
    def fail_collection(interface):
        raise ValueError(f"invalid interface: {interface}")

    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", fail_collection
    )
    monkeypatch.setattr(
        live_decision,
        "make_decision",
        lambda network_input: pytest.fail("engine must not be called"),
    )

    with pytest.raises(ValueError, match="invalid interface"):
        run("Video Call")


def test_invalid_telemetry_is_rejected_before_engine_call(monkeypatch, telemetry):
    invalid = replace(telemetry, qdisc_dropped_packets=-1)
    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", lambda interface: invalid
    )
    monkeypatch.setattr(
        live_decision,
        "make_decision",
        lambda network_input: pytest.fail("engine must not be called"),
    )

    with pytest.raises(ValueError, match="qdisc_dropped_packets"):
        run("Video Call")


def test_invalid_interface_is_forwarded_to_telemetry_collector(monkeypatch):
    received_interfaces = []

    def reject_interface(interface):
        received_interfaces.append(interface)
        raise ValueError("invalid interface")

    monkeypatch.setattr(
        live_decision, "collect_network_telemetry", reject_interface
    )

    with pytest.raises(ValueError, match="invalid interface"):
        live_decision.run_live_decision(
            interface="bad;interface",
            measured_rtt_ms=30,
            traffic_type="Video Call",
            application_priority=9,
            threat_level=2,
            device_trust=90,
        )
    assert received_interfaces == ["bad;interface"]
