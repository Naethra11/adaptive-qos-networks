"""Reproducible software-level metrics for Phase 1–4 ablation runs.

These outputs summarize deterministic software decisions over the fixed
scenario matrix. They are not throughput, latency, packet-loss, real-network,
or production-performance results, and are not population estimates or tests
of statistical significance.
"""

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from src.ablation import (
    PHASE1_BASELINE,
    PHASE2_RISK_AWARE,
    PHASE3_TEMPORAL,
    PHASE4_STABILITY,
    AblationResult,
    run_ablation_scenario,
)
from src.evaluation_scenarios import Scenario, get_evaluation_scenarios
from src.policy_stability import (
    POLICY_ORDER,
    calculate_policy_stability_index,
    calculate_policy_switch_rate,
    count_policy_switches,
)


VARIANTS = (
    PHASE1_BASELINE,
    PHASE2_RISK_AWARE,
    PHASE3_TEMPORAL,
    PHASE4_STABILITY,
)
TEMPORAL_VARIANTS = (PHASE3_TEMPORAL, PHASE4_STABILITY)
_TREND_LABELS = ("TRENDING_UP", "STABLE", "TRENDING_DOWN")
_SECURITY_OVERRIDE_ACTIONS = {"RESTRICT", "QUARANTINE"}
_DISTRIBUTION_POLICIES = (*POLICY_ORDER, "RATE LIMITED")
_SEQUENCE_MARKERS = (
    ("_RISING_", "RISING"),
    ("_FALLING_", "FALLING"),
    ("_HYST_", "HYSTERESIS"),
)


@dataclass(frozen=True)
class AblationRun:
    """One scenario evaluated by one ablation variant."""

    scenario_id: str
    variant: str
    result: AblationResult
    sequence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible record without serializing native objects."""
        return {
            "scenario_id": self.scenario_id,
            "variant": self.variant,
            "sequence_id": self.sequence_id,
            "result": _ablation_result_to_dict(self.result),
        }


@dataclass(frozen=True)
class PolicyDistribution:
    counts: Mapping[str, int]
    percentages: Mapping[str, float]
    total: int


@dataclass(frozen=True)
class RateMetric:
    numerator: int
    denominator: int
    rate: float


@dataclass(frozen=True)
class PolicySwitchMetrics:
    decisions: int
    switches: int
    psr: float
    psi: float


@dataclass(frozen=True)
class HysteresisEffect:
    scenario_ids: tuple[str, ...]
    candidate_policies: tuple[str, ...]
    final_policies: tuple[str, ...]
    candidate_switch_count: int
    final_switch_count: int


@dataclass(frozen=True)
class AblationMetrics:
    """Descriptive counts and means over the supplied deterministic runs."""

    scenario_count: int
    variant_count: int
    policy_distribution: Mapping[str, PolicyDistribution]
    security_override_rate: Mapping[str, RateMetric | None]
    risk_constraint_violation_rate: Mapping[str, RateMetric | None]
    mean_effective_security_risk: Mapping[str, float | None]
    mean_raw_security_risk: Mapping[str, float | None]
    mean_qos_utility: Mapping[str, float | None]
    temporal_trend_counts: Mapping[str, Mapping[str, int] | None]
    policy_switching_metrics: Mapping[
        str, Mapping[str, PolicySwitchMetrics]
    ]
    hysteresis_effect: HysteresisEffect | None
    phase_differences: Mapping[str, Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible summary; unavailable metrics stay null."""
        return asdict(self)


