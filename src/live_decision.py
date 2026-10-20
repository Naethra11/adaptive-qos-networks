"""Run the existing decision engine from a read-only telemetry snapshot."""

from src.decision_engine import make_decision
from src.models import DecisionResult
from src.network_telemetry import collect_network_telemetry
from src.telemetry_adapter import network_input_from_telemetry


def run_live_decision(
    interface: str,
    measured_rtt_ms: float,
    traffic_type: str,
    application_priority: float,
    threat_level: float,
    device_trust: float,
) -> DecisionResult:
    """Collect one telemetry snapshot and pass it through the existing engine.

    The supplied RTT and application/security context are passed through the
    telemetry adapter unchanged. Collection, validation, and decision errors
    propagate to the caller; this function does not synthesize fallback data.
    """
    telemetry = collect_network_telemetry(interface)
    network_input = network_input_from_telemetry(
        telemetry,
        measured_rtt_ms=measured_rtt_ms,
        traffic_type=traffic_type,
        application_priority=application_priority,
        threat_level=threat_level,
        device_trust=device_trust,
    )
    return make_decision(network_input)
