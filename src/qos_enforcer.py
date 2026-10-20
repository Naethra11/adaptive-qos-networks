"""Opt-in rate enforcement for Mininet switch interfaces only.

This module adjusts the existing root HTB class in place. It deliberately
does not replace the root qdisc, which could discard Mininet's configured
delay or other qdisc settings. Original root-class rates are cached in-process
so :func:`clear_qos_policy` can restore them after one or more policy updates.
"""

from dataclasses import dataclass
import math
import re
import subprocess
from threading import RLock
from typing import Callable, Sequence

from src.models import DecisionResult


_MININET_SWITCH_INTERFACE = re.compile(r"^s\d+-eth\d+$")
_ROOT_HTB_CLASS = re.compile(
    r"(?m)^\s*class\s+htb\s+(\S+)\s+root\b[^\r\n]*"
    r"\brate\s+(\S+)[^\r\n]*\bceil\s+(\S+)"
)
_RATE = re.compile(r"^(\d+(?:\.\d+)?)(bit|kbit|mbit|gbit)$", re.IGNORECASE)
_COMMAND_TIMEOUT_SECONDS = 5


class QosEnforcementError(RuntimeError):
    """Raised when tc state cannot be safely inspected or changed."""


@dataclass(frozen=True)
class QosEnforcementResult:
    interface: str
    policy: str
    requested_rate_mbps: float
    class_id: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class _OriginalClassRates:
    class_id: str
    rate: str
    ceil: str
    capacity_mbps: float


_APPLIED_STATE: dict[str, _OriginalClassRates] = {}
_STATE_LOCK = RLock()

_SUPPORTED_POLICIES = {
    "CRITICAL PRIORITY",
    "HIGH PRIORITY",
    "NORMAL",
    "LOW / RATE LIMITED",
    "QUARANTINED",
}

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def apply_qos_policy(
    interface: str,
    decision_result: DecisionResult,
    configured_capacity_mbps: float,
    *,
    enabled: bool = False,
    command_runner: CommandRunner | None = None,
) -> QosEnforcementResult:
    """Set the selected decision's bandwidth as the root HTB class rate.

    Enforcement is disabled unless the caller explicitly supplies
    ``enabled=True``. The interface must be a Mininet switch port (``sN-ethN``),
    and the decision's positive allocation must not exceed the caller-supplied
    bottleneck capacity. The reported HTB ceiling is also checked against that
    capacity before any mutation.

    The existing root HTB class is updated using ``tc class change`` with both
    ``rate`` and ``ceil`` set to the decision allocation. The original values
    are retained in process memory for :func:`clear_qos_policy`.
    """
    if not enabled:
        raise PermissionError(
            "QoS enforcement is opt-in; call with enabled=True to proceed."
        )
    _validate_interface(interface)
    if not isinstance(decision_result, DecisionResult):
        raise TypeError("decision_result must be a DecisionResult.")

    capacity = _finite_positive(configured_capacity_mbps, "configured_capacity_mbps")
    requested = _finite_positive(
        decision_result.bandwidth_allocation,
        "decision_result.bandwidth_allocation",
    )
    if requested > capacity:
        raise ValueError(
            "Requested bandwidth cannot exceed configured bottleneck capacity."
        )
    if decision_result.qos_policy not in _SUPPORTED_POLICIES:
        raise ValueError(f"Unsupported decision policy: {decision_result.qos_policy!r}.")

    runner = command_runner or subprocess.run
    with _STATE_LOCK:
        original = _APPLIED_STATE.get(interface)
        if original is None:
            class_id, current_rate, current_ceil = _read_root_htb_class(
                interface, runner
            )
            original_capacity = _rate_to_mbps(current_ceil)
            if not math.isclose(original_capacity, capacity, rel_tol=1e-6):
                raise ValueError(
                    "Configured bottleneck capacity does not match the interface "
                    f"root HTB ceiling ({current_ceil})."
                )
            original = _OriginalClassRates(
                class_id=class_id,
                rate=current_rate,
                ceil=current_ceil,
                capacity_mbps=original_capacity,
            )
        elif not math.isclose(original.capacity_mbps, capacity, rel_tol=1e-6):
            raise ValueError(
                "Configured bottleneck capacity differs from the captured "
                "original HTB ceiling."
            )

        rate = f"{requested:g}mbit"
        command = (
            "tc",
            "class",
            "change",
            "dev",
            interface,
            "classid",
            original.class_id,
            "htb",
            "rate",
            rate,
            "ceil",
            rate,
        )
        _run_tc(command, runner)
        _APPLIED_STATE[interface] = original

    return QosEnforcementResult(
        interface=interface,
        policy=decision_result.qos_policy,
        requested_rate_mbps=requested,
        class_id=original.class_id,
        command=command,
    )


def clear_qos_policy(
    interface: str,
    *,
    enabled: bool = False,
    command_runner: CommandRunner | None = None,
) -> tuple[str, ...]:
    """Restore the root HTB rates captured by a prior explicit apply call.

    The original class rates are kept in process memory. If this process did
    not apply a policy to the interface, state is ambiguous (including after a
    process restart) and the function refuses to guess.
    """
    if not enabled:
        raise PermissionError(
            "QoS enforcement is opt-in; call with enabled=True to proceed."
        )
    _validate_interface(interface)
    runner = command_runner or subprocess.run

    with _STATE_LOCK:
        original = _APPLIED_STATE.get(interface)
        if original is None:
            raise QosEnforcementError(
                "Cannot clear this interface safely: no original HTB rates were "
                "captured by this process. Clear must run in the process that "
                "applied the policy."
            )

        command = (
            "tc",
            "class",
            "change",
            "dev",
            interface,
            "classid",
            original.class_id,
            "htb",
            "rate",
            original.rate,
            "ceil",
            original.ceil,
        )
        _run_tc(command, runner)
        del _APPLIED_STATE[interface]
        return command


def _read_root_htb_class(
    interface: str,
    runner: CommandRunner,
) -> tuple[str, str, str]:
    command = ("tc", "class", "show", "dev", interface)
    result = _run_tc(command, runner)
    match = _ROOT_HTB_CLASS.search(result.stdout)
    if match is None:
        raise QosEnforcementError(
            f"No root HTB class with rate and ceiling found on {interface}."
        )
    class_id, rate, ceil = match.groups()
    _rate_to_mbps(rate)
    _rate_to_mbps(ceil)
    return class_id, rate, ceil


def _run_tc(
    command: Sequence[str],
    runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise QosEnforcementError(
            f"tc command failed for interface {command[4]}: {error}"
        ) from error


def _validate_interface(interface: str) -> None:
    if not isinstance(interface, str) or not _MININET_SWITCH_INTERFACE.fullmatch(
        interface
    ):
        raise ValueError(
            "interface must be a Mininet switch port name such as 's1-eth3'."
        )


def _finite_positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite positive number.")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number.")
    return float(value)


def _rate_to_mbps(rate: str) -> float:
    match = _RATE.fullmatch(rate)
    if match is None:
        raise QosEnforcementError(f"Unsupported HTB rate value: {rate!r}.")
    amount = float(match.group(1))
    multiplier = {
        "bit": 1,
        "kbit": 1_000,
        "mbit": 1_000_000,
        "gbit": 1_000_000_000,
    }[match.group(2).lower()]
    return amount * multiplier / 1_000_000