def run_ablation_matrix(
    scenarios: list[Scenario] | None = None,
) -> list[AblationRun]:
    """Run every scenario in order through each Phase 1–4 variant.

    Scenario IDs containing ``_RISING_``, ``_FALLING_``, or ``_HYST_`` mark
    independent ordered sequences. Their sequence-local histories are keyed by
    marker, separately for Phase 3 and Phase 4. For the hysteresis group,
    Phase 4 receives the preceding Phase 4 final policy. Every other scenario
    is independent: it receives no previous threat or policy state.
    """
    selected_scenarios = (
        get_evaluation_scenarios() if scenarios is None else scenarios
    )
    _validate_scenarios(selected_scenarios)
    runs: list[AblationRun] = []
    previous_smoothed: dict[tuple[str, str], float] = {}
    previous_policy: dict[str, str] = {}

    for scenario in selected_scenarios:
        sequence_id = _sequence_id(scenario.scenario_id)
        for variant in VARIANTS:
            temporal_key = (
                (variant, sequence_id) if sequence_id is not None else None
            )
            prior_smoothed = (
                previous_smoothed.get(temporal_key)
                if variant in TEMPORAL_VARIANTS and temporal_key is not None
                else None
            )
            prior_policy = (
                previous_policy.get(sequence_id)
                if variant == PHASE4_STABILITY and sequence_id is not None
                else None
            )
            result = run_ablation_scenario(
                scenario.network_input,
                previous_smoothed_threat=prior_smoothed,
                previous_policy=prior_policy,
                variant=variant,
            )
            runs.append(
                AblationRun(
                    scenario_id=scenario.scenario_id,
                    variant=variant,
                    result=result,
                    sequence_id=sequence_id,
                )
            )
            if (
                variant in TEMPORAL_VARIANTS
                and temporal_key is not None
                and result.smoothed_threat is not None
            ):
                previous_smoothed[temporal_key] = result.smoothed_threat
            if (
                variant == PHASE4_STABILITY
                and sequence_id is not None
            ):
                previous_policy[sequence_id] = result.policy
    return runs


def calculate_policy_distribution(
    runs: Iterable[AblationRun],
) -> dict[str, PolicyDistribution]:
    """Count and calculate per-policy percentages for each variant."""
    grouped = _group_by_variant(runs)
    distributions: dict[str, PolicyDistribution] = {}
    for variant in VARIANTS:
        variant_runs = grouped[variant]
        counts = {policy: 0 for policy in _DISTRIBUTION_POLICIES}
        for run in variant_runs:
            if run.result.policy not in counts:
                counts[run.result.policy] = 0
            counts[run.result.policy] += 1
        total = len(variant_runs)
        percentages = {
            policy: round(count / total * 100, 4) if total else 0.0
            for policy, count in counts.items()
        }
        distributions[variant] = PolicyDistribution(counts, percentages, total)
    return distributions


def calculate_security_override_rate(
    runs: Iterable[AblationRun],
) -> dict[str, RateMetric | None]:
    """Measure security restriction only for variants exposing that action."""
    grouped = _group_by_variant(runs)
    rates: dict[str, RateMetric | None] = {}
    for variant in VARIANTS:
        available = [
            run.result.security_action
            for run in grouped[variant]
            if run.result.security_action is not None
        ]
        if not available:
            rates[variant] = None
            continue
        overrides = sum(
            action in _SECURITY_OVERRIDE_ACTIONS for action in available
        )
        rates[variant] = RateMetric(
            numerator=overrides,
            denominator=len(available),
            rate=round(overrides / len(available), 4),
        )
    return rates


def calculate_risk_constraint_rate(
    runs: Iterable[AblationRun],
) -> dict[str, RateMetric | None]:
    """Calculate constraint violation only where risk status is available."""
    grouped = _group_by_variant(runs)
    rates: dict[str, RateMetric | None] = {}
    for variant in VARIANTS:
        available = [
            run.result.risk_budget_satisfied
            for run in grouped[variant]
            if run.result.risk_budget_satisfied is not None
        ]
        if not available:
            rates[variant] = None
            continue
        violations = sum(not satisfied for satisfied in available)
        rates[variant] = RateMetric(
            numerator=violations,
            denominator=len(available),
            rate=round(violations / len(available), 4),
        )
    return rates


def calculate_mean_risk(
    runs: Iterable[AblationRun],
    *,
    risk_field: str = "effective_security_risk",
) -> dict[str, float | None]:
    """Calculate per-variant mean risk, ignoring unavailable values."""
    if risk_field not in {"raw_security_risk", "effective_security_risk"}:
        raise ValueError(
            "risk_field must be 'raw_security_risk' or 'effective_security_risk'."
        )
    grouped = _group_by_variant(runs)
    return {
        variant: _mean(
            getattr(run.result, risk_field) for run in grouped[variant]
        )
        for variant in VARIANTS
    }


