from dataclasses import replace

import pytest

from src.network_telemetry import NetworkTelemetry
from src.telemetry_adapter import network_input_from_telemetry


@pytest.fixture
def idle_telemetry():
    return NetworkTelemetry(
        interface="s1-eth3",
        qdisc_sent_bytes=0,
        qdisc_sent_packets=0,
        qdisc_dropped_packets=0,
        qdisc_overlimits=0,
        qdisc_backlog_bytes=0,
        qdisc_backlog_packets=0,
        htb_configured_rate="10Mbit",
        interface_rx_bytes=0,
        interface_rx_packets=0,
        interface_rx_errors=0,
        interface_rx_drops=0,
        interface_tx_bytes=0,
        interface_tx_packets=0,
        interface_tx_errors=0,
        interface_tx_drops=0,
    )


def adapt(telemetry, *, rtt=25.0):
    return network_input_from_telemetry(
        telemetry,
        measured_rtt_ms=rtt,
        traffic_type="Video Call",
        application_priority=8,
        threat_level=2,
        device_trust=90,
    )


def test_idle_telemetry_maps_to_zero_congestion(idle_telemetry):
    network_input = adapt(idle_telemetry)

    assert network_input.congestion == 0
    assert network_input.bandwidth_available == 10
    assert network_input.latency == 25
    assert network_input.traffic_type == "Video Call"
    assert network_input.application_priority == 8
    assert network_input.threat_level == 2
    assert network_input.device_trust == 90


def test_congested_telemetry_uses_backlog_and_distinct_counter_signals(
    idle_telemetry,
):
    telemetry = replace(
        idle_telemetry,
        qdisc_sent_packets=100,
        qdisc_dropped_packets=10,
        qdisc_overlimits=20,
        qdisc_backlog_bytes=125_000,
    )

    result = adapt(telemetry)

    # A 10 Mbps configured rate carries 125,000 bytes in the 100 ms
    # reference window, so backlog pressure saturates at 1.
    expected = 10 * (0.60 + 0.20 * (10 / 110) + 0.20 * (20 / 120))
    assert result.congestion == pytest.approx(expected, abs=0.0001)


def test_zero_or_empty_counters_produce_zero_congestion(idle_telemetry):
    assert adapt(idle_telemetry).congestion == 0


def test_high_qdisc_drops_increase_drop_signal_without_overlimits(idle_telemetry):
    telemetry = replace(
        idle_telemetry,
        qdisc_sent_packets=100,
        qdisc_dropped_packets=100,
    )

    result = adapt(telemetry)

    assert result.congestion == 1


def test_high_overlimits_are_a_separate_signal_not_packet_loss(idle_telemetry):
    telemetry = replace(
        idle_telemetry,
        qdisc_sent_packets=100,
        qdisc_overlimits=100,
    )

    result = adapt(telemetry)

    assert result.congestion == 1
    assert telemetry.qdisc_dropped_packets == 0


def test_measured_rtt_is_preserved_and_changes_with_input(idle_telemetry):
    assert adapt(idle_telemetry, rtt=12).latency == 12
    assert adapt(idle_telemetry, rtt=180).latency == 180


@pytest.mark.parametrize(
    ("rate", "expected_mbps"),
    [
        ("10Mbit", 10),
        ("2500Kbit", 2.5),
        ("1.5Gbit", 1500),
        ("500000bit", 0.5),
    ],
)
def test_configured_htb_rate_maps_to_decimal_mbps(
    idle_telemetry, rate, expected_mbps
):
    result = adapt(replace(idle_telemetry, htb_configured_rate=rate))

    assert result.bandwidth_available == expected_mbps


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("qdisc_dropped_packets", -1, ValueError),
        ("qdisc_overlimits", 1.5, TypeError),
        ("interface_rx_bytes", True, TypeError),
    ],
)
def test_invalid_telemetry_counters_are_rejected(
    idle_telemetry, field, value, error
):
    with pytest.raises(error, match="telemetry"):
        adapt(replace(idle_telemetry, **{field: value}))


@pytest.mark.parametrize("rate", ["", "10Mbps", "0Mbit", "-1Mbit", "NaNMbit"])
def test_invalid_htb_rate_is_rejected(idle_telemetry, rate):
    with pytest.raises(ValueError, match="HTB rate|positive finite"):
        adapt(replace(idle_telemetry, htb_configured_rate=rate))


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"rtt": -1}, ValueError),
        ({"rtt": float("nan")}, ValueError),
    ],
)
def test_invalid_rtt_is_rejected(idle_telemetry, kwargs, error):
    with pytest.raises(error, match="measured_rtt_ms"):
        adapt(idle_telemetry, **kwargs)


def test_invalid_network_context_is_rejected(idle_telemetry):
    with pytest.raises(ValueError, match="Threat level"):
        network_input_from_telemetry(
            idle_telemetry,
            measured_rtt_ms=25,
            traffic_type="Video Call",
            application_priority=8,
            threat_level=11,
            device_trust=90,
        )
