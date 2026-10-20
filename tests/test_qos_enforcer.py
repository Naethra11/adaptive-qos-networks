from dataclasses import dataclass
import subprocess

import pytest

from src.models import DecisionResult
from src.qos_enforcer import (
    QosEnforcementError,
    apply_qos_policy,
    clear_qos_policy,
)


ROOT_CLASS_OUTPUT = (
    "class htb 5:1 root leaf 10: prio 0 rate 10Mbit ceil 10Mbit burst 15Kb\n"
)


@dataclass
class CommandRecorder:
    outputs: list[str]
    commands: list[tuple[list[str], dict]]

    def __call__(self, command, **kwargs):
        self.commands.append((command, kwargs))
        output = self.outputs.pop(0) if self.outputs else ""
        return subprocess.CompletedProcess(command, 0, output, "")


def decision(policy, allocation=4.0):
    return DecisionResult(
        decision_score=75,
        priority=policy,
        qos_policy=policy,
        bandwidth_allocation=allocation,
        queue="test",
        security_action="ALLOW",
        reason="test decision",
        factor_contributions={},
        normalized_factors={},
        dynamic_weights={},
    )


@pytest.mark.parametrize(
    "policy",
    [
        "NORMAL",
        "HIGH PRIORITY",
        "CRITICAL PRIORITY",
        "LOW / RATE LIMITED",
        "QUARANTINED",
    ],
)
def test_policy_uses_decision_allocation_and_expected_tc_command(policy):
    runner = CommandRecorder([ROOT_CLASS_OUTPUT, ""], [])

    result = apply_qos_policy(
        "s1-eth3",
        decision(policy, 4),
        10,
        enabled=True,
        command_runner=runner,
    )

    assert result.policy == policy
    assert result.requested_rate_mbps == 4
    assert runner.commands[0][0] == ["tc", "class", "show", "dev", "s1-eth3"]
    assert runner.commands[1][0] == [
        "tc",
        "class",
        "change",
        "dev",
        "s1-eth3",
        "classid",
        "5:1",
        "htb",
        "rate",
        "4mbit",
        "ceil",
        "4mbit",
    ]
    assert all(kwargs == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 5,
    } for _, kwargs in runner.commands)

    clear_qos_policy("s1-eth3", enabled=True, command_runner=runner)


def test_enforcement_is_opt_in_before_any_command_runs():
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(PermissionError, match="opt-in"):
        apply_qos_policy(
            "s1-eth3", decision("NORMAL"), 10, command_runner=runner
        )
    with pytest.raises(PermissionError, match="opt-in"):
        clear_qos_policy("s1-eth3", command_runner=runner)
    assert runner.commands == []


def test_requested_bandwidth_above_capacity_is_rejected():
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(ValueError, match="cannot exceed"):
        apply_qos_policy(
            "s1-eth3",
            decision("HIGH PRIORITY", 10.1),
            10,
            enabled=True,
            command_runner=runner,
        )
    assert runner.commands == []


@pytest.mark.parametrize("allocation", [0, -1])
def test_zero_or_negative_bandwidth_is_rejected(allocation):
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(ValueError, match="finite positive"):
        apply_qos_policy(
            "s1-eth3",
            decision("NORMAL", allocation),
            10,
            enabled=True,
            command_runner=runner,
        )
    assert runner.commands == []


@pytest.mark.parametrize("interface", ["eth0", "lo", "s1-eth3;id", "h1-eth0"])
def test_non_mininet_switch_interfaces_are_rejected(interface):
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(ValueError, match="Mininet switch port"):
        apply_qos_policy(
            interface,
            decision("NORMAL"),
            10,
            enabled=True,
            command_runner=runner,
        )
    assert runner.commands == []


def test_subprocess_failure_raises_clear_enforcement_error():
    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="tc failed")

    with pytest.raises(QosEnforcementError, match="tc command failed"):
        apply_qos_policy(
            "s1-eth3",
            decision("NORMAL"),
            10,
            enabled=True,
            command_runner=fail,
        )


def test_clear_restores_original_rate_and_ceiling():
    runner = CommandRecorder([ROOT_CLASS_OUTPUT, ""], [])

    apply_qos_policy(
        "s1-eth3",
        decision("LOW / RATE LIMITED", 2.5),
        10,
        enabled=True,
        command_runner=runner,
    )
    clear_command = clear_qos_policy(
        "s1-eth3", enabled=True, command_runner=runner
    )

    assert clear_command == (
        "tc",
        "class",
        "change",
        "dev",
        "s1-eth3",
        "classid",
        "5:1",
        "htb",
        "rate",
        "10Mbit",
        "ceil",
        "10Mbit",
    )
    assert runner.commands[-1][0] == list(clear_command)


def test_configured_capacity_must_match_htb_root_ceiling():
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(ValueError, match="does not match"):
        apply_qos_policy(
            "s1-eth3",
            decision("NORMAL", 4),
            12,
            enabled=True,
            command_runner=runner,
        )
    assert len(runner.commands) == 1


def test_unknown_active_policy_is_not_cleared_by_guessing():
    runner = CommandRecorder([ROOT_CLASS_OUTPUT], [])

    with pytest.raises(QosEnforcementError, match="no original HTB rates"):
        clear_qos_policy(
            "s1-eth3", enabled=True, command_runner=runner
        )
