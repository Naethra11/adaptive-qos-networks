from src.decision_engine import load_config
from src.models import NetworkInput
from src.risk_model import calculate_security_risk
from src.evaluation_scenarios import Scenario, get_evaluation_scenarios


def test_scenario_matrix_is_non_empty_with_unique_ids():
    scenarios = get_evaluation_scenarios()

    assert scenarios
    assert all(isinstance(scenario, Scenario) for scenario in scenarios)
    ids = [scenario.scenario_id for scenario in scenarios]
    assert len(ids) == len(set(ids))


def test_scenario_order_is_deterministic():
    first = get_evaluation_scenarios()
    second = get_evaluation_scenarios()

    assert [scenario.scenario_id for scenario in first] == [
        scenario.scenario_id for scenario in second
    ]


def test_all_scenarios_contain_valid_network_inputs():
    for scenario in get_evaluation_scenarios():
        assert isinstance(scenario.network_input, NetworkInput)
        scenario.network_input.validate()
        assert scenario.description


def test_required_condition_categories_are_included():
    ids = {scenario.scenario_id for scenario in get_evaluation_scenarios()}

    assert "S01_SAFE_HIGH_PRIORITY" in ids
    assert "S02_HIGH_THREAT" in ids
    assert "S03_MODERATE_RISK" in ids
    assert "S04_LOW_BANDWIDTH" in ids
    assert "S05_HIGH_CONGESTION" in ids
    assert "S06_HIGH_LATENCY" in ids
    assert "S07_BACKGROUND_LOW_PRIORITY" in ids
    assert "S08_SUSPICIOUS_TRAFFIC" in ids


def test_rising_threat_sequence_is_present_and_ordered():
    scenarios = get_evaluation_scenarios()
    sequence = [
        next(item for item in scenarios if item.scenario_id == scenario_id)
        for scenario_id in ("S09_RISING_T1", "S10_RISING_T2", "S11_RISING_T3")
    ]

    assert [item.network_input.threat_level for item in sequence] == [2, 4, 7]


def test_falling_threat_sequence_is_present_and_ordered():
    scenarios = get_evaluation_scenarios()
    sequence = [
        next(item for item in scenarios if item.scenario_id == scenario_id)
        for scenario_id in ("S12_FALLING_T1", "S13_FALLING_T2", "S14_FALLING_T3")
    ]

    assert [item.network_input.threat_level for item in sequence] == [8, 5, 2]


def test_hysteresis_boundary_regions_cover_configured_boundaries():
    ids = {scenario.scenario_id for scenario in get_evaluation_scenarios()}
    config = load_config()["stability"]["hysteresis"]

    assert {
        "S15_HYST_NORMAL_EXIT_REGION",
        "S16_HYST_NORMAL_ENTER_REGION",
        "S17_HYST_HIGH_EXIT_REGION",
        "S18_HYST_HIGH_ENTER_REGION",
        "S19_HYST_CRITICAL_EXIT_REGION",
        "S20_HYST_CRITICAL_ENTER_REGION",
    } <= ids
    assert config["normal_exit"] == 45
    assert config["normal_enter"] == 50
    assert config["high_exit"] == 65
    assert config["high_enter"] == 70
    assert config["critical_exit"] == 80
    assert config["critical_enter"] == 85


def test_security_risk_scenarios_straddle_existing_r_max():
    scenarios = {
        scenario.scenario_id: scenario.network_input
        for scenario in get_evaluation_scenarios()
    }
    risk_config = load_config()["risk_aware"]
    r_max = risk_config["r_max"]

    below = scenarios["S21_RISK_NEAR_RMAX"]
    above = scenarios["S22_RISK_ABOVE_RMAX"]
    below_risk = calculate_security_risk(
        below.threat_level,
        below.device_trust,
        risk_config["risk_weights"],
    )
    above_risk = calculate_security_risk(
        above.threat_level,
        above.device_trust,
        risk_config["risk_weights"],
    )

    assert r_max == 65
    assert below_risk == 62
    assert below_risk < r_max
    assert above_risk == 72
    assert above_risk > r_max


def test_repeated_calls_return_equivalent_fixed_scenarios():
    first = get_evaluation_scenarios()
    second = get_evaluation_scenarios()

    assert first == second


def test_matrix_is_fixed_size_and_has_no_runtime_experiment_dependency():
    scenarios = get_evaluation_scenarios()

    assert 15 <= len(scenarios) <= 25
    assert len(scenarios) == 22
    assert all(isinstance(item.network_input, NetworkInput) for item in scenarios)
