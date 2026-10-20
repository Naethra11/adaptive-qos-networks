"""Temporal adjustments to Phase 2 raw security risk."""

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from src.threat_trend import STABLE, TRENDING_DOWN, TRENDING_UP


@dataclass(frozen=True)
class TemporalRiskAssessment:
    """Raw and temporally adjusted risk values with an explanation."""

    raw_security_risk: float
    smoothed_threat: float
    threat_trend: str
    temporal_adjustment: float
    effective_security_risk: float
    risk_budget_status: str
    explanation: str


def calculate_effective_risk(
    raw_security_risk: float,
    threat_trend: str,
    risk_adjustment: Mapping[str, float],
    *,
    enabled: bool = True,
) -> tuple[float, float]:
    """Return the configured temporal adjustment and clamped effective risk."""
    if not isinstance(raw_security_risk, (int, float)) or not isfinite(raw_security_risk):
        raise ValueError("raw_security_risk must be a finite number.")
    if not 0 <= raw_security_risk <= 100:
        raise ValueError("raw_security_risk must be between 0 and 100.")

    adjustment_key = {
        TRENDING_UP: "trending_up",
        STABLE: "stable",
        TRENDING_DOWN: "trending_down",
    }.get(threat_trend)
    if adjustment_key is None:
        raise ValueError(f"Unsupported threat trend: {threat_trend}")

    configured_adjustment = risk_adjustment[adjustment_key]
    if not isinstance(configured_adjustment, (int, float)) or not isfinite(configured_adjustment):
        raise ValueError(f"temporal.risk_adjustment.{adjustment_key} must be finite.")
    adjustment = float(configured_adjustment) if enabled else 0.0
    effective_risk = min(100.0, max(0.0, raw_security_risk + adjustment))
    return round(adjustment, 2), round(effective_risk, 2)


def explain_temporal_adjustment(
    raw_security_risk: float,
    smoothed_threat: float,
    threat_trend: str,
    temporal_adjustment: float,
    effective_security_risk: float,
    r_max: float,
) -> str:
    """Explain how the observed threat trend affects the risk-budget result."""
    status = "satisfied" if effective_security_risk <= r_max else "violated"
    if temporal_adjustment > 0:
        adjustment_text = f"increased risk by {temporal_adjustment:.2f}"
    elif temporal_adjustment < 0:
        adjustment_text = f"reduced risk by {abs(temporal_adjustment):.2f}"
    else:
        adjustment_text = "did not adjust risk"
    return (
        f"Raw security risk is {raw_security_risk:.2f}; smoothed threat is "
        f"{smoothed_threat:.2f} with trend {threat_trend}. The temporal trend "
        f"{adjustment_text}, giving effective security risk "
        f"{effective_security_risk:.2f}; risk budget R_MAX {r_max:.2f} is {status}."
    )


def assess_temporal_risk(
    raw_security_risk: float,
    smoothed_threat: float,
    threat_trend: str,
    temporal_config: Mapping[str, Any],
    r_max: float,
) -> TemporalRiskAssessment:
    """Combine raw Phase 2 risk with the configured temporal adjustment."""
    adjustment, effective_risk = calculate_effective_risk(
        raw_security_risk,
        threat_trend,
        temporal_config["risk_adjustment"],
        enabled=bool(temporal_config["enabled"]),
    )
    if not 0 <= smoothed_threat <= 100:
        raise ValueError("smoothed_threat must be between 0 and 100.")
    status = "SATISFIED" if effective_risk <= r_max else "VIOLATED"
    explanation = explain_temporal_adjustment(
        raw_security_risk,
        smoothed_threat,
        threat_trend,
        adjustment,
        effective_risk,
        r_max,
    )
    return TemporalRiskAssessment(
        raw_security_risk=round(raw_security_risk, 2),
        smoothed_threat=round(smoothed_threat, 2),
        threat_trend=threat_trend,
        temporal_adjustment=adjustment,
        effective_security_risk=effective_risk,
        risk_budget_status=status,
        explanation=explanation,
    )
