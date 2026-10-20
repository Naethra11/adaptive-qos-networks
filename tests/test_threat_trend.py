import pytest

from src.decision_engine import load_config
from src.threat_trend import (
    STABLE,
    TRENDING_DOWN,
    TRENDING_UP,
    update_threat_trend,
)


def update_sequence(threat_levels: list[float]) -> list:
    temporal = load_config()["temporal"]
    previous = None
    results = []
    for threat_level in threat_levels:
        result = update_threat_trend(
            threat_level,
            previous,
            alpha=temporal["alpha"],
            trend_threshold=temporal["trend_threshold"],
        )
        results.append(result)
        previous = result.smoothed_threat
    return results


def test_first_observation_initializes_smoothed_threat():
    result = update_threat_trend(6, None, alpha=0.4, trend_threshold=5)

    assert result.normalized_threat == 60
    assert result.smoothed_threat == 60
    assert result.trend_delta == 0
    assert result.trend == STABLE


def test_repeated_stable_threat_values_classify_stable():
    results = update_sequence([4, 4, 4, 4])

    assert [result.smoothed_threat for result in results] == [40, 40, 40, 40]
    assert all(result.trend == STABLE for result in results)


def test_increasing_threat_sequence_classifies_trending_up():
    results = update_sequence([2, 4, 6, 8])

    assert [result.trend for result in results] == [
        STABLE,
        TRENDING_UP,
        TRENDING_UP,
        TRENDING_UP,
    ]


def test_decreasing_threat_sequence_classifies_trending_down():
    results = update_sequence([8, 6, 4, 2])

    assert [result.trend for result in results] == [
        STABLE,
        TRENDING_DOWN,
        TRENDING_DOWN,
        TRENDING_DOWN,
    ]


@pytest.mark.parametrize("threat_level", [0, 1, 5, 10])
def test_ewma_remains_within_0_to_100(threat_level):
    result = update_threat_trend(
        threat_level,
        100 if threat_level < 10 else 0,
        alpha=0.4,
        trend_threshold=5,
    )

    assert 0 <= result.smoothed_threat <= 100


@pytest.mark.parametrize("alpha", [0, -0.1, 1.01, float("nan"), float("inf")])
def test_invalid_alpha_raises_clear_value_error(alpha):
    with pytest.raises(ValueError, match="alpha"):
        update_threat_trend(5, None, alpha=alpha, trend_threshold=5)


def test_trend_threshold_is_configurable():
    result = update_threat_trend(6, 50, alpha=0.4, trend_threshold=5)
    stable_result = update_threat_trend(6, 50, alpha=0.4, trend_threshold=20)

    assert result.trend_delta == 4
    assert result.trend == STABLE
    assert stable_result.trend == STABLE


def test_trend_threshold_classifies_same_change_differently():
    low_threshold = update_threat_trend(
        7, 50, alpha=0.4, trend_threshold=5
    )
    high_threshold = update_threat_trend(
        7, 50, alpha=0.4, trend_threshold=10
    )

    assert low_threshold.trend_delta == 8
    assert low_threshold.trend == TRENDING_UP
    assert high_threshold.trend == STABLE


@pytest.mark.parametrize("threat_level", [-0.1, 10.1, float("nan")])
def test_invalid_threat_observation_raises_value_error(threat_level):
    with pytest.raises(ValueError, match="threat_level"):
        update_threat_trend(
            threat_level, None, alpha=0.4, trend_threshold=5
        )
