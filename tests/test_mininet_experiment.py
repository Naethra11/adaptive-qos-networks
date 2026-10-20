import json
from pathlib import Path
import subprocess

import pytest

from src.decision_engine import CONFIG_PATH
from src.mininet_experiment import NetworkTelemetry
from src.mininet_experiment import (
    BOTTLENECK_INTERFACE,
    CONDITIONS,
    ExperimentSessionResult,
    IPERF_DURATION_SECONDS,
    PING_COUNT,
    TRIALS_PER_CONDITION,
    Iperf3Result,
    MininetTrialResult,
    PingResult,
    _start_host_process,
    calculate_counter_delta,
    calculate_jain_fairness,
    parse_class_telemetry,
    parse_iperf3_result,
    parse_ping_result,
    run_experiment_session,
    summarize_trials,
)


IPERF_JSON = {
    "start": {"test_start": {"duration": 20}},
    "end": {
        "sum_sent": {
            "seconds": 20.0,
            "bits_per_second": 5_200_000,
            "retransmits": 7,
        },
        "sum_received": {
            "seconds": 20.0,
            "bits_per_second": 5_000_000,
        },
    },
}
PING_OUTPUT = """\
PING 10.0.0.2 (10.0.0.2) 56(84) bytes of data.
64 bytes from 10.0.0.2: icmp_seq=1 ttl=64 time=1.20 ms

--- 10.0.0.2 ping statistics ---
20 packets transmitted, 20 received, 0% packet loss, time 19019ms
rtt min/avg/max/mdev = 1.000/1.200/1.600/0.100 ms
"""
CLASS_OUTPUT = """\
class htb 5:1 root leaf 10: prio 0 rate 4Mbit ceil 4Mbit burst 15Kb
 Sent 1234 bytes 20 pkt (dropped 3, overlimits 5 requeues 0)
 backlog 0b 0p requeues 0
"""


def test_iperf3_parser_uses_receiver_throughput_and_reads_sender():
    parsed = parse_iperf3_result(IPERF_JSON)

    assert parsed.receiver_mbps == 5
    assert parsed.sender_mbps == 5.2
    assert parsed.requested_duration_seconds == 20
    assert parsed.observed_duration_seconds == 20


def test_iperf3_parser_extracts_retransmissions():
    assert parse_iperf3_result(json.dumps(IPERF_JSON)).retransmissions == 7


def test_iperf3_parser_does_not_substitute_sender_as_receiver():
    parsed = parse_iperf3_result({
        "end": {"sum_sent": {"bits_per_second": 2_000_000, "retransmits": 1}}
    })

    assert parsed.receiver_mbps is None
    assert parsed.sender_mbps == 2


def test_iperf3_parser_missing_measurements_remain_none():
    assert parse_iperf3_result({"start": {}, "end": {}}) == Iperf3Result(
        None, None, None, None, None
    )


def test_ping_parser_reads_packet_loss_and_rtt_variation_proxy():
    parsed = parse_ping_result(PING_OUTPUT)

    assert parsed.transmitted == 20
    assert parsed.received == 20
    assert parsed.packet_loss_percent == 0
    assert parsed.rtt_min_ms == 1
    assert parsed.rtt_avg_ms == 1.2
    assert parsed.rtt_max_ms == 1.6
    assert parsed.rtt_mdev_ms == 0.1


def test_ping_parser_missing_values_remain_none():
    parsed = parse_ping_result("ping unavailable")

    assert parsed.transmitted is None
    assert parsed.received is None
    assert parsed.packet_loss_percent is None
    assert parsed.rtt_avg_ms is None
    assert parsed.rtt_mdev_ms is None


def test_jain_fairness_formula_and_equal_flows():
    assert calculate_jain_fairness(3, 1) == pytest.approx(0.8)
    assert calculate_jain_fairness(4, 4) == 1.0


def test_jain_fairness_approaches_half_for_very_unequal_flows():
    assert calculate_jain_fairness(1000, 0.001) == pytest.approx(
        0.500001, abs=0.000002
    )


