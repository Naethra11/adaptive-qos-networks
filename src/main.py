from models import NetworkInput
from decision_engine import make_decision


def main() -> None:
    """Run a simple demonstration of the decision engine."""

    video_call = NetworkInput(
        traffic_type="Video Call",
        threat_level=2,
        congestion=8,
        bandwidth_available=25,
        application_priority=9,
        device_trust=90,
        latency=80,
    )

    result = make_decision(video_call)

    print("\n===== ADAPTIVE SMART QoS =====")
    print(f"Decision Score       : {result.decision_score}")
    print(f"Priority             : {result.priority}")
    print(f"QoS Policy           : {result.qos_policy}")
    print(f"Bandwidth Allocation : {result.bandwidth_allocation} Mbps")
    print(f"Queue                : {result.queue}")
    print(f"Security Action      : {result.security_action}")
    print(f"Reason               : {result.reason}")
    print("==============================\n")


if __name__ == "__main__":
    main()