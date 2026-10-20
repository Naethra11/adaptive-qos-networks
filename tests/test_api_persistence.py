import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import src.database as database
from api import (
    IntegratedDecisionRequest,
    NetworkInputRequest,
    ScenarioRequest,
    SimulationRequest,
    analytics_summary,
    create_scenario,
    create_simulation,
    decision_detail,
    get_decision,
    get_integrated_decision,
    evaluation_scenarios,
    ablation_evaluation,
    list_decisions,
    list_scenarios,
    remove_decision,
    remove_scenario,
    system_settings,
    update_scenario,
)
from src.database import DecisionRecord, ScenarioRecord


SAMPLE_INPUT = {
    "traffic_type": "Video Call",
    "threat_level": 2,
    "congestion": 4,
    "bandwidth_available": 24,
    "application_priority": 8,
    "device_trust": 90,
    "latency": 80,
}


@pytest.fixture
def database_session(tmp_path, monkeypatch):
    previous_engine = database.engine
    test_engine = create_engine(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
    monkeypatch.setattr(database, "engine", test_engine)
    database.SessionLocal.configure(bind=test_engine)
    database.initialize_database()
    with Session(test_engine, expire_on_commit=False) as session:
        yield session
    test_engine.dispose()
    database.SessionLocal.configure(bind=previous_engine)


def test_api_persists_decisions_across_database_reinitialization(database_session):
    saved_result = get_decision(NetworkInputRequest(**SAMPLE_INPUT), database_session)
    history = list_decisions(limit=100, offset=0, session=database_session)

    assert history["total"] == 1
    assert history["items"][0]["input"] == SAMPLE_INPUT
    assert history["items"][0]["result"] == saved_result

    database.initialize_database()
    history_after_reinitialization = list_decisions(limit=100, offset=0, session=database_session)
    assert history_after_reinitialization["total"] == 1
    assert history_after_reinitialization["items"][0]["result"] == saved_result
    assert history_after_reinitialization["items"][0]["integrated_result"] is None


def test_integrated_endpoint_returns_and_persists_phase_outputs(database_session):
    result = get_integrated_decision(
        IntegratedDecisionRequest(**SAMPLE_INPUT),
        database_session,
    )

    assert result["input"] == SAMPLE_INPUT
    assert result["phase1_result"]["decision_score"] == result["decision_score"]
    assert result["risk_aware_result"]["selected_policy"] == result["candidate_policy"]
    assert result["final_policy"]
    assert result["raw_security_risk"] is not None
    assert result["effective_security_risk"] is not None
    assert result["risk_budget_satisfied"] is not None

    record = list_decisions(limit=10, offset=0, session=database_session)["items"][0]
    assert record["integrated_result"]["final_policy"] == result["final_policy"]
    assert record["integrated_result"]["raw_security_risk"] == result["raw_security_risk"]


def test_history_details_and_explicit_delete(database_session):
    get_decision(NetworkInputRequest(**SAMPLE_INPUT), database_session)
    record = database_session.scalar(select(DecisionRecord))
    assert record is not None

    assert decision_detail(record.id, database_session)["id"] == record.id
    response = remove_decision(record.id, database_session)
    assert response.status_code == 204
    assert list_decisions(limit=100, offset=0, session=database_session)["total"] == 0


def test_scenario_create_update_and_default_delete_protection(database_session):
    scenarios = list_scenarios(database_session)["items"]
    assert len(scenarios) == 5
    assert all(scenario["is_default"] for scenario in scenarios)

    new_scenario_data = {
        "name": "Custom validation scenario",
        "description": "Created by a persistence test.",
        **SAMPLE_INPUT,
    }
    created = create_scenario(ScenarioRequest(**new_scenario_data), database_session)
    assert created["is_default"] is False

    new_scenario_data["name"] = "Updated validation scenario"
    updated = update_scenario(
        created["id"],
        ScenarioRequest(**new_scenario_data),
        database_session,
    )
    assert updated["name"] == new_scenario_data["name"]

    default_scenario = database_session.scalar(
        select(ScenarioRecord).where(ScenarioRecord.is_default.is_(True))
    )
    with pytest.raises(Exception) as error:
        remove_scenario(default_scenario.id, database_session)
    assert getattr(error.value, "status_code", None) == 409


def test_simulation_and_analytics_use_saved_database_records(database_session):
    simulation = create_simulation(
        SimulationRequest(name="Five baseline scenarios"),
        database_session,
    )

    assert [result["Time Step"] for result in simulation["results"]] == [
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
    ]
    assert len(simulation["comparison"]) == 5
    assert list_decisions(limit=100, offset=0, session=database_session)["total"] == 5

    analytics = analytics_summary(database_session)
    assert analytics["total_decisions"] == 5
    assert analytics["average_score"] is not None
    assert len(analytics["decision_score_over_time"]) == 5


def test_settings_report_runtime_information():
    settings = system_settings()

    assert settings["api_endpoint"] == "/api"
    assert settings["database_location"] == "data/decisions.sqlite3"
    assert settings["application_version"] == "1.0.0"
    assert settings["baseline_status"] == "Integrated Phase 1–4 research controller available"


def test_fixed_evaluation_endpoints_use_existing_matrix_and_ablation():
    scenarios = evaluation_scenarios()
    results = ablation_evaluation()

    assert len(scenarios["items"]) == 22
    assert scenarios["evaluation_type"] == "deterministic software-level evaluation"
    assert results["evaluation_type"] == "deterministic software-level ablation"
    assert results["summary"]["scenario_count"] == 22
    assert len(results["runs"]) == 88


def test_testbed_status_marks_missing_live_interface(monkeypatch):
    import api as api_module

    def unavailable(interface):
        raise FileNotFoundError("tc executable unavailable")

    monkeypatch.setattr(api_module, "collect_network_telemetry", unavailable)
    result = api_module.testbed_status()

    assert result["connected"] is False
    assert result["telemetry"] is None
    assert "Controlled Mininet testbed not connected" in result["message"]
    assert "tc executable unavailable" in result["message"]
