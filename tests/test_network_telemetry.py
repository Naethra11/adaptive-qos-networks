import subprocess

import pytest

from src.network_telemetry import (
    DEFAULT_INTERFACE,
    collect_network_telemetry,
    parse_htb_rate,
    parse_interface_statistics,
    parse_qdisc_statistics,
)


TC_QDISC_OUTPUT = """\
qdisc htb 1: root refcnt 2 r2q 10 default 0x10 direct_qlen 1000
 Sent 123456 bytes 789 pkt (dropped 12, overlimits 34 requeues 0)
 backlog 1Kb 2p requeues 0
qdisc fq_codel 10: parent 1:10 limit 10240p flows 1024
 Sent 999 bytes 9 pkt (dropped 99, overlimits 99 requeues 0)
 backlog 9Kb 9p requeues 0
"""
TC_CLASS_OUTPUT = """\
class htb 1:1 root rate 10Mbit ceil 10Mbit burst 15Kb cburst 15Kb
class htb 1:10 parent 1:1 rate 5Mbit ceil 10Mbit
"""
IP_LINK_OUTPUT = """\
3: s1-eth3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc htb state UP
    link/ether 00:00:00:00:00:03 brd ff:ff:ff:ff:ff:ff
    RX:  bytes packets errors dropped  missed   mcast
    1111  22      3      4        0       0
    TX:  bytes packets errors dropped carrier collsns
    5555  66      7      8       0       0
"""


def test_parse_qdisc_statistics_uses_root_counters_and_converts_backlog():
    assert parse_qdisc_statistics(TC_QDISC_OUTPUT) == {
        "qdisc_sent_bytes": 123456,
        "qdisc_sent_packets": 789,
        "qdisc_dropped_packets": 12,
        "qdisc_overlimits": 34,
        "qdisc_backlog_bytes": 1024,
        "qdisc_backlog_packets": 2,
    }


def test_parse_root_htb_configured_rate():
    assert parse_htb_rate(TC_CLASS_OUTPUT) == "10Mbit"


def test_parse_interface_rx_and_tx_counters():
    assert parse_interface_statistics(IP_LINK_OUTPUT) == {
        "interface_rx_bytes": 1111,
        "interface_rx_packets": 22,
        "interface_rx_errors": 3,
        "interface_rx_drops": 4,
        "interface_tx_bytes": 5555,
        "interface_tx_packets": 66,
        "interface_tx_errors": 7,
        "interface_tx_drops": 8,
    }


def test_collect_telemetry_runs_only_read_only_commands(monkeypatch):
    outputs = [TC_QDISC_OUTPUT, TC_CLASS_OUTPUT, IP_LINK_OUTPUT]
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, outputs[len(commands) - 1], "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = collect_network_telemetry()

    assert result.interface == DEFAULT_INTERFACE == "s1-eth3"
    assert result.qdisc_sent_bytes == 123456
    assert result.qdisc_sent_packets == 789
    assert result.qdisc_dropped_packets == 12
    assert result.qdisc_overlimits == 34
    assert result.qdisc_backlog_bytes == 1024
    assert result.qdisc_backlog_packets == 2
    assert result.htb_configured_rate == "10Mbit"
    assert result.interface_rx_bytes == 1111
    assert result.interface_rx_packets == 22
    assert result.interface_rx_errors == 3
    assert result.interface_rx_drops == 4
    assert result.interface_tx_bytes == 5555
    assert result.interface_tx_packets == 66
    assert result.interface_tx_errors == 7
    assert result.interface_tx_drops == 8
    assert result.to_dict()["interface"] == "s1-eth3"
    assert [command for command, _ in commands] == [
        ["tc", "-s", "qdisc", "show", "dev", "s1-eth3"],
        ["tc", "-s", "class", "show", "dev", "s1-eth3"],
        ["ip", "-s", "link", "show", "dev", "s1-eth3"],
    ]
    assert all(kwargs == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 5,
    } for _, kwargs in commands)


def test_collect_telemetry_accepts_configurable_interface(monkeypatch):
    outputs = [TC_QDISC_OUTPUT, TC_CLASS_OUTPUT, IP_LINK_OUTPUT]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, outputs.pop(0), ""
        ),
    )

    result = collect_network_telemetry("s2-eth1")
    assert result.interface == "s2-eth1"


def test_interface_argument_is_validated_before_command_execution(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("command must not be executed"),
    )

    with pytest.raises(ValueError, match="interface"):
        collect_network_telemetry("s1-eth3; rm -rf /")


@pytest.mark.parametrize(
    ("parser", "output", "message"),
    [
        (parse_qdisc_statistics, "qdisc fq_codel 1: root", "root qdisc"),
        (parse_htb_rate, "class fq_codel 1:1 root", "root HTB"),
        (parse_interface_statistics, "3: eth0: UP", "RX counters"),
    ],
)
def test_missing_command_counters_raise_clear_errors(parser, output, message):
    with pytest.raises(ValueError, match=message):
        parser(output)


def test_subprocess_failures_are_not_silently_converted_to_empty_telemetry(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="tc unavailable")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        collect_network_telemetry()
