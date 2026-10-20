"""Minimal orchestration for telemetry, decision-making, and opt-in QoS."""

from dataclasses import dataclass

from src.decision_engine import make_decision
from src.models import DecisionResult, NetworkInput
from src.network_telemetry import NetworkTelemetry, collect_network_telemetry
from src.qos_enforcer import QosEnforcementResult, apply_qos_policy
from src.telemetry_adapter import network_input_from_telemetry


@dataclass(frozen=True)
class ClosedLoopResult:
    """Inputs, decision, and telemetry observed around one controller run."""

    pre_telemetry: NetworkTelemetry
    network_input: NetworkInput
    decision_result: DecisionResult
    enforcement_result: QosEnforcementResult | None
    post_telemetry: NetworkTelemetry | None


def run_closed_loop(
    interface: str,
    measured_rtt_ms: float,
    traffic_type: str,
    application_priority: float,
    threat_level: float,
    device_trust: float,
    configured_capacity_mbps: float,
    enforce: bool = False,
) -> ClosedLoopResult:
    """Run one telemetry-to-decision cycle and optionally enforce its result.

    In dry-run mode, this function performs read-only telemetry collection and
    decision evaluation only; ``enforcement_result`` and ``post_telemetry`` are
    ``None``. When ``enforce`` is true, the existing enforcer is called once
    with its explicit opt-in enabled, then a fresh post-enforcement telemetry
    snapshot is collected. Enforcement and collection failures propagate.

    The existing adapter and baseline ``make_decision`` API are used directly
    so the controller can retain the exact pre-decision snapshot without
    collecting telemetry a second time through ``run_live_decision``.
    """
    if not isinstance(enforce, bool):
        raise TypeError("enforce must be a boolean.")

    pre_telemetry = collect_network_telemetry(interface)
    network_input = network_input_from_telemetry(
        pre_telemetry,
        measured_rtt_ms=measured_rtt_ms,
        traffic_type=traffic_type,
        application_priority=application_priority,
        threat_level=threat_level,
        device_trust=device_trust,
    )
    decision_result = make_decision(network_input)

    if not enforce:
        return ClosedLoopResult(
            pre_telemetry=pre_telemetry,
            network_input=network_input,
            decision_result=decision_result,
            enforcement_result=None,
            post_telemetry=None,
        )

    enforcement_result = apply_qos_policy(
        interface,
        decision_result,
        configured_capacity_mbps,
        enabled=True,
    )
    post_telemetry = collect_network_telemetry(interface)
    return ClosedLoopResult(
        pre_telemetry=pre_telemetry,
        network_input=network_input,
        decision_result=decision_result,
        enforcement_result=enforcement_result,
        post_telemetry=post_telemetry,
    )