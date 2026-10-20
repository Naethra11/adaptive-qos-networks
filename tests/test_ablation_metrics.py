from dataclasses import replace
from pathlib import Path

import pytest

from src.ablation import (
    PHASE1_BASELINE,
    PHASE2_RISK_AWARE,
    PHASE3_TEMPORAL,
    PHASE4_STABILITY,
)
from src.ablation_metrics import (
    AblationRun,
    calculate_hysteresis_effect,
    calculate_mean_qos_utility,
    calculate_mean_risk,
    calculate_policy_distribution,
    calculate_policy_switch_metrics,
    calculate_risk_constraint_rate,
    calculate_security_override_rate,
    calculate_temporal_trend_counts,
    run_ablation_matrix,
    summarize_ablation_runs,
)
from src.decision_engine import CONFIG_PATH
from src.evaluation_scenarios import get_evaluation_scenarios


ALL_VARIANTS = (
    PHASE1_BASELINE,
    PHASE2_RISK_AWARE,
    PHASE3_TEMPORAL,
    PHASE4_STABILITY,
)


@pytest.fixture(scope="module")
def matrix_runs():
    return run_ablation_matrix()


def test_matrix_evaluates_every_scenario_with_all_four_variants(matrix_runs):
    scenario_ids = [item.scenario_id for item in get_evaluation_scenarios()]

    assert len(matrix_runs) == len(scenario_ids) * len(ALL_VARIANTS)
    assert [run.variant for run in matrix_runs[:4]] == list(ALL_VARIANTS)
    assert [run.scenario_id for run in matrix_runs[::4]] == scenario_ids
    assert {
        (run.scenario_id, run.variant) for run in matrix_runs
    } == {
        (scenario_id, variant)
        for scenario_id in scenario_ids
        for variant in ALL_VARIANTS
    }


def test_each_variant_receives_identical_network_input_values(matrix_runs):
    for index in range(0, len(matrix_runs), len(ALL_VARIANTS)):
        variant_runs = matrix_runs[index:index + len(ALL_VARIANTS)]
        inputs = [run.result.scenario for run in variant_runs]

        assert all(network_input == inputs[0] for network_input in inputs)
        assert all(network_input is inputs[0] for network_input in inputs)


def test_temporal_state_propagates_separately_for_phase3_and_phase4(
    monkeypatch,
):
    from src import ablation_metrics

    real_runner = ablation_metrics.run_ablation_scenario
    calls = []

    def capture(network_input, **kwargs):
        calls.append((network_input, kwargs.copy()))
        return real_runner(network_input, **kwargs)

    monkeypatch.setattr(ablation_metrics, "run_ablation_scenario", capture)
    runs = run_ablation_matrix()
    run_by_key = {(run.scenario_id, run.variant): run for run in runs}
    ordered_scenarios = get_evaluation_scenarios()
    scenario_positions = {
        scenario.scenario_id: index
        for index, scenario in enumerate(ordered_scenarios)
    }

    for sequence_ids in (
        ("S09_RISING_T1", "S10_RISING_T2", "S11_RISING_T3"),
        ("S12_FALLING_T1", "S13_FALLING_T2", "S14_FALLING_T3"),
    ):
        for variant in (PHASE3_TEMPORAL, PHASE4_STABILITY):
            observed_previous = []
            for scenario_id in sequence_ids:
                call_index = (
                    scenario_positions[scenario_id] * len(ALL_VARIANTS)
                    + ALL_VARIANTS.index(variant)
                )
                call = calls[call_index][1]
                observed_previous.append(call["previous_smoothed_threat"])
            assert observed_previous[0] is None
            for index in range(1, len(sequence_ids)):
                prior_result = run_by_key[(sequence_ids[index - 1], variant)].result
                assert observed_previous[index] == prior_result.smoothed_threat


