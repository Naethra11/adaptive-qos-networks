# Phase 6.4 Mininet experiment protocol

Phase 6.4 measures behavior in the project's controlled Mininet shared
bottleneck testbed. It is separate from Phase 6.3 software-level ablation
metrics, which summarize decision outputs rather than observed network traffic.

> The Phase 6.4 measurements are controlled Mininet/WSL testbed observations
> and are not claims about production-network performance.

The configured 10 Mbps bottleneck is a testbed parameter, not a representation
of physical Internet capacity. Virtualized Mininet/WSL measurements can contain
measurement artifacts; throughput utilization is left unclamped, including
values above 100%. No condition is presumed superior based on these measures.

## Testbed and bottleneck

Use the existing topology in `src/shared_bottleneck.py` without changing it:

```text
h1 --------\
             s1 ===== s2 -------- h2
h3 --------/       10 Mbps
```

Source and destination host-side links are configured at 100 Mbps with 1 ms
delay. The shared s1–s2 link is configured at 10 Mbps with 5 ms delay. The
enforcement interface is `s1-eth3`, using existing root HTB class `5:1`.

## Conditions and trials

Each condition uses the same topology, two flows, 20-second iperf3 duration,
20-packet loaded ping, and measurement parsers:

| Condition | Bottleneck rate |
|---|---:|
| BASELINE | 10.0 Mbps |
| NORMAL | 4.0 Mbps |
| QUARANTINED | 0.5 Mbps |

Three trials are configured per condition. The harness explicitly applies
the rate through `qos_enforcer.apply_qos_policy()`, verifies the observed HTB
rate before traffic, checks that qdisc counters and backlog remain idle over a
short pre-trial window, restores 10 Mbps after every trial, and verifies the
baseline again after the session. The harness does not change rate unless the
experiment function is explicitly invoked.

## Traffic and measurements

Two simultaneous TCP flows run to h2:

- h1 → h2, iperf3 port 5201
- h3 → h2, iperf3 port 5202

iperf3 JSON receiver-side throughput is the primary measure. Sender throughput
is supplementary. Retransmissions are recorded when present in sender-side
iperf3 results; unavailable values remain `None`.

During the loaded flows, h3 pings h2 with `ping -n -c 20`. The pre-session
reference measurement is an unloaded h3-to-h2 20-packet ping. Loaded and
unloaded values are retained separately. Linux `rtt_mdev_ms` is labeled as an
RTT-variation proxy, not as a standardized jitter measurement.

Jain fairness is calculated only from the two receiver throughputs:

```text
J = (x1 + x2)^2 / (2 * (x1^2 + x2^2))
```

where `x1` and `x2` are flow 1 and flow 2 receiver Mbps.

## qdisc and class telemetry

For each trial, the harness collects the existing `NetworkTelemetry` snapshot
and `tc -s class show dev s1-eth3` before and after traffic. It records
per-trial counter deltas for qdisc sent packets, drops, and overlimits; class
drops and overlimits are kept distinct from qdisc drops. Post-trial backlog
packets and configured HTB rate are also recorded. Cumulative counters are not
reported as per-trial counts: deltas are computed as post minus pre. A counter
reset (negative delta) is explicitly reported as unavailable and invalidates
the trial rather than being silently interpreted.

## Validity and aggregation

A trial is valid only when both iperf3 flows start and finish with the complete
configured duration, required iperf/ping/qdisc/class measurements parse, the
interface remains up, and no unrelated command fails. Every attempted trial is
returned; failures have `valid=False` and explanatory notes. Invalid trials
are not silently discarded or rerun in their place.

Condition summaries use valid trials only, list valid and invalid counts, and
calculate available-measurement means and population standard deviation.
Throughput utilization is the raw mean aggregate receiver Mbps divided by the
configured condition rate, multiplied by 100. No confidence intervals,
significance tests, or population estimates are calculated.

## Environment limitations

The runner expects an already running topology, Linux `mnexec`, `iperf3`,
`ping`, `ss`, `ip`, and `tc`, and suitable privilege for changing the Mininet
HTB class. It does not invoke sudo, create the topology, or run on import.
Tests mock process, command, telemetry, and enforcement interfaces and require
no Mininet, root, OVS, or live network.

## Manual execution

In WSL, install the host tools if necessary:

```bash
sudo apt-get update
sudo apt-get install -y mininet iperf3 iputils-ping iproute2
```

From the repository root, start the existing topology in terminal 1:

```bash
sudo python3 src/shared_bottleneck.py
```

At the `mininet>` prompt, record each Mininet host namespace PID:

```text
py net.get('h1').pid
py net.get('h2').pid
py net.get('h3').pid
```

Leave the topology running. In terminal 2, from the repository root, explicitly
run the experiment with the recorded integer PIDs (replace the examples):

```bash
sudo python3 -m src.mininet_experiment \
  --run-experiment \
  --h1-pid 1234 \
  --h2-pid 1235 \
  --h3-pid 1236
```

The defaults run three trials per condition at 20 seconds and 20 ping packets.
One JSON object containing `no_load_ping`, `trials`, and `summary` is printed
to stdout; capture the output manually if it should be preserved. Trial or
session errors are also reported to stderr and produce a non-zero exit status,
while completed trial records remain in the JSON when available. To shorten a
deliberate test run, pass
`--trials`, `--duration`, and `--ping-count`; record any non-default settings
with the captured output. The CLI refuses to run without `--run-experiment`
and does not invoke sudo itself.
