from typing import Dict


def calculate_decision_score(
    normalized_factors: Dict[str, float],
    weights: Dict[str, float]
) -> float:
    """
    Calculate the weighted Multi-Factor Decision Score.

    Every factor must already be normalized to 0-100.
    The weights should add up to 1.0.
    """

    if not normalized_factors:
        raise ValueError("No normalized factors were provided.")

    if not weights:
        raise ValueError("No weights were provided.")

    missing_factors = set(weights) - set(normalized_factors)

    if missing_factors:
        raise ValueError(
            f"Missing normalized factors: {missing_factors}"
        )

    total_weight = sum(weights.values())

    if abs(total_weight - 1.0) > 0.001:
        raise ValueError(
            f"Weights must sum to 1.0. Current total: {total_weight}"
        )

    score = sum(
        normalized_factors[factor] * weight
        for factor, weight in weights.items()
    )

    return round(score, 2)


def calculate_factor_contributions(
    normalized_factors: Dict[str, float],
    weights: Dict[str, float]
) -> Dict[str, float]:
    """
    Calculate the contribution of each factor to the
    final Multi-Factor Decision Score.

    Each contribution is:

        normalized factor × dynamic weight
    """

    if not normalized_factors:
        raise ValueError("No normalized factors were provided.")

    if not weights:
        raise ValueError("No weights were provided.")

    missing_factors = set(weights) - set(normalized_factors)

    if missing_factors:
        raise ValueError(
            f"Missing normalized factors: {missing_factors}"
        )

    total_weight = sum(weights.values())

    if abs(total_weight - 1.0) > 0.001:
        raise ValueError(
            f"Weights must sum to 1.0. Current total: {total_weight}"
        )

    contributions = {
        factor: round(
            normalized_factors[factor] * weight,
            2
        )
        for factor, weight in weights.items()
    }

    return contributions