def test_jain_fairness_is_unavailable_when_flow_data_is_missing_or_zero():
    assert calculate_jain_fairness(None, 1) is None
    assert calculate_jain_fairness(0, 0) is None


def test_counter_delta_and_missing_counter():
    assert calculate_counter_delta(100, 145) == 45
    assert calculate_counter_delta(None, 145) is None


def test_counter_reset_negative_delta_is_explicit():
    with pytest.raises(ValueError, match="decreased"):
        calculate_counter_delta(145, 2)


def test_class_parser_keeps_class_drops_distinct_from_qdisc_drops():
    parsed = parse_class_telemetry(CLASS_OUTPUT)

    assert parsed.configured_rate == "4Mbit"
    assert parsed.configured_ceil == "4Mbit"
    assert parsed.dropped_packets == 3
    assert parsed.overlimits == 5


def test_trial_result_preserves_condition_trial_and_invalid_status():
    trial = make_trial("NORMAL", 2, valid=False, aggregate=None)

    assert trial.condition == "NORMAL"
    assert trial.trial_number == 2
    assert trial.valid is False
    assert trial.aggregate_receiver_mbps is None
    assert trial.to_dict()["notes"] == "measurement unavailable"


def test_aggregate_uses_only_valid_trials_and_counts_invalid():
    valid = make_trial("NORMAL", 1, valid=True, aggregate=5.0)
    invalid = make_trial("NORMAL", 2, valid=False, aggregate=100.0)

    summary = summarize_trials([valid, invalid])["NORMAL"]

    assert summary.valid_trials == 1
    assert summary.invalid_trials == 1
    assert summary.mean_aggregate_receiver_mbps == 5
    assert summary.stddev_aggregate_receiver_mbps == 0


def test_standard_deviation_uses_available_valid_measurements():
    first = make_trial("BASELINE", 1, valid=True, aggregate=2.0)
    second = make_trial("BASELINE", 2, valid=True, aggregate=4.0)
    missing = make_trial("BASELINE", 3, valid=True, aggregate=None)

    summary = summarize_trials([first, second, missing])["BASELINE"]

    assert summary.valid_trials == 3
    assert summary.mean_aggregate_receiver_mbps == 3
    assert summary.stddev_aggregate_receiver_mbps == 1


def test_throughput_utilization_formula_is_not_clamped():
    trial = make_trial("BASELINE", 1, valid=True, aggregate=12.5)

    summary = summarize_trials([trial])["BASELINE"]

    assert summary.throughput_utilization_percent == 125


def test_fixed_experiment_constants_and_conditions():
    assert TRIALS_PER_CONDITION == 3
    assert IPERF_DURATION_SECONDS == 20
    assert PING_COUNT == 20
    assert BOTTLENECK_INTERFACE == "s1-eth3"
    assert [(condition.name, condition.configured_rate_mbps) for condition in CONDITIONS] == [
        ("BASELINE", 10.0),
        ("NORMAL", 4.0),
        ("QUARANTINED", 0.5),
    ]


def test_host_commands_use_argument_lists_and_are_injectable():
    observed = {}

    def fake_popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return object()

    process = _start_host_process(
        fake_popen,
        123,
        ["ping", "-c", "20", "10.0.0.2"],
        text=True,
    )

    assert process is not None
    assert observed["command"] == [
        "mnexec", "-a", "123", "ping", "-c", "20", "10.0.0.2"
    ]
    assert observed["kwargs"] == {"text": True}


def test_no_mininet_or_privileged_execution_on_import_or_without_flag():
    from src.mininet_experiment import main

    assert main([]) == 2


