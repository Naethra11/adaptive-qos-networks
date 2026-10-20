"""Deterministic EWMA smoothing and trend classification for threat levels."""

from dataclasses import dataclass
from math import isfinite

TRENDING_UP = "TRENDING_UP"
STABLE = "STABLE"
TRENDING_DOWN = "TRENDING_DOWN"


@dataclass(frozen=True)
class ThreatTrend:
    """One temporal threat observation and its EWMA trend."""

    normalized_threat: float
    previous_smoothed_threat: float | None
    smoothed_threat: float
    trend_delta: float
    trend: str


def update_threat_trend(
    threat_level: float,
    previous_smoothed_threat: float | None,
    *,
    alpha: float,
    trend_threshold: float,
) -> ThreatTrend:
    """Update the EWMA with a raw 0-10 threat observation.

    The observation is first converted to a 0-100 scale. The first observation
    initializes the smoother directly; subsequent observations use
    ``S_t = alpha * T_t + (1 - alpha) * S_(t-1)``.
    """
    _validate_finite(alpha, "alpha")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be greater than 0 and at most 1.")
    _validate_finite(trend_threshold, "trend_threshold")
    if not 0 <= trend_threshold <= 100:
        raise ValueError("trend_threshold must be between 0 and 100.")
    _validate_finite(threat_level, "threat_level")
    if not 0 <= threat_level <= 10:
        raise ValueError("threat_level must be between 0 and 10.")

    if previous_smoothed_threat is not None:
        _validate_finite(previous_smoothed_threat, "previous_smoothed_threat")
        if not 0 <= previous_smoothed_threat <= 100:
            raise ValueError("previous_smoothed_threat must be between 0 and 100.")

    normalized_threat = threat_level * 10
    if previous_smoothed_threat is None:
        smoothed_threat = normalized_threat
        trend_delta = 0.0
        trend = STABLE
    else:
        smoothed_threat = (
            alpha * normalized_threat
            + (1 - alpha) * previous_smoothed_threat
        )
        trend_delta = smoothed_threat - previous_smoothed_threat
        if trend_delta > trend_threshold:
            trend = TRENDING_UP
        elif trend_delta < -trend_threshold:
            trend = TRENDING_DOWN
        else:
            trend = STABLE

    smoothed_threat = round(min(100.0, max(0.0, smoothed_threat)), 2)
    trend_delta = round(trend_delta, 2)
    return ThreatTrend(
        normalized_threat=round(normalized_threat, 2),
        previous_smoothed_threat=previous_smoothed_threat,
        smoothed_threat=smoothed_threat,
        trend_delta=trend_delta,
        trend=trend,
    )


def _validate_finite(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
