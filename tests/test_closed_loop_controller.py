from dataclasses import dataclass
from typing import Any

import pytest

from src import closed_loop_controller
from src.models import DecisionResult, NetworkInput
from src.network_telemetry import NetworkTelemetry
from src.qos_enforcer import QosEnforcementResult


@pytest.fixture
def pre_telemetry():
    return NetworkTelemetry(
        interface="s1-eth3",
        qdisc_sent_bytes=1_000,
        qdisc_sent_packets=10,
        qdisc_dropped_packets=0,
        qdisc_overlimits=0,
        qdisc_backlog_bytes=0,
        qdisc_backlog_packets=0,
        htb_configured_rate="10Mbit",
        interface_rx_bytes=900,
        interface_rx_packets=9,
        interface_rx_errors=0,
        interface_rx_drops=0,
        interface_tx_bytes=1_000,
        interface_tx_packets=10,
        interface_tx_errors=0,
        interface_tx_drops=0,
    )


@pytest.fixture
def post_telemetry(pre_telemetry):
    return NetworkTelemetry(
        **{
            **pre_telemetry.to_dict(),
            "qdisc_sent_bytes": 2_000,
            "qdisc_sent_packets": 20,
        }
    )


@pytest.fixture
def decision_result():
    return DecisionResult(
        decision_score=72,
        priority="HIGH",
        qos_policy="HIGH PRIORITY",
        bandwidth_allocation=6.0,
        queue="High Priority Queue",
        security_action="ALLOW",
        reason="test decision",
        factor_contributions={},
        normalized_factors={},
        dynamic_weights={},
    )


@dataclass(frozen=True)
class TelemetryCall:
    interface: str
    snapshot: NetworkTelemetry


def install_mocks(
    monkeypatch,
    pre_telemetry: NetworkTelemetry,
    decision_result: DecisionResult,
    *,
    post_telemetry: NetworkTelemetry | None = None,
) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {
        "telemetry": [],
        "adapter": [],
        "decision": [],
        "enforcement": [],
    }
    snapshots = [pre_telemetry]
    if post_telemetry is not None:
        snapshots.append(post_telemetry)

    def collect(interface: str) -> NetworkTelemetry:
        snapshot = snapshots.pop(0)
        calls["telemetry"].append(TelemetryCall(interface, snapshot))
        return snapshot

    def adapt(telemetry: NetworkTelemetry, **kwargs: Any) -> NetworkInput:
        calls["adapter"].append((telemetry, kwargs))
        return NetworkInput(
            traffic_type=kwargs["traffic_type"],
            threat_level=kwargs["threat_level"],
            congestion=0,
            bandwidth_available=10,
            application_priority=kwargs["application_priority"],
            device_trust=kwargs["device_trust"],
            latency=kwargs["measured_rtt_ms"],
        )

    def decide(network_input: NetworkInput) -> DecisionResult:
        calls["decision"].append(network_input)
        return decision_result

    def enforce(
        interface: str,
        result: DecisionResult,
        capacity: float,
        *,
        enabled: bool,
    ) -> QosEnforcementResult:
        calls["enforcement"].append((interface, result, capacity, enabled))
        return QosEnforcementResult(
            interface=interface,
            policy=result.qos_policy,
            requested_rate_mbps=result.bandwidth_allocation,
            class_id="5:1",
            command=("tc", "class", "change"),
        )

    monkeypatch.setattr(
        closed_loop_controller, "collect_network_telemetry", collect
    )
    monkeypatch.setattr(
        closed_loop_controller, "network_input_from_telemetry", adapt
    )
    monkeypatch.setattr(closed_loop_controller, "make_decision", decide)
    monkeypatch.setattr(closed_loop_controller, "apply_qos_policy", enforce)
    return calls


def call_controller(*, interface="s1-eth3", enforce=False, capacity=10):
    return closed_loop_controller.run_closed_loop(
        interface=interface,
        measured_rtt_ms=30.5,
        traffic_type="Video Call",
        application_priority=9,
        threat_level=2,
        device_trust=90,
        configured_capacity_mbps=capacity,
        enforce=enforce,
    )


def test_dry_run_collects_decides_and_does_not_enforce(
    monkeypatch, pre_telemetry, decision_result
):
    calls = install_mocks(monkeypatch, pre_telemetry, decision_result)

    result = call_controller()

    assert result.pre_telemetry is pre_telemetry
    assert result.decision_result is decision_result
    assert result.enforcement_result is None
    assert result.post_telemetry is None
    assert calls["telemetry"] == [TelemetryCall("s1-eth3", pre_telemetry)]
    assert calls["decision"] == [result.network_input]
    assert calls["enforcement"] == []


def test_enforce_mode_applies_once_and_returns_both_snapshots(
    monkeypatch, pre_telemetry, post_telemetry, decision_result
):
    calls = install_mocks(
        monkeypatch,
        pre_telemetry,
        decision_result,
        post_telemetry=post_telemetry,
    )

    result = call_controller(enforce=True, capacity=10)

    assert result.pre_telemetry is pre_telemetry
    assert result.post_telemetry is post_telemetry
    assert result.decision_result is decision_result
    assert result.enforcement_result is not None
    assert calls["telemetry"] == [
        TelemetryCall("s1-eth3", pre_telemetry),
        TelemetryCall("s1-eth3", post_telemetry),
    ]
    assert calls["enforcement"] == [
        ("s1-eth3", decision_result, 10, True)
    ]
    assert len(calls["enforcement"]) == 1


def test_adapter_and_decision_receive_expected_values(
    monkeypatch, pre_telemetry, decision_result
):
    calls = install_mocks(monkeypatch, pre_telemetry, decision_result)

    result = closed_loop_controller.run_closed_loop(
        interface="s2-eth1",
        measured_rtt_ms=18.25,
        traffic_type="Web Browsing",
        application_priority=6,
        threat_level=3,
        device_trust=82,
        configured_capacity_mbps=10,
    )

    assert calls["telemetry"][0].interface == "s2-eth1"
    source_snapshot, adapter_kwargs = calls["adapter"][0]
    assert source_snapshot is pre_telemetry
    assert adapter_kwargs == {
        "measured_rtt_ms": 18.25,
        "traffic_type": "Web Browsing",
        "application_priority": 6,
        "threat_level": 3,
        "device_trust": 82,
    }
    assert isinstance(result.network_input, NetworkInput)
    assert result.network_input.latency == 18.25
    assert result.network_input.traffic_type == "Web Browsing"
    assert calls["decision"] == [result.network_input]


def test_enforcement_error_is_propagated(monkeypatch, pre_telemetry, decision_result):
    install_mocks(monkeypatch, pre_telemetry, decision_result)

    def fail_enforcement(*args, **kwargs):
        raise RuntimeError("enforcement rejected by tc")

    monkeypatch.setattr(
        closed_loop_controller, "apply_qos_policy", fail_enforcement
    )

    with pytest.raises(RuntimeError, match="enforcement rejected"):
        call_controller(enforce=True)


@pytest.mark.parametrize("enforce", [None, 1, "true"])
def test_enforce_requires_a_boolean(monkeypatch, enforce):
    with pytest.raises(TypeError, match="enforce must be a boolean"):
        call_controller(enforce=enforce)
