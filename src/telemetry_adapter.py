"""Convert read-only Mininet telemetry into the decision engine input model.

The qdisc and interface counters in :class:`NetworkTelemetry` are cumulative
since their counters were last reset. They are never interpreted as rates.
Only qdisc backlog is a current queue-depth observation; the configured HTB
rate is a configured capacity, not an estimate of residual free bandwidth.
"""

import re
from math import isfinite

from src.models import NetworkInput
from src.network_telemetry import NetworkTelemetry


_HTB_RATE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)([kmg]?bit)$", re.IGNORECASE)
_BACKLOG_WINDOW_SECONDS = 0.1


def network_input_from_telemetry(
    telemetry: NetworkTelemetry,
    *,
    measured_rtt_ms: float,
    traffic_type: str,
    application_priority: float,
    threat_level: float,
    device_trust: float,
) -> NetworkInput:
    """Build a validated ``NetworkInput`` from telemetry and explicit context.

    ``bandwidth_available`` is populated from the root HTB configured rate in
    decimal Mbps. No residual-bandwidth estimate is made because this function
    receives only a single cumulative-counter snapshot, not counter deltas over
    a measured interval.

    Congestion is a deterministic 0–10 prototype estimate:

    * backlog pressure is backlog bytes divided by 100 ms of configured rate;
    * historical drop incidence is drops / (sent packets + drops);
    * historical overlimit incidence is overlimits / (sent packets + overlimits).

    The estimate is ``10 * (0.60 * backlog_pressure + 0.20 * drop_incidence
    + 0.20 * overlimit_incidence)``. Each component is clamped to [0, 1].
    Drop and overlimit counters remain distinct signals; overlimits are not
    treated as packet loss. This is an explainable prototype heuristic, not a
    standardized or instantaneous congestion metric.

    Traffic type, application priority, threat level, device trust, and RTT
    are explicit inputs because the telemetry collector does not measure them.
    """
    if not isinstance(telemetry, NetworkTelemetry):
        raise TypeError("telemetry must be a NetworkTelemetry instance.")
    _validate_telemetry_counters(telemetry)

    if not isinstance(traffic_type, str) or not traffic_type.strip():
        raise ValueError("traffic_type must be a non-empty string.")
    rtt = _finite_number(measured_rtt_ms, "measured_rtt_ms")
    if rtt < 0:
        raise ValueError("measured_rtt_ms cannot be negative.")

    available_bandwidth = _parse_htb_rate_mbps(telemetry.htb_configured_rate)
    congestion = _estimate_congestion(telemetry, available_bandwidth)
    network_input = NetworkInput(
        traffic_type=traffic_type,
        threat_level=_finite_number(threat_level, "threat_level"),
        congestion=congestion,
        bandwidth_available=available_bandwidth,
        application_priority=_finite_number(
            application_priority, "application_priority"
        ),
        device_trust=_finite_number(device_trust, "device_trust"),
        latency=rtt,
    )
    network_input.validate()
    return network_input


def _parse_htb_rate_mbps(rate: str) -> float:
    if not isinstance(rate, str):
        raise TypeError("htb_configured_rate must be a string.")
    match = _HTB_RATE_PATTERN.fullmatch(rate.strip())
    if match is None:
        raise ValueError(
            f"Unsupported HTB rate {rate!r}; expected a bit, kbit, Mbit, or Gbit value."
        )

    magnitude = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"bit": 1.0, "kbit": 1_000.0, "mbit": 1_000_000.0, "gbit": 1_000_000_000.0}[unit]
    rate_mbps = magnitude * multiplier / 1_000_000.0
    if not isfinite(rate_mbps) or rate_mbps <= 0:
        raise ValueError("htb_configured_rate must represent a positive finite rate.")
    return rate_mbps


def _estimate_congestion(
    telemetry: NetworkTelemetry,
    configured_rate_mbps: float,
) -> float:
    configured_bytes_per_second = configured_rate_mbps * 1_000_000 / 8
    backlog_budget_bytes = configured_bytes_per_second * _BACKLOG_WINDOW_SECONDS
    backlog_pressure = min(
        telemetry.qdisc_backlog_bytes / backlog_budget_bytes,
        1.0,
    )

    drop_denominator = telemetry.qdisc_sent_packets + telemetry.qdisc_dropped_packets
    drop_incidence = (
        telemetry.qdisc_dropped_packets / drop_denominator
        if drop_denominator
        else 0.0
    )
    overlimit_denominator = telemetry.qdisc_sent_packets + telemetry.qdisc_overlimits
    overlimit_incidence = (
        telemetry.qdisc_overlimits / overlimit_denominator
        if overlimit_denominator
        else 0.0
    )
    return round(
        10.0
        * (
            0.60 * backlog_pressure
            + 0.20 * drop_incidence
            + 0.20 * overlimit_incidence
        ),
        4,
    )


def _validate_telemetry_counters(telemetry: NetworkTelemetry) -> None:
    counter_fields = (
        "qdisc_sent_bytes",
        "qdisc_sent_packets",
        "qdisc_dropped_packets",
        "qdisc_overlimits",
        "qdisc_backlog_bytes",
        "qdisc_backlog_packets",
        "interface_rx_bytes",
        "interface_rx_packets",
        "interface_rx_errors",
        "interface_rx_drops",
        "interface_tx_bytes",
        "interface_tx_packets",
        "interface_tx_errors",
        "interface_tx_drops",
    )
    for name in counter_fields:
        value = getattr(telemetry, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"telemetry.{name} must be an integer counter.")
        if value < 0:
            raise ValueError(f"telemetry.{name} cannot be negative.")


def _finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    return float(value)