def test_cli_prints_one_parseable_json_result(monkeypatch, capsys):
    import src.mininet_experiment as experiment

    session = ExperimentSessionResult(
        no_load_ping=PingResult(20, 20, 0.0, 1.0, 1.2, 1.6, 0.1),
        trials=(make_trial("BASELINE", 1, valid=True, aggregate=5.0),),
    )
    observed = {}

    def fake_run(host_pids, **kwargs):
        observed["host_pids"] = host_pids
        return session

    monkeypatch.setattr(experiment.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(experiment, "run_experiment_session", fake_run)

    exit_code = experiment.main([
        "--run-experiment",
        "--h1-pid", "101",
        "--h2-pid", "102",
        "--h3-pid", "103",
    ])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert exit_code == 0
    assert observed["host_pids"] == {"h1": 101, "h2": 102, "h3": 103}
    assert set(output) >= {"no_load_ping", "trials", "summary"}
    assert len(output["trials"]) == 1
    assert set(output["summary"]) == {"BASELINE", "NORMAL", "QUARANTINED"}
    assert captured.err == ""


def test_cli_reports_session_exception_to_stderr(monkeypatch, capsys):
    import src.mininet_experiment as experiment

    def fail_run(*args, **kwargs):
        raise RuntimeError("synthetic session failure")

    monkeypatch.setattr(experiment.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(experiment, "run_experiment_session", fail_run)

    exit_code = experiment.main([
        "--run-experiment",
        "--h1-pid", "101",
        "--h2-pid", "102",
        "--h3-pid", "103",
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Experiment failed: RuntimeError: synthetic session failure" in captured.err


def test_cli_preserves_results_and_reports_session_error(monkeypatch, capsys):
    import src.mininet_experiment as experiment

    session = ExperimentSessionResult(
        no_load_ping=PingResult(20, 20, 0.0, 1.0, 1.2, 1.6, 0.1),
        trials=(make_trial("BASELINE", 1, valid=True, aggregate=5.0),),
        session_errors=("final rate check failed",),
    )
    monkeypatch.setattr(experiment.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        experiment, "run_experiment_session", lambda *args, **kwargs: session
    )

    exit_code = experiment.main([
        "--run-experiment",
        "--h1-pid", "101",
        "--h2-pid", "102",
        "--h3-pid", "103",
    ])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert exit_code == 1
    assert output["trials"][0]["trial_number"] == 1
    assert output["session_errors"] == ["final rate check failed"]
    assert "Experiment session error: final rate check failed" in captured.err


def test_no_configuration_file_is_modified():
    before = Path(CONFIG_PATH).read_bytes()

    parse_iperf3_result(IPERF_JSON)
    parse_ping_result(PING_OUTPUT)
    summarize_trials([])

    assert Path(CONFIG_PATH).read_bytes() == before


@pytest.mark.parametrize("fail_final_check", [False, True])
def test_mocked_session_runs_conditions_and_restores_baseline(
    monkeypatch,
    fail_final_check,
):
    import src.mininet_experiment as experiment

    monkeypatch.setattr(experiment.time, "sleep", lambda _: None)
    state = {"rate": 10.0, "collect_calls": 0, "qdisc_packets": 0}
    applied_rates = []
    cleared_rates = []

    class FakeProcess:
        def __init__(self, command):
            self.command = command
            self.returncode = 0
            self.is_server = "-s" in command
            self.terminated = False

        def poll(self):
            return None if self.is_server and not self.terminated else self.returncode

        def communicate(self, timeout=None):
            if "ping" in self.command:
                return PING_OUTPUT, ""
            if "-c" in self.command and "iperf3" in self.command:
                return json.dumps(IPERF_JSON), ""
            return "", ""

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.terminated = True

    def popen(command, **kwargs):
        return FakeProcess(command)

    def runner(command, **kwargs):
        if "pgrep" in command:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command[:3] == ["ip", "-brief", "link"]:
            return subprocess.CompletedProcess(command, 0, "s1-eth3 UP 1500", "")
        if "ss" in command:
            return subprocess.CompletedProcess(command, 0, f":{command[-1]}", "")
        if command[:3] == ["tc", "-s", "class"]:
            return subprocess.CompletedProcess(command, 0, CLASS_OUTPUT, "")
        raise AssertionError(f"Unexpected command: {command}")

    def collect(interface):
        state["collect_calls"] += 1
        if fail_final_check and state["collect_calls"] == 13:
            raise OSError("synthetic final telemetry failure")
        if state["collect_calls"] % 4 == 3:
            state["qdisc_packets"] += 100
        rate = state["rate"]
        rate_text = "500Kbit" if rate == 0.5 else f"{rate:g}Mbit"
        packets = state["qdisc_packets"]
        return NetworkTelemetry(
            interface=interface,
            qdisc_sent_bytes=packets * 100,
            qdisc_sent_packets=packets,
            qdisc_dropped_packets=0,
            qdisc_overlimits=0,
            qdisc_backlog_bytes=0,
            qdisc_backlog_packets=0,
            htb_configured_rate=rate_text,
            interface_rx_bytes=0,
            interface_rx_packets=0,
            interface_rx_errors=0,
            interface_rx_drops=0,
            interface_tx_bytes=0,
            interface_tx_packets=0,
            interface_tx_errors=0,
            interface_tx_drops=0,
        )

    def apply(interface, decision, capacity, *, enabled):
        assert enabled is True
        assert capacity == 10
        state["rate"] = decision.bandwidth_allocation
        applied_rates.append(state["rate"])

    def clear(interface, *, enabled):
        assert enabled is True
        state["rate"] = 10.0
        cleared_rates.append(state["rate"])

    session = run_experiment_session(
        {"h1": 101, "h2": 102, "h3": 103},
        trials_per_condition=1,
        duration_seconds=20,
        ping_count=20,
        command_runner=runner,
        popen_factory=popen,
        telemetry_collector=collect,
        qos_apply=apply,
        qos_clear=clear,
    )

    assert [trial.condition for trial in session.trials] == [
        "BASELINE", "NORMAL", "QUARANTINED"
    ]
    assert all(trial.valid for trial in session.trials)
    assert applied_rates == [10.0, 4.0, 0.5]
    assert cleared_rates == [10.0, 10.0, 10.0]
    assert state["rate"] == 10.0
    if fail_final_check:
        assert session.session_errors
        assert "synthetic final telemetry failure" in session.session_errors[0]
    else:
        assert session.session_errors == ()


def test_summary_unknown_condition_is_rejected():
    trial = make_trial("OTHER", 1, valid=False, aggregate=None)

    with pytest.raises(ValueError, match="Unknown trial conditions"):
        summarize_trials([trial])


def make_trial(
    condition: str,
    trial_number: int,
    *,
    valid: bool,
    aggregate: float | None,
) -> MininetTrialResult:
    return MininetTrialResult(
        condition=condition,
        trial_number=trial_number,
        valid=valid,
        duration_seconds=20,
        configured_rate_mbps={
            "BASELINE": 10.0,
            "NORMAL": 4.0,
            "QUARANTINED": 0.5,
        }.get(condition, 1.0),
        flow_1_receiver_mbps=aggregate / 2 if aggregate is not None else None,
        flow_2_receiver_mbps=aggregate / 2 if aggregate is not None else None,
        aggregate_receiver_mbps=aggregate,
        flow_1_sender_mbps=None,
        flow_2_sender_mbps=None,
        flow_1_retransmissions=1,
        flow_2_retransmissions=1,
        aggregate_retransmissions=2,
        jain_fairness=1.0 if aggregate is not None else None,
        ping_transmitted=20,
        ping_received=20,
        packet_loss_percent=0,
        rtt_min_ms=1,
        rtt_avg_ms=1.2,
        rtt_max_ms=1.6,
        rtt_mdev_ms=0.1,
        qdisc_sent_packets=100,
        qdisc_dropped_packets=0,
        qdisc_overlimits=0,
        qdisc_backlog_packets=0,
        class_dropped_packets=0,
        class_overlimits=0,
        notes=None if valid else "measurement unavailable",
    )