def test_hysteresis_previous_policy_propagates_within_hysteresis_sequence(
    monkeypatch,
):
    from src import ablation_metrics

    real_runner = ablation_metrics.run_ablation_scenario
    calls = []

    def capture(network_input, **kwargs):
        calls.append((network_input, kwargs.copy()))
        return real_runner(network_input, **kwargs)

    monkeypatch.setattr(ablation_metrics, "run_ablation_scenario", capture)
    runs = run_ablation_matrix()
    hysteresis_ids = (
        "S15_HYST_NORMAL_EXIT_REGION",
        "S16_HYST_NORMAL_ENTER_REGION",
        "S17_HYST_HIGH_EXIT_REGION",
        "S18_HYST_HIGH_ENTER_REGION",
        "S19_HYST_CRITICAL_EXIT_REGION",
        "S20_HYST_CRITICAL_ENTER_REGION",
    )
    run_by_id = {
        run.scenario_id: run
        for run in runs
        if run.variant == PHASE4_STABILITY and run.sequence_id == "HYSTERESIS"
    }
    scenario_positions = {
        scenario.scenario_id: index
        for index, scenario in enumerate(get_evaluation_scenarios())
    }

    prior_policies = [
        calls[
            scenario_positions[scenario_id] * len(ALL_VARIANTS)
            + ALL_VARIANTS.index(PHASE4_STABILITY)
        ][1]["previous_policy"]
        for scenario_id in hysteresis_ids
    ]

    assert prior_policies[0] is None
    assert prior_policies[1:] == [
        run_by_id[scenario_id].result.policy for scenario_id in hysteresis_ids[:-1]
    ]


def test_policy_distribution_counts_and_percentages(matrix_runs):
    distributions = calculate_policy_distribution(matrix_runs)
    scenarios_count = len(get_evaluation_scenarios())

    for variant in ALL_VARIANTS:
        distribution = distributions[variant]
        assert sum(distribution.counts.values()) == scenarios_count
        assert sum(distribution.percentages.values()) == pytest.approx(100, abs=0.001)
        assert distribution.total == scenarios_count


def test_security_override_and_constraint_rates_are_only_reported_when_available(
    matrix_runs,
):
    overrides = calculate_security_override_rate(matrix_runs)
    violations = calculate_risk_constraint_rate(matrix_runs)

    assert overrides[PHASE1_BASELINE] is not None
    assert all(overrides[variant] is None for variant in ALL_VARIANTS[1:])
    assert violations[PHASE1_BASELINE] is None
    assert all(violations[variant] is not None for variant in ALL_VARIANTS[1:])
    assert violations[PHASE2_RISK_AWARE].denominator == len(
        get_evaluation_scenarios()
    )


def test_mean_risk_ignores_unavailable_values_not_treating_them_as_zero(
    matrix_runs,
):
    means = calculate_mean_risk(matrix_runs)
    assert means[PHASE1_BASELINE] is None
    assert all(means[variant] is not None for variant in ALL_VARIANTS[1:])

    selected_runs = [
        next(run for run in matrix_runs if run.variant == PHASE1_BASELINE),
        next(run for run in matrix_runs if run.variant == PHASE2_RISK_AWARE),
        next(run for run in matrix_runs if run.variant == PHASE2_RISK_AWARE
             and run.scenario_id != matrix_runs[1].scenario_id),
    ]
    available = [
        run.result.effective_security_risk
        for run in selected_runs
        if run.result.effective_security_risk is not None
    ]
    partial_mean = calculate_mean_risk(selected_runs)[PHASE2_RISK_AWARE]
    assert partial_mean == pytest.approx(sum(available) / len(available))


def test_mean_qos_utility_ignores_unavailable_phase1_values(matrix_runs):
    means = calculate_mean_qos_utility(matrix_runs)
    assert means[PHASE1_BASELINE] is None
    assert all(means[variant] is not None for variant in ALL_VARIANTS[1:])


