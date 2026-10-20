"""Read-only Linux traffic-control and interface telemetry collection."""

from dataclasses import asdict, dataclass
import re
import subprocess
from typing import Any, Sequence


DEFAULT_INTERFACE = "s1-eth3"
COMMAND_TIMEOUT_SECONDS = 5
_INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True)
class NetworkTelemetry:
    interface: str
    qdisc_sent_bytes: int
    qdisc_sent_packets: int
    qdisc_dropped_packets: int
    qdisc_overlimits: int
    qdisc_backlog_bytes: int
    qdisc_backlog_packets: int
    htb_configured_rate: str
    interface_rx_bytes: int
    interface_rx_packets: int
    interface_rx_errors: int
    interface_rx_drops: int
    interface_tx_bytes: int
    interface_tx_packets: int
    interface_tx_errors: int
    interface_tx_drops: int

    def to_dict(self) -> dict[str, Any]:
        """Return telemetry as a plain dictionary."""
        return asdict(self)


def collect_network_telemetry(interface: str = DEFAULT_INTERFACE) -> NetworkTelemetry:
    """Read qdisc, HTB class, and interface counters without changing state."""
    if not isinstance(interface, str) or not _INTERFACE_PATTERN.fullmatch(interface):
        raise ValueError("interface must contain only letters, digits, '_', '.', ':', or '-'.")

    qdisc_result = _run_readonly(["tc", "-s", "qdisc", "show", "dev", interface])
    class_result = _run_readonly(["tc", "-s", "class", "show", "dev", interface])
    link_result = _run_readonly(["ip", "-s", "link", "show", "dev", interface])

    qdisc = parse_qdisc_statistics(qdisc_result.stdout)
    htb_rate = parse_htb_rate(class_result.stdout)
    link = parse_interface_statistics(link_result.stdout)

    return NetworkTelemetry(
        interface=interface,
        **qdisc,
        htb_configured_rate=htb_rate,
        **link,
    )


def parse_qdisc_statistics(output: str) -> dict[str, int]:
    """Parse counters from the root qdisc's ``tc -s qdisc`` output."""
    blocks = re.split(r"(?m)(?=^qdisc\s+)", output.strip())
    root_block = next(
        (
            block for block in blocks
            if block.startswith("qdisc ") and re.search(r"\broot\b", block.splitlines()[0])
        ),
        None,
    )
    if root_block is None:
        raise ValueError("tc output does not contain a root qdisc.")

    sent = re.search(
        r"\bSent\s+(\d+)\s+bytes\s+(\d+)\s+pkt\s*"
        r"\(dropped\s+(\d+),\s*overlimits\s+(\d+)\b",
        root_block,
    )
    backlog = re.search(
        r"\bbacklog\s+(\d+(?:\.\d+)?[KMG]?b)\s+(\d+)p\b",
        root_block,
        re.IGNORECASE,
    )
    if sent is None:
        raise ValueError("tc root qdisc output is missing sent/drop/overlimit statistics.")
    if backlog is None:
        raise ValueError("tc root qdisc output is missing backlog statistics.")

    return {
        "qdisc_sent_bytes": int(sent.group(1)),
        "qdisc_sent_packets": int(sent.group(2)),
        "qdisc_dropped_packets": int(sent.group(3)),
        "qdisc_overlimits": int(sent.group(4)),
        "qdisc_backlog_bytes": _parse_tc_bytes(backlog.group(1)),
        "qdisc_backlog_packets": int(backlog.group(2)),
    }


def parse_htb_rate(output: str) -> str:
    """Return the configured rate from the root HTB class."""
    for line in output.splitlines():
        if re.search(r"^\s*class\s+htb\b", line) and re.search(r"\broot\b", line):
            rate = re.search(r"\brate\s+([^\s]+)", line)
            if rate:
                return rate.group(1)
    raise ValueError("tc class output does not contain a root HTB class rate.")


def parse_interface_statistics(output: str) -> dict[str, int]:
    """Parse RX/TX byte, packet, error, and drop counters from ``ip -s link``."""
    stats: dict[str, int] = {}
    for direction in ("RX", "TX"):
        match = re.search(
            rf"(?m)^\s*{direction}:\s*([A-Za-z ]+)\r?\n"
            rf"\s*(\d+(?:\s+\d+)+)\s*$",
            output,
        )
        if match is None:
            raise ValueError(f"ip link output is missing {direction} counters.")
        columns = match.group(1).split()
        values = [int(value) for value in match.group(2).split()]
        if len(columns) != len(values):
            raise ValueError(f"ip link {direction} counter columns do not match their values.")
        counters = dict(zip(columns, values))
        required = ("bytes", "packets", "errors", "dropped")
        missing = [name for name in required if name not in counters]
        if missing:
            raise ValueError(f"ip link {direction} counters are missing: {', '.join(missing)}.")
        prefix = f"interface_{direction.lower()}_"
        stats.update({
            f"{prefix}{'drops' if name == 'dropped' else name}": counters[name]
            for name in required
        })
    return stats


def _run_readonly(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Execute a fixed, read-only system command without invoking a shell."""
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _parse_tc_bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)b", value, re.IGNORECASE)
    if match is None:
        raise ValueError(f"Unsupported tc byte quantity: {value}")
    amount = float(match.group(1))
    exponent = {"": 0, "K": 1, "M": 2, "G": 3}[match.group(2).upper()]
    return int(amount * (1024 ** exponent))
