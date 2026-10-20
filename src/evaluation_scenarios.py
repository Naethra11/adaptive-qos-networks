"""Fixed scenario matrix for reproducible software-level QoS ablations.

The same deterministic ``NetworkInput`` scenarios are available to each
Phase 1–4 ablation variant so variant comparisons use identical inputs. This
matrix is intended for software-level evaluation only; it is not a Mininet or
real-network experiment matrix, and its values are not statistically sampled
or claimed to be scientifically optimal. Hysteresis boundary scenarios place
inputs in relevant operating regions but do not guarantee exact decision
scores at the configured thresholds.
"""

from dataclasses import dataclass

from src.models import NetworkInput


@dataclass(frozen=True)
class Scenario:
    """Named, described, and deterministic decision-engine test input."""

    scenario_id: str
    description: str
    network_input: NetworkInput


def get_evaluation_scenarios() -> list[Scenario]:
    """Return the fixed 22-scenario matrix in its documented order."""
    definitions = (
        (
            "S01_SAFE_HIGH_PRIORITY",
            "Safe, high-priority latency-sensitive Video Call conditions.",
            "Video Call", 1, 2, 50, 10, 95, 35,
        ),
        (
            "S02_HIGH_THREAT",
            "High threat and low trust test security override despite priority.",
            "Video Call", 9, 2, 50, 10, 15, 40,
        ),
        (
            "S03_MODERATE_RISK",
            "Moderate threat, trust, and network conditions.",
            "Web Browsing", 5, 5, 30, 6, 60, 100,
        ),
        (
            "S04_LOW_BANDWIDTH",
            "Legitimate Video Call with scarce available bandwidth.",
            "Video Call", 1, 3, 5, 8, 90, 45,
        ),
        (
            "S05_HIGH_CONGESTION",
            "Legitimate traffic with high congestion and ample bandwidth.",
            "Web Browsing", 1, 9, 80, 7, 90, 90,
        ),
        (
            "S06_HIGH_LATENCY",
            "Latency-sensitive Voice Call under high measured latency input.",
            "Voice Call", 1, 3, 50, 9, 95, 280,
        ),
        (
            "S07_BACKGROUND_LOW_PRIORITY",
            "Relatively safe, low-priority background file traffic.",
            "Background Traffic", 1, 3, 50, 1, 95, 120,
        ),
        (
            "S08_SUSPICIOUS_TRAFFIC",
            "Suspicious traffic type with elevated threat and reduced trust.",
            "Suspicious Traffic", 7, 5, 30, 7, 35, 100,
        ),
        (
            "S09_RISING_T1",
            "First observation in the ordered rising-threat sequence.",
            "Video Call", 2, 3, 50, 8, 90, 45,
        ),
        (
            "S10_RISING_T2",
            "Second observation in the rising-threat sequence; follow S09.",
            "Video Call", 4, 3, 50, 8, 90, 45,
        ),
        (
            "S11_RISING_T3",
            "Third observation in the rising-threat sequence; follow S10.",
            "Video Call", 7, 3, 50, 8, 90, 45,
        ),
        (
            "S12_FALLING_T1",
            "First observation in the ordered falling-threat sequence.",
            "Video Call", 8, 3, 50, 8, 90, 45,
        ),
        (
            "S13_FALLING_T2",
            "Second observation in the falling-threat sequence; follow S12.",
            "Video Call", 5, 3, 50, 8, 90, 45,
        ),
        (
            "S14_FALLING_T3",
            "Third observation in the falling-threat sequence; follow S13.",
            "Video Call", 2, 3, 50, 8, 90, 45,
        ),
        (
            "S15_HYST_NORMAL_EXIT_REGION",
            "Input region for examining scores around NORMAL exit at 45.",
            "Web Browsing", 2, 6, 35, 4, 85, 110,
        ),
        (
            "S16_HYST_NORMAL_ENTER_REGION",
            "Input region for examining scores around NORMAL entry at 50.",
            "Web Browsing", 1, 4, 45, 5, 90, 90,
        ),
        (
            "S17_HYST_HIGH_EXIT_REGION",
            "Input region for examining scores around HIGH exit at 65.",
            "Video Call", 1, 4, 55, 7, 95, 65,
        ),
        (
            "S18_HYST_HIGH_ENTER_REGION",
            "Input region for examining scores around HIGH entry at 70.",
            "Video Call", 1, 3, 65, 8, 95, 50,
        ),
        (
            "S19_HYST_CRITICAL_EXIT_REGION",
            "Input region for examining scores around CRITICAL exit at 80.",
            "Video Call", 1, 2, 80, 9, 98, 30,
        ),
        (
            "S20_HYST_CRITICAL_ENTER_REGION",
            "Input region for examining scores around CRITICAL entry at 85.",
            "Video Call", 0, 1, 100, 10, 100, 10,
        ),
        (
            "S21_RISK_NEAR_RMAX",
            "Raw risk is near but below R_MAX: threat 8, trust 80 gives 62.",
            "Web Browsing", 8, 3, 50, 6, 80, 80,
        ),
        (
            "S22_RISK_ABOVE_RMAX",
            "Raw risk exceeds R_MAX: threat 9, trust 70 gives 72.",
            "Web Browsing", 9, 3, 50, 6, 70, 80,
        ),
    )
    return [
        Scenario(
            scenario_id=scenario_id,
            description=description,
            network_input=NetworkInput(
                traffic_type=traffic_type,
                threat_level=threat_level,
                congestion=congestion,
                bandwidth_available=bandwidth_available,
                application_priority=application_priority,
                device_trust=device_trust,
                latency=latency,
            ),
        )
        for (
            scenario_id,
            description,
            traffic_type,
            threat_level,
            congestion,
            bandwidth_available,
            application_priority,
            device_trust,
            latency,
        ) in definitions
    ]