def test_temporal_trend_counts_match_available_results(matrix_runs):
    counts = calculate_temporal_trend_counts(matrix_runs)

    assert counts[PHASE1_BASELINE] is None
    assert counts[PHASE2_RISK_AWARE] is not None
    assert counts[PHASE3_TEMPORAL] is not None
    assert counts[PHASE4_STABILITY] is not None
    for variant in (PHASE3_TEMPORAL, PHASE4_STABILITY):
        assert sum(counts[variant].values()) == len(get_evaluation_scenarios())


def test_policy_switch_metrics_use_existing_psr_and_psi_definitions(matrix_runs):
    metrics = calculate_policy_switch_metrics(matrix_runs)
    for variant in ALL_VARIANTS:
        for sequence_metrics in metrics[variant].values():
            assert sequence_metrics.psr == pytest.approx(
                round(
                    sequence_metrics.switches / sequence_metrics.decisions,
                    4,
                )
            )
            assert sequence_metrics.psi == pytest.approx(
                round(
                    1
                    - sequence_metrics.switches / sequence_metrics.decisions,
                    4,
                )
            )


def test_hysteresis_effect_reports_candidate_and_final_sequence(matrix_runs):
    effect = calculate_hysteresis_effect(matrix_runs)

    assert effect is not None
    assert effect.scenario_ids == (
        "S15_HYST_NORMAL_EXIT_REGION",
        "S16_HYST_NORMAL_ENTER_REGION",
        "S17_HYST_HIGH_EXIT_REGION",
        "S18_HYST_HIGH_ENTER_REGION",
        "S19_HYST_CRITICAL_EXIT_REGION",
        "S20_HYST_CRITICAL_ENTER_REGION",
    )
    assert effect.candidate_switch_count == sum(
        previous != current
        for previous, current in zip(
            effect.candidate_policies, effect.candidate_policies[1:]
        )
    )
    assert effect.final_switch_count == sum(
        previous != current
        for previous, current in zip(effect.final_policies, effect.final_policies[1:])
    )


def test_matrix_has_no_randomness_and_is_reproducible():
    first = run_ablation_matrix()
    second = run_ablation_matrix()

    assert first == second
    assert [run.to_dict() for run in first] == [run.to_dict() for run in second]


def test_phase1_missing_fields_remain_unavailable(matrix_runs):
    phase1 = next(run.result for run in matrix_runs if run.variant == PHASE1_BASELINE)

    assert phase1.raw_security_risk is None
    assert phase1.effective_security_risk is None
    assert phase1.qos_utility is None
    assert phase1.threat_trend is None
    assert phase1.smoothed_threat is None
    assert phase1.temporal_adjustment is None


def test_run_does_not_modify_configuration_file():
    before = Path(CONFIG_PATH).read_bytes()

    run_ablation_matrix()

    assert Path(CONFIG_PATH).read_bytes() == before


def test_empty_input_has_explicit_empty_metrics():
    assert run_ablation_matrix([]) == []
    summary = summarize_ablation_runs([])

    assert summary.scenario_count == 0
    assert summary.variant_count == 0
    assert summary.hysteresis_effect is None
    assert all(
        distribution.total == 0
        and set(distribution.counts.values()) == {0}
        and set(distribution.percentages.values()) == {0.0}
        for distribution in summary.policy_distribution.values()
    )
    assert all(
        value is None
        for value in summary.mean_effective_security_risk.values()
    )
    assert all(value is None for value in summary.security_override_rate.values())
    assert summary.to_dict()["scenario_count"] == 0


def test_summary_serializes_without_native_results(matrix_runs):
    summary_dict = summarize_ablation_runs(matrix_runs).to_dict()
    first_run = matrix_runs[0].to_dict()

    assert summary_dict["scenario_count"] == len(get_evaluation_scenarios())
    assert summary_dict["variant_count"] == len(ALL_VARIANTS)
    assert first_run["variant"] == PHASE1_BASELINE
    assert "native_result" not in first_run["result"]
    assert first_run["result"]["raw_security_risk"] is None
