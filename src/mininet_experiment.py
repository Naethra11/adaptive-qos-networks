"""Explicit Mininet/WSL experiment protocol and result parsing.

Importing this module or running its unit tests never starts Mininet or changes
network state. Real experiments require the explicit ``--run-experiment`` CLI
flag and a caller-supplied, already-running Mininet topology. Measurements
produced here are testbed observations, not claims about production networks.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence

from src.models import DecisionResult
from src.network_telemetry import NetworkTelemetry, collect_network_telemetry
from src.qos_enforcer import apply_qos_policy, clear_qos_policy


TRIALS_PER_CONDITION = 3
IPERF_DURATION_SECONDS = 20
PING_COUNT = 20
BOTTLENECK_INTERFACE = "s1-eth3"
BOTTLENECK_CAPACITY_MBPS = 10.0
FLOW_1_SOURCE = "h1"
FLOW_2_SOURCE = "h3"
RECEIVER_HOST = "h2"
RECEIVER_IP = "10.0.0.2"
FLOW_1_PORT = 5201
FLOW_2_PORT = 5202
_RATE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)(bit|kbit|mbit|gbit)$", re.IGNORECASE)
_CLASS_BLOCK_PATTERN = re.compile(r"(?m)(?=^\s*class\s+htb\s+)")


@dataclass(frozen=True)
class ExperimentCondition:
    name: str
    configured_rate_mbps: float


CONDITIONS = (
    ExperimentCondition("BASELINE", 10.0),
    ExperimentCondition("NORMAL", 4.0),
    ExperimentCondition("QUARANTINED", 0.5),
)
CONDITIONS_BY_NAME = {condition.name: condition for condition in CONDITIONS}


@dataclass(frozen=True)
class Iperf3Result:
    receiver_mbps: float | None
    sender_mbps: float | None
    retransmissions: int | None
    requested_duration_seconds: float | None
    observed_duration_seconds: float | None


@dataclass(frozen=True)
class PingResult:
    transmitted: int | None
    received: int | None
    packet_loss_percent: float | None
    rtt_min_ms: float | None
    rtt_avg_ms: float | None
    rtt_max_ms: float | None
    rtt_mdev_ms: float | None


@dataclass(frozen=True)
class ClassTelemetry:
    configured_rate: str | None
    configured_ceil: str | None
    dropped_packets: int | None
    overlimits: int | None


@dataclass(frozen=True)
class MininetTrialResult:
    condition: str
    trial_number: int
    valid: bool
    duration_seconds: float
    configured_rate_mbps: float
    flow_1_receiver_mbps: float | None
    flow_2_receiver_mbps: float | None
    aggregate_receiver_mbps: float | None
    flow_1_sender_mbps: float | None
    flow_2_sender_mbps: float | None
    flow_1_retransmissions: int | None
    flow_2_retransmissions: int | None
    aggregate_retransmissions: int | None
    jain_fairness: float | None
    ping_transmitted: int | None
    ping_received: int | None
    packet_loss_percent: float | None
    rtt_min_ms: float | None
    rtt_avg_ms: float | None
    rtt_max_ms: float | None
    rtt_mdev_ms: float | None
    qdisc_sent_packets: int | None
    qdisc_dropped_packets: int | None
    qdisc_overlimits: int | None
    qdisc_backlog_packets: int | None
    class_dropped_packets: int | None
    class_overlimits: int | None
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class ConditionSummary:
    condition: str
    configured_rate_mbps: float
    valid_trials: int
    invalid_trials: int
    mean_aggregate_receiver_mbps: float | None
    stddev_aggregate_receiver_mbps: float | None
    mean_flow_1_receiver_mbps: float | None
    mean_flow_2_receiver_mbps: float | None
    mean_jain_fairness: float | None
    mean_packet_loss_percent: float | None
    mean_rtt_avg_ms: float | None
    mean_rtt_mdev_ms: float | None
    mean_aggregate_retransmissions: float | None
    mean_qdisc_dropped_packets: float | None
    mean_qdisc_overlimits: float | None
    throughput_utilization_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentSessionResult:
    no_load_ping: PingResult
    trials: tuple[MininetTrialResult, ...]
    session_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "no_load_ping": asdict(self.no_load_ping),
            "trials": [trial.to_dict() for trial in self.trials],
            "session_errors": list(self.session_errors),
        }


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., Any]
TelemetryCollector = Callable[[str], NetworkTelemetry]
QosApply = Callable[..., Any]
QosClear = Callable[..., Any]


def parse_iperf3_result(payload: str | Mapping[str, Any]) -> Iperf3Result:
    """Parse one iperf3 JSON client result, preferring receiver-side rates.

    Missing optional values remain ``None``. A sender rate is never substituted
    for a missing receiver rate.
    """
    if isinstance(payload, str):
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid iperf3 JSON: {error}") from error
    elif isinstance(payload, Mapping):
        document = payload
    else:
        raise TypeError("iperf3 payload must be JSON text or a mapping.")

    start = document.get("start") or {}
    test_start = start.get("test_start") or {}
    end = document.get("end") or {}
    received = end.get("sum_received") or {}
    sent = end.get("sum_sent") or {}
    receiver_bps = _first_number(
        received.get("bits_per_second"),
        _sum_stream_direction(end, "receiver", "bits_per_second"),
    )
    sender_bps = _first_number(
        sent.get("bits_per_second"),
        _sum_stream_direction(end, "sender", "bits_per_second"),
    )
    retransmissions = _first_integer(
        sent.get("retransmits"),
        _sum_stream_direction(end, "sender", "retransmits"),
    )
    observed_duration = _first_number(
        received.get("seconds"),
        sent.get("seconds"),
        (end.get("sum") or {}).get("seconds"),
    )

    return Iperf3Result(
        receiver_mbps=receiver_bps / 1_000_000 if receiver_bps is not None else None,
        sender_mbps=sender_bps / 1_000_000 if sender_bps is not None else None,
        retransmissions=retransmissions,
        requested_duration_seconds=_optional_number(test_start.get("duration")),
        observed_duration_seconds=observed_duration,
    )


def parse_ping_result(output: str) -> PingResult:
    """Parse Linux ping packet loss and RTT summary; mdev is an RTT variation proxy."""
    if not isinstance(output, str):
        raise TypeError("ping output must be a string.")
    packet_match = re.search(
        r"(?m)(\d+)\s+packets transmitted,\s*(\d+)\s+"
        r"(?:packets )?received,\s*([\d.]+)%\s+packet loss",
        output,
    )
    transmitted = int(packet_match.group(1)) if packet_match else None
    received = int(packet_match.group(2)) if packet_match else None
    loss = float(packet_match.group(3)) if packet_match else None
    rtt_match = re.search(
        r"(?m)(?:rtt|round-trip)\s+min/avg/max/"
        r"(?:mdev|stddev)\s*=\s*"
        r"([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",
        output,
    )
    return PingResult(
        transmitted=transmitted,
        received=received,
        packet_loss_percent=loss,
        rtt_min_ms=float(rtt_match.group(1)) if rtt_match else None,
        rtt_avg_ms=float(rtt_match.group(2)) if rtt_match else None,
        rtt_max_ms=float(rtt_match.group(3)) if rtt_match else None,
        rtt_mdev_ms=float(rtt_match.group(4)) if rtt_match else None,
    )


def calculate_jain_fairness(
    flow_1_throughput_mbps: float | None,
    flow_2_throughput_mbps: float | None,
) -> float | None:
    """Calculate Jain fairness from two receiver-throughput measurements."""
    if flow_1_throughput_mbps is None or flow_2_throughput_mbps is None:
        return None
    values = (flow_1_throughput_mbps, flow_2_throughput_mbps)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        raise ValueError("Throughputs must be finite non-negative measurements.")
    denominator = 2 * (flow_1_throughput_mbps ** 2 + flow_2_throughput_mbps ** 2)
    if denominator == 0:
        return None
    return round(
        (flow_1_throughput_mbps + flow_2_throughput_mbps) ** 2 / denominator,
        6,
    )


def calculate_counter_delta(before: int | None, after: int | None) -> int | None:
    """Return a counter delta; missing values stay None and resets raise."""
    if before is None or after is None:
        return None
    if (
        isinstance(before, bool)
        or isinstance(after, bool)
        or not isinstance(before, int)
        or not isinstance(after, int)
    ):
        raise TypeError("Counter values must be integers or None.")
    if before < 0 or after < 0:
        raise ValueError("Counter values cannot be negative.")
    if after < before:
        raise ValueError(
            "Counter decreased between snapshots; it may have reset. "
            "The trial delta is unavailable."
        )
    return after - before


def parse_class_telemetry(
    output: str,
    *,
    class_id: str = "5:1",
) -> ClassTelemetry:
    """Parse rate, ceiling, drops, and overlimits for the specified HTB class."""
    if not isinstance(output, str):
        raise TypeError("tc class output must be a string.")
    blocks = _CLASS_BLOCK_PATTERN.split(output)
    for block in blocks:
        header = block.splitlines()[0] if block.splitlines() else ""
        match = re.match(r"\s*class\s+htb\s+(\S+)\b(.*)", header)
        if match is None or match.group(1) != class_id:
            continue
        header_tail = match.group(2)
        rate_match = re.search(r"\brate\s+(\S+)", header_tail)
        ceil_match = re.search(r"\bceil\s+(\S+)", header_tail)
        sent_match = re.search(
            r"\bSent\s+\d+\s+bytes\s+\d+\s+pkt\s*"
            r"\(dropped\s+(\d+),\s*overlimits\s+(\d+)\b",
            block,
        )
        return ClassTelemetry(
            configured_rate=rate_match.group(1) if rate_match else None,
            configured_ceil=ceil_match.group(1) if ceil_match else None,
            dropped_packets=int(sent_match.group(1)) if sent_match else None,
            overlimits=int(sent_match.group(2)) if sent_match else None,
        )
    return ClassTelemetry(None, None, None, None)


def parse_rate_mbps(rate: str) -> float:
    """Parse Linux tc decimal bit-rate units into Mbps."""
    match = _RATE_PATTERN.fullmatch(rate.strip())
    if match is None:
        raise ValueError(f"Unsupported tc rate: {rate!r}.")
    amount = float(match.group(1))
    multiplier = {
        "bit": 1,
        "kbit": 1_000,
        "mbit": 1_000_000,
        "gbit": 1_000_000_000,
    }[match.group(2).lower()]
    result = amount * multiplier / 1_000_000
    if not math.isfinite(result) or result <= 0:
        raise ValueError("tc rate must be a finite positive rate.")
    return result


def summarize_trials(
    trials: Sequence[MininetTrialResult],
) -> dict[str, ConditionSummary]:
    """Summarize valid trials only, reporting invalid counts separately."""
    summaries: dict[str, ConditionSummary] = {}
    for condition in CONDITIONS:
        condition_trials = [trial for trial in trials if trial.condition == condition.name]
        valid_trials = [trial for trial in condition_trials if trial.valid]
        summaries[condition.name] = ConditionSummary(
            condition=condition.name,
            configured_rate_mbps=condition.configured_rate_mbps,
            valid_trials=len(valid_trials),
            invalid_trials=len(condition_trials) - len(valid_trials),
            mean_aggregate_receiver_mbps=_mean(
                trial.aggregate_receiver_mbps for trial in valid_trials
            ),
            stddev_aggregate_receiver_mbps=_population_stddev(
                trial.aggregate_receiver_mbps for trial in valid_trials
            ),
            mean_flow_1_receiver_mbps=_mean(
                trial.flow_1_receiver_mbps for trial in valid_trials
            ),
            mean_flow_2_receiver_mbps=_mean(
                trial.flow_2_receiver_mbps for trial in valid_trials
            ),
            mean_jain_fairness=_mean(
                trial.jain_fairness for trial in valid_trials
            ),
            mean_packet_loss_percent=_mean(
                trial.packet_loss_percent for trial in valid_trials
            ),
            mean_rtt_avg_ms=_mean(trial.rtt_avg_ms for trial in valid_trials),
            mean_rtt_mdev_ms=_mean(trial.rtt_mdev_ms for trial in valid_trials),
            mean_aggregate_retransmissions=_mean(
                trial.aggregate_retransmissions for trial in valid_trials
            ),
            mean_qdisc_dropped_packets=_mean(
                trial.qdisc_dropped_packets for trial in valid_trials
            ),
            mean_qdisc_overlimits=_mean(
                trial.qdisc_overlimits for trial in valid_trials
            ),
            throughput_utilization_percent=_utilization(
                _mean(trial.aggregate_receiver_mbps for trial in valid_trials),
                condition.configured_rate_mbps,
            ),
        )
    unknown_conditions = {
        trial.condition for trial in trials
    } - set(CONDITIONS_BY_NAME)
    if unknown_conditions:
        raise ValueError(f"Unknown trial conditions: {sorted(unknown_conditions)}.")
    return summaries


def run_experiment_session(
    host_pids: Mapping[str, int],
    *,
    trials_per_condition: int = TRIALS_PER_CONDITION,
    duration_seconds: int = IPERF_DURATION_SECONDS,
    ping_count: int = PING_COUNT,
    interface: str = BOTTLENECK_INTERFACE,
    command_runner: CommandRunner | None = None,
    popen_factory: PopenFactory | None = None,
    telemetry_collector: TelemetryCollector | None = None,
    qos_apply: QosApply | None = None,
    qos_clear: QosClear | None = None,
) -> ExperimentSessionResult:
    """Explicitly execute the three-condition experiment on an active testbed.

    The caller must provide the host namespace PIDs for h1, h2, and h3 and
    invoke this function intentionally (the CLI additionally requires
    ``--run-experiment``). No topology is started here. Failed trials are
    returned with ``valid=False`` and notes; they are never silently discarded.
    The bottleneck is restored and verified at 10 Mbps after each attempt and
    verified once more after all trials complete.
    """
    _validate_run_settings(
        host_pids, trials_per_condition, duration_seconds, ping_count, interface
    )
    runner = command_runner or subprocess.run
    popen = popen_factory or subprocess.Popen
    collect = telemetry_collector or collect_network_telemetry
    apply_rate = qos_apply or apply_qos_policy
    clear_rate = qos_clear or clear_qos_policy
    normalized_pids = {name: int(pid) for name, pid in host_pids.items()}

    no_load_process = _start_host_process(
        popen,
        normalized_pids["h3"],
        ["ping", "-n", "-c", str(ping_count), RECEIVER_IP],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    no_load_output, no_load_error, no_load_code = _communicate(
        no_load_process, ping_count + 10
    )
    if no_load_code != 0:
        raise RuntimeError(f"No-load reference ping failed: {no_load_error.strip()}")
    no_load_ping = parse_ping_result(no_load_output)
    if (
        no_load_ping.transmitted != ping_count
        or no_load_ping.received is None
        or no_load_ping.rtt_avg_ms is None
        or no_load_ping.rtt_mdev_ms is None
    ):
        raise RuntimeError("No-load reference ping was incomplete or unparseable.")

    results: list[MininetTrialResult] = []
    for condition in CONDITIONS:
        for trial_number in range(1, trials_per_condition + 1):
            results.append(
                _run_trial(
                    condition,
                    trial_number,
                    normalized_pids,
                    duration_seconds=duration_seconds,
                    ping_count=ping_count,
                    interface=interface,
                    runner=runner,
                    popen=popen,
                    collect=collect,
                    apply_rate=apply_rate,
                    clear_rate=clear_rate,
                )
            )
    session_errors: list[str] = []
    try:
        final_telemetry = collect(interface)
        final_rate = parse_rate_mbps(final_telemetry.htb_configured_rate)
        if not math.isclose(
            final_rate,
            BOTTLENECK_CAPACITY_MBPS,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise RuntimeError(
                "Final baseline restoration verification failed: "
                f"{final_rate:g} Mbps."
            )
    except Exception as error:
        session_errors.append(
            f"Final baseline restoration verification failed: "
            f"{type(error).__name__}: {error}"
        )
    return ExperimentSessionResult(
        no_load_ping,
        tuple(results),
        tuple(session_errors),
    )


def _run_trial(
    condition: ExperimentCondition,
    trial_number: int,
    host_pids: Mapping[str, int],
    *,
    duration_seconds: int,
    ping_count: int,
    interface: str,
    runner: CommandRunner,
    popen: PopenFactory,
    collect: TelemetryCollector,
    apply_rate: QosApply,
    clear_rate: QosClear,
) -> MininetTrialResult:
    flow_results: list[Iperf3Result | None] = [None, None]
    ping_result: PingResult | None = None
    pre_telemetry: NetworkTelemetry | None = None
    post_telemetry: NetworkTelemetry | None = None
    pre_class: ClassTelemetry | None = None
    post_class: ClassTelemetry | None = None
    errors: list[str] = []
    applied = False
    started_processes: list[Any] = []

    try:
        _assert_no_iperf_clients(host_pids, runner)
        _assert_bottleneck_up(interface, runner)
        apply_rate(
            interface,
            _rate_decision(condition),
            BOTTLENECK_CAPACITY_MBPS,
            enabled=True,
        )
        applied = True
        pre_telemetry = collect(interface)
        configured = parse_rate_mbps(pre_telemetry.htb_configured_rate)
        if not math.isclose(
            configured, condition.configured_rate_mbps, rel_tol=0.0, abs_tol=0.001
        ):
            message = (
                f"Configured HTB rate {configured:g} Mbps does not match "
                f"expected {condition.configured_rate_mbps:g} Mbps."
            )
            raise RuntimeError(message)
        time.sleep(0.25)
        idle_check = collect(interface)
        _assert_idle_window(pre_telemetry, idle_check)
        pre_telemetry = idle_check
        pre_class = _read_class_telemetry(interface, runner)

        _assert_no_iperf_clients(host_pids, runner)
        server_processes = _start_iperf_servers(
            host_pids[RECEIVER_HOST], popen, runner, started_processes
        )
        del server_processes
        flow_processes = [
            _start_host_process(
                popen,
                host_pids[FLOW_1_SOURCE],
                [
                    "iperf3", "-c", RECEIVER_IP, "-p", str(FLOW_1_PORT),
                    "-t", str(duration_seconds), "-J", "--get-server-output",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
            _start_host_process(
                popen,
                host_pids[FLOW_2_SOURCE],
                [
                    "iperf3", "-c", RECEIVER_IP, "-p", str(FLOW_2_PORT),
                    "-t", str(duration_seconds), "-J", "--get-server-output",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
        ]
        started_processes.extend(flow_processes)
        ping_process = _start_host_process(
            popen,
            host_pids[FLOW_2_SOURCE],
            ["ping", "-n", "-c", str(ping_count), RECEIVER_IP],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started_processes.append(ping_process)

        with ThreadPoolExecutor(max_workers=3) as executor:
            flow_futures = [
                executor.submit(_communicate, process, duration_seconds + 15)
                for process in flow_processes
            ]
            ping_future = executor.submit(
                _communicate, ping_process, ping_count + 15
            )
            flow_completions = [future.result() for future in flow_futures]
            ping_completion = ping_future.result()

        for index, (stdout, stderr, returncode) in enumerate(flow_completions):
            try:
                flow_results[index] = parse_iperf3_result(stdout)
                _validate_iperf_completion(
                    flow_results[index], duration_seconds, returncode, stderr
                )
            except (TypeError, ValueError) as error:
                errors.append(f"Flow {index + 1}: {error}")
        ping_stdout, ping_stderr, ping_returncode = ping_completion
        ping_result = parse_ping_result(ping_stdout)
        if ping_returncode != 0:
            errors.append(f"Loaded ping failed: {ping_stderr.strip()}")
        if ping_result.transmitted != ping_count or ping_result.received is None:
            errors.append("Loaded ping result is missing expected packet counts.")
        if ping_result.rtt_avg_ms is None or ping_result.rtt_mdev_ms is None:
            errors.append("Loaded ping RTT summary is missing or unparseable.")

        _assert_bottleneck_up(interface, runner)
        post_telemetry = collect(interface)
        post_class = _read_class_telemetry(interface, runner)
        if _required_counters_missing(pre_telemetry, post_telemetry, pre_class, post_class):
            errors.append("Required qdisc/class counters are unavailable.")
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        for process in started_processes:
            _stop_if_running(process)
        if applied:
            try:
                clear_rate(interface, enabled=True)
                restored = collect(interface)
                restored_rate = parse_rate_mbps(restored.htb_configured_rate)
                if not math.isclose(
                    restored_rate,
                    BOTTLENECK_CAPACITY_MBPS,
                    rel_tol=0.0,
                    abs_tol=0.001,
                ):
                    errors.append(
                        f"Restoration verification failed: {restored_rate:g} Mbps."
                    )
            except Exception as error:
                errors.append(f"Failed to restore/verify baseline rate: {error}")

    return _make_trial_result(
        condition,
        trial_number,
        duration_seconds,
        flow_results,
        ping_result,
        pre_telemetry,
        post_telemetry,
        pre_class,
        post_class,
        errors,
    )


def _make_trial_result(
    condition: ExperimentCondition,
    trial_number: int,
    duration_seconds: float,
    flow_results: Sequence[Iperf3Result | None],
    ping_result: PingResult | None,
    pre: NetworkTelemetry | None,
    post: NetworkTelemetry | None,
    pre_class: ClassTelemetry | None,
    post_class: ClassTelemetry | None,
    errors: Sequence[str],
) -> MininetTrialResult:
    flow_1 = flow_results[0] if len(flow_results) > 0 else None
    flow_2 = flow_results[1] if len(flow_results) > 1 else None
    receiver_1 = flow_1.receiver_mbps if flow_1 else None
    receiver_2 = flow_2.receiver_mbps if flow_2 else None
    retrans_1 = flow_1.retransmissions if flow_1 else None
    retrans_2 = flow_2.retransmissions if flow_2 else None
    aggregate_receiver = (
        receiver_1 + receiver_2
        if receiver_1 is not None and receiver_2 is not None
        else None
    )
    aggregate_retransmissions = (
        retrans_1 + retrans_2
        if retrans_1 is not None and retrans_2 is not None
        else None
    )
    qdisc_sent = _delta(
        pre.qdisc_sent_packets if pre else None,
        post.qdisc_sent_packets if post else None,
        errors,
        "qdisc sent packets",
    )
    qdisc_drops = _delta(
        pre.qdisc_dropped_packets if pre else None,
        post.qdisc_dropped_packets if post else None,
        errors,
        "qdisc dropped packets",
    )
    qdisc_overlimits = _delta(
        pre.qdisc_overlimits if pre else None,
        post.qdisc_overlimits if post else None,
        errors,
        "qdisc overlimits",
    )
    backlog = post.qdisc_backlog_packets if post else None
    class_drops = _delta(
        pre_class.dropped_packets if pre_class else None,
        post_class.dropped_packets if post_class else None,
        errors,
        "class dropped packets",
    )
    class_overlimits = _delta(
        pre_class.overlimits if pre_class else None,
        post_class.overlimits if post_class else None,
        errors,
        "class overlimits",
    )
    required_values = (
        receiver_1,
        receiver_2,
        flow_1.observed_duration_seconds if flow_1 else None,
        flow_2.observed_duration_seconds if flow_2 else None,
        retrans_1,
        retrans_2,
        ping_result.transmitted if ping_result else None,
        ping_result.received if ping_result else None,
        ping_result.packet_loss_percent if ping_result else None,
        ping_result.rtt_avg_ms if ping_result else None,
        ping_result.rtt_mdev_ms if ping_result else None,
        qdisc_sent,
        qdisc_drops,
        qdisc_overlimits,
        backlog,
        class_drops,
        class_overlimits,
    )
    if any(value is None for value in required_values):
        if "One or more required measurements are unavailable." not in errors:
            errors.append("One or more required measurements are unavailable.")

    return MininetTrialResult(
        condition=condition.name,
        trial_number=trial_number,
        valid=not errors,
        duration_seconds=duration_seconds,
        configured_rate_mbps=condition.configured_rate_mbps,
        flow_1_receiver_mbps=receiver_1,
        flow_2_receiver_mbps=receiver_2,
        aggregate_receiver_mbps=aggregate_receiver,
        flow_1_sender_mbps=flow_1.sender_mbps if flow_1 else None,
        flow_2_sender_mbps=flow_2.sender_mbps if flow_2 else None,
        flow_1_retransmissions=retrans_1,
        flow_2_retransmissions=retrans_2,
        aggregate_retransmissions=aggregate_retransmissions,
        jain_fairness=calculate_jain_fairness(receiver_1, receiver_2),
        ping_transmitted=ping_result.transmitted if ping_result else None,
        ping_received=ping_result.received if ping_result else None,
        packet_loss_percent=ping_result.packet_loss_percent if ping_result else None,
        rtt_min_ms=ping_result.rtt_min_ms if ping_result else None,
        rtt_avg_ms=ping_result.rtt_avg_ms if ping_result else None,
        rtt_max_ms=ping_result.rtt_max_ms if ping_result else None,
        rtt_mdev_ms=ping_result.rtt_mdev_ms if ping_result else None,
        qdisc_sent_packets=qdisc_sent,
        qdisc_dropped_packets=qdisc_drops,
        qdisc_overlimits=qdisc_overlimits,
        qdisc_backlog_packets=backlog,
        class_dropped_packets=class_drops,
        class_overlimits=class_overlimits,
        notes="; ".join(errors) if errors else None,
    )


def _rate_decision(condition: ExperimentCondition) -> DecisionResult:
    policy = {
        "BASELINE": "NORMAL",
        "NORMAL": "NORMAL",
        "QUARANTINED": "QUARANTINED",
    }[condition.name]
    return DecisionResult(
        decision_score=0.0,
        priority=policy,
        qos_policy=policy,
        bandwidth_allocation=condition.configured_rate_mbps,
        queue="Experiment Queue",
        security_action="ALLOW",
        reason=f"Controlled experiment condition {condition.name}.",
        factor_contributions={},
        normalized_factors={},
        dynamic_weights={},
    )


def _assert_no_iperf_clients(
    host_pids: Mapping[str, int],
    runner: CommandRunner,
) -> None:
    for name in (FLOW_1_SOURCE, FLOW_2_SOURCE, RECEIVER_HOST):
        result = runner(
            ["mnexec", "-a", str(host_pids[name]), "pgrep", "-x", "iperf3"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            raise RuntimeError(f"Pre-existing iperf3 process found in {name}.")
        if result.returncode != 1:
            raise RuntimeError(
                f"Could not verify iperf3 process state in {name}: "
                f"{result.stderr.strip()}"
            )


def _assert_bottleneck_up(interface: str, runner: CommandRunner) -> None:
    result = runner(
        ["ip", "-brief", "link", "show", "dev", interface],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if "UP" not in result.stdout.split():
        raise RuntimeError(f"Bottleneck interface {interface} is not UP.")


def _assert_idle_window(
    before: NetworkTelemetry,
    after: NetworkTelemetry,
) -> None:
    sent_bytes_delta = calculate_counter_delta(
        before.qdisc_sent_bytes, after.qdisc_sent_bytes
    )
    sent_packets_delta = calculate_counter_delta(
        before.qdisc_sent_packets, after.qdisc_sent_packets
    )
    if sent_bytes_delta is None or sent_packets_delta is None:
        raise RuntimeError("Cannot verify idle traffic window from qdisc counters.")
    if sent_bytes_delta or sent_packets_delta or after.qdisc_backlog_packets:
        raise RuntimeError(
            "Bottleneck was not idle before trial traffic; qdisc counters or "
            "backlog changed during the idle check."
        )


def _read_class_telemetry(
    interface: str,
    runner: CommandRunner,
) -> ClassTelemetry:
    result = runner(
        ["tc", "-s", "class", "show", "dev", interface],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return parse_class_telemetry(result.stdout)


def _start_iperf_servers(
    h2_pid: int,
    popen: PopenFactory,
    runner: CommandRunner,
    started: list[Any],
) -> tuple[Any, Any]:
    servers = []
    for port in (FLOW_1_PORT, FLOW_2_PORT):
        server = _start_host_process(
            popen,
            h2_pid,
            ["iperf3", "-s", "-1", "-p", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started.append(server)
        servers.append(server)
    deadline = time.monotonic() + 5
    for port, server in zip((FLOW_1_PORT, FLOW_2_PORT), servers):
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f"iperf3 server on port {port} exited before ready.")
            result = runner(
                [
                    "mnexec", "-a", str(h2_pid), "ss", "-lnt",
                    "sport", "=", f":{port}",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and f":{port}" in result.stdout:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"iperf3 server on port {port} did not become ready.")
    return servers[0], servers[1]


def _start_host_process(
    popen: PopenFactory,
    host_pid: int,
    command: Sequence[str],
    **kwargs: Any,
) -> Any:
    return popen(
        ["mnexec", "-a", str(host_pid), *command],
        **kwargs,
    )


def _communicate(process: Any, timeout: float) -> tuple[str, str, int]:
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _stop_if_running(process)
        raise RuntimeError(f"Command timed out after {timeout:g} seconds.") from error
    return stdout or "", stderr or "", int(process.returncode)


def _stop_if_running(process: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _validate_iperf_completion(
    result: Iperf3Result,
    duration_seconds: int,
    returncode: int,
    stderr: str,
) -> None:
    if returncode != 0:
        raise ValueError(f"iperf3 client failed: {stderr.strip()}")
    if result.receiver_mbps is None:
        raise ValueError("iperf3 receiver throughput is missing.")
    if result.retransmissions is None:
        raise ValueError("iperf3 retransmission count is missing.")
    if result.requested_duration_seconds != duration_seconds:
        raise ValueError("iperf3 requested duration does not match the protocol.")
    if (
        result.observed_duration_seconds is None
        or result.observed_duration_seconds < duration_seconds - 0.5
    ):
        raise ValueError("iperf3 flow did not run for the full configured duration.")


def _required_counters_missing(
    pre: NetworkTelemetry,
    post: NetworkTelemetry,
    pre_class: ClassTelemetry,
    post_class: ClassTelemetry,
) -> bool:
    return any(
        value is None
        for value in (
            calculate_counter_delta(pre.qdisc_sent_packets, post.qdisc_sent_packets),
            calculate_counter_delta(
                pre.qdisc_dropped_packets, post.qdisc_dropped_packets
            ),
            calculate_counter_delta(pre.qdisc_overlimits, post.qdisc_overlimits),
            post.qdisc_backlog_packets,
            pre_class.dropped_packets,
            post_class.dropped_packets,
            pre_class.overlimits,
            post_class.overlimits,
        )
    )


def _delta(
    before: int | None,
    after: int | None,
    errors: list[str],
    label: str,
) -> int | None:
    try:
        return calculate_counter_delta(before, after)
    except (TypeError, ValueError) as error:
        errors.append(f"{label} delta unavailable: {error}")
        return None


def _sum_stream_direction(
    end: Mapping[str, Any],
    direction: str,
    field: str,
) -> float | int | None:
    streams = end.get("streams") or []
    values = []
    for stream in streams:
        if not isinstance(stream, Mapping):
            continue
        direction_result = stream.get(direction) or {}
        value = direction_result.get(field)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _optional_number(value)
        if parsed is not None:
            return parsed
    return None


def _first_integer(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(value) and value >= 0 and float(value).is_integer():
            return int(value)
    return None


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _mean(values: Sequence[float | int | None] | Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(statistics.mean(present), 6) if present else None


def _population_stddev(values: Sequence[float | int | None] | Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(statistics.pstdev(present), 6) if present else None


def _utilization(
    mean_throughput: float | None,
    configured_rate_mbps: float,
) -> float | None:
    if mean_throughput is None:
        return None
    return round(mean_throughput / configured_rate_mbps * 100, 6)


def _validate_run_settings(
    host_pids: Mapping[str, int],
    trials_per_condition: int,
    duration_seconds: int,
    ping_count: int,
    interface: str,
) -> None:
    if set(host_pids) != {FLOW_1_SOURCE, FLOW_2_SOURCE, RECEIVER_HOST}:
        raise ValueError("host_pids must contain exactly h1, h2, and h3.")
    for host, pid in host_pids.items():
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ValueError(f"{host} PID must be a positive integer.")
    for name, value in (
        ("trials_per_condition", trials_per_condition),
        ("duration_seconds", duration_seconds),
        ("ping_count", ping_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    if interface != BOTTLENECK_INTERFACE:
        raise ValueError(
            f"This experiment protocol is fixed to {BOTTLENECK_INTERFACE}."
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explicit Mininet shared-bottleneck experiment runner."
    )
    parser.add_argument(
        "--run-experiment",
        action="store_true",
        help="required confirmation to change tc state and run traffic",
    )
    parser.add_argument("--h1-pid", type=int)
    parser.add_argument("--h2-pid", type=int)
    parser.add_argument("--h3-pid", type=int)
    parser.add_argument("--trials", type=int, default=TRIALS_PER_CONDITION)
    parser.add_argument("--duration", type=int, default=IPERF_DURATION_SECONDS)
    parser.add_argument("--ping-count", type=int, default=PING_COUNT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; does nothing unless explicitly passed --run-experiment."""
    args = _parse_args(argv)
    if not args.run_experiment:
        print("No experiment run: pass --run-experiment to opt in.", file=sys.stderr)
        return 2
    if any(pid is None for pid in (args.h1_pid, args.h2_pid, args.h3_pid)):
        print("--h1-pid, --h2-pid, and --h3-pid are required.", file=sys.stderr)
        return 2
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print(
            "Run explicitly as root in the Mininet WSL environment; "
            "this program will not invoke sudo automatically.",
            file=sys.stderr,
        )
        return 2
    try:
        session = run_experiment_session(
            {"h1": args.h1_pid, "h2": args.h2_pid, "h3": args.h3_pid},
            trials_per_condition=args.trials,
            duration_seconds=args.duration,
            ping_count=args.ping_count,
        )
        output = session.to_dict()
        output["summary"] = {
            name: summary.to_dict()
            for name, summary in summarize_trials(session.trials).items()
        }
        print(json.dumps(output, indent=2, sort_keys=True), flush=True)
    except Exception as error:
        print(
            f"Experiment failed: {type(error).__name__}: {error}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    failed_trials = [trial for trial in session.trials if not trial.valid]
    for trial in failed_trials:
        print(
            f"{trial.condition} trial {trial.trial_number} failed: "
            f"{trial.notes or 'unspecified measurement error'}",
            file=sys.stderr,
            flush=True,
        )
    for error in session.session_errors:
        print(f"Experiment session error: {error}", file=sys.stderr, flush=True)
    if failed_trials or session.session_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