def calculate_mean_qos_utility(
    runs: Iterable[AblationRun],
) -> dict[str, float | None]:
    """Calculate mean QoS utility, ignoring variants without that field."""
    grouped = _group_by_variant(runs)
    return {
        variant: _mean(run.result.qos_utility for run in grouped[variant])
        for variant in VARIANTS
    }


def calculate_temporal_trend_counts(
    runs: Iterable[AblationRun],
) -> dict[str, dict[str, int] | None]:
    """Count temporal trend labels only where the evaluator exposes them."""
    grouped = _group_by_variant(runs)
    counts: dict[str, dict[str, int] | None] = {}
    for variant in VARIANTS:
        trends = [
            run.result.threat_trend
            for run in grouped[variant]
            if run.result.threat_trend is not None
        ]
        if not trends:
            counts[variant] = None
            continue
        variant_counts = {trend: 0 for trend in _TREND_LABELS}
        for trend in trends:
            if trend not in variant_counts:
                raise ValueError(f"Unsupported threat trend in run: {trend!r}.")
            variant_counts[trend] += 1
        counts[variant] = variant_counts
    return counts


def calculate_policy_switch_metrics(
    runs: Iterable[AblationRun],
) -> dict[str, dict[str, PolicySwitchMetrics]]:
    """Calculate PSR/PSI within each ordered sequence, never across boundaries."""
    grouped = _group_by_variant(runs)
    metrics: dict[str, dict[str, PolicySwitchMetrics]] = {}
    for variant in VARIANTS:
        sequences: dict[str, list[str]] = {}
        for run in grouped[variant]:
            if run.sequence_id is not None:
                sequences.setdefault(run.sequence_id, []).append(run.result.policy)
        metrics[variant] = {
            sequence_id: _switch_metrics(policies)
            for sequence_id, policies in sequences.items()
        }
    return metrics


def calculate_hysteresis_effect(
    runs: Iterable[AblationRun],
) -> HysteresisEffect | None:
    """Compare candidate and final policies within the marked hysteresis run."""
    selected = [
        run
        for run in runs
        if run.variant == PHASE4_STABILITY
        and run.sequence_id == "HYSTERESIS"
        and run.result.candidate_policy is not None
    ]
    if not selected:
        return None
    candidate_policies = tuple(run.result.candidate_policy for run in selected)
    final_policies = tuple(run.result.policy for run in selected)
    return HysteresisEffect(
        scenario_ids=tuple(run.scenario_id for run in selected),
        candidate_policies=candidate_policies,
        final_policies=final_policies,
        candidate_switch_count=count_policy_switches(candidate_policies),
        final_switch_count=count_policy_switches(final_policies),
    )


def summarize_ablation_runs(runs: Iterable[AblationRun]) -> AblationMetrics:
    """Summarize deterministic software results without inferential statistics."""
    run_list = list(runs)
    grouped = _group_by_variant(run_list)
    distributions = calculate_policy_distribution(run_list)
    override_rates = calculate_security_override_rate(run_list)
    risk_rates = calculate_risk_constraint_rate(run_list)
    mean_effective = calculate_mean_risk(run_list)
    mean_raw = calculate_mean_risk(run_list, risk_field="raw_security_risk")
    mean_utility = calculate_mean_qos_utility(run_list)
    trend_counts = calculate_temporal_trend_counts(run_list)
    switching = calculate_policy_switch_metrics(run_list)
    return AblationMetrics(
        scenario_count=len({run.scenario_id for run in run_list}),
        variant_count=sum(bool(grouped[variant]) for variant in VARIANTS),
        policy_distribution=distributions,
        security_override_rate=override_rates,
        risk_constraint_violation_rate=risk_rates,
        mean_effective_security_risk=mean_effective,
        mean_raw_security_risk=mean_raw,
        mean_qos_utility=mean_utility,
        temporal_trend_counts=trend_counts,
        policy_switching_metrics=switching,
        hysteresis_effect=calculate_hysteresis_effect(run_list),
        phase_differences=_calculate_phase_differences(
            distributions,
            risk_rates,
            mean_effective,
            mean_raw,
            mean_utility,
        ),
    )


def _calculate_phase_differences(
    distributions: Mapping[str, PolicyDistribution],
    violation_rates: Mapping[str, RateMetric | None],
    mean_effective_risk: Mapping[str, float | None],
    mean_raw_risk: Mapping[str, float | None],
    mean_utility: Mapping[str, float | None],
) -> dict[str, dict[str, Any]]:
    pairs = (
        (PHASE1_BASELINE, PHASE2_RISK_AWARE),
        (PHASE2_RISK_AWARE, PHASE3_TEMPORAL),
        (PHASE3_TEMPORAL, PHASE4_STABILITY),
    )
    differences: dict[str, dict[str, Any]] = {}
    for left, right in pairs:
        key = f"{left}_vs_{right}"
        pair_metrics: dict[str, Any] = {}
        for metric_name, values in (
            ("mean_effective_security_risk", mean_effective_risk),
            ("mean_raw_security_risk", mean_raw_risk),
            ("mean_qos_utility", mean_utility),
        ):
            left_value = values[left]
            right_value = values[right]
            pair_metrics[metric_name] = (
                round(abs(left_value - right_value), 4)
                if left_value is not None and right_value is not None
                else None
            )
        left_rate = violation_rates[left]
        right_rate = violation_rates[right]
        pair_metrics["risk_constraint_violation_rate"] = (
            round(abs(left_rate.rate - right_rate.rate), 4)
            if left_rate is not None and right_rate is not None
            else None
        )
        pair_metrics["policy_distribution_percentage_points"] = {
            policy: round(
                abs(
                    distributions[left].percentages.get(policy, 0.0)
                    - distributions[right].percentages.get(policy, 0.0)
                ),
                4,
            )
            for policy in _DISTRIBUTION_POLICIES
        }
        differences[key] = pair_metrics
    return differences


def _group_by_variant(
    runs: Iterable[AblationRun],
) -> dict[str, list[AblationRun]]:
    grouped = {variant: [] for variant in VARIANTS}
    for run in runs:
        if run.variant not in grouped:
            raise ValueError(f"Unknown ablation variant in run: {run.variant!r}.")
        grouped[run.variant].append(run)
    return grouped


def _mean(values: Iterable[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 4)


def _switch_metrics(policies: list[str]) -> PolicySwitchMetrics:
    switches = sum(
        previous != current
        for previous, current in zip(policies, policies[1:])
    )
    decisions = len(policies)
    return PolicySwitchMetrics(
        decisions=decisions,
        switches=switches,
        psr=calculate_policy_switch_rate(decisions, switches),
        psi=calculate_policy_stability_index(decisions, switches),
    )


def _sequence_id(scenario_id: str) -> str | None:
    for marker, sequence_id in _SEQUENCE_MARKERS:
        if marker in scenario_id:
            return sequence_id
    return None


def _validate_scenarios(scenarios: list[Scenario]) -> None:
    if not isinstance(scenarios, list):
        raise TypeError("scenarios must be a list of Scenario objects.")
    scenario_ids: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, Scenario):
            raise TypeError("Each scenario must be a Scenario.")
        if scenario.scenario_id in scenario_ids:
            raise ValueError(f"Duplicate scenario_id: {scenario.scenario_id}.")
        scenario_ids.add(scenario.scenario_id)
        scenario.network_input.validate()


def _ablation_result_to_dict(result: AblationResult) -> dict[str, Any]:
    result_dict = asdict(result)
    result_dict.pop("native_result", None)
    result_dict["scenario"] = asdict(result.scenario)
    result_dict["stability_objective"] = (
        asdict(result.stability_objective)
        if result.stability_objective is not None
        else None
    )
    return result_dict
