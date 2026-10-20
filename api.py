from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.adaptive_simulator import run_adaptive_simulation
from src.database import (
    DATABASE_PATH,
    PROJECT_ROOT,
    DecisionRecord,
    ScenarioRecord,
    SessionLocal,
    SimulationRecord,
    decision_to_dict,
    get_db,
    initialize_database,
    scenario_to_dict,
    simulation_to_dict,
)
from src.decision_engine import load_config, make_decision
from src.decision_store import (
    delete_decision,
    get_decision as find_decision,
    list_decisions as query_decisions,
    save_decision,
)
from src.evaluation import run_evaluation
from src.evaluation_scenarios import get_evaluation_scenarios
from src.ablation_metrics import run_ablation_matrix, summarize_ablation_runs
from src.integrated_controller import run_integrated_controller
from src.models import NetworkInput
from src.network_telemetry import DEFAULT_INTERFACE, collect_network_telemetry


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


app = FastAPI(
    title="Adaptive Smart QoS",
    description="Multi-Factor Adaptive QoS Decision Engine API",
    version="1.0.0",
    lifespan=lifespan,
)


class NetworkInputRequest(BaseModel):
    traffic_type: str
    threat_level: float = Field(ge=0, le=10)
    congestion: float = Field(ge=0, le=10)
    bandwidth_available: float = Field(ge=0)
    application_priority: float = Field(ge=0, le=10)
    device_trust: float = Field(ge=0, le=100)
    latency: float = Field(ge=0)


class ScenarioRequest(NetworkInputRequest):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class SimulationRequest(BaseModel):
    name: str = Field(default="QoS Scenario Simulation", min_length=1, max_length=120)
    scenario_ids: List[int] = Field(default_factory=list)


class IntegratedDecisionRequest(NetworkInputRequest):
    previous_smoothed_threat: Optional[float] = Field(default=None, ge=0, le=100)
    previous_policy: Optional[str] = None


@app.get("/")
def home() -> Dict[str, str]:
    return {
        "message": "Adaptive Smart QoS API is running",
        "status": "online",
    }


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/status")
def system_status() -> Dict[str, Any]:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return {
            "api_connected": True,
            "database_connected": True,
            "database": "SQLite",
            "decision_engine_active": True,
            "temporal_risk_active": True,
            "stability_active": True,
        }
    except Exception:
        return {
            "api_connected": True,
            "database_connected": False,
            "database": "SQLite",
            "decision_engine_active": True,
            "temporal_risk_active": True,
            "stability_active": True,
        }


@app.get("/api/settings")
def system_settings() -> Dict[str, Any]:
    config = load_config()
    return {
        "api_endpoint": "/api",
        "database_location": DATABASE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "application_version": app.version,
        "baseline_status": "Integrated Phase 1–4 research controller available",
        "weights": config["weights"],
        "policy_thresholds": config["policy_thresholds"],
        "security_thresholds": config["security_thresholds"],
        "traffic_type_scores": config["traffic_type_scores"],
        "risk_aware": config["risk_aware"],
        "temporal": config["temporal"],
        "stability": config["stability"],
        "control_mode": "Simulation and decision support only",
    }


@app.post("/api/decision")
def get_decision(
    request: NetworkInputRequest,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        network_input = NetworkInput(**request.model_dump())
        result = make_decision(network_input)
        response = {
            "decision_score": result.decision_score,
            "priority": result.priority,
            "qos_policy": result.qos_policy,
            "bandwidth_allocation": result.bandwidth_allocation,
            "queue": result.queue,
            "security_action": result.security_action,
            "reason": result.reason,
            "factor_contributions": result.factor_contributions,
            "normalized_factors": result.normalized_factors,
            "dynamic_weights": result.dynamic_weights,
        }
        save_decision(session, request.model_dump(), response)
        return response
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/integrated-decision")
def get_integrated_decision(
    request: IntegratedDecisionRequest,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        request_data = request.model_dump()
        network_data = {
            key: request_data[key]
            for key in NetworkInputRequest.model_fields
        }
        network_input = NetworkInput(**network_data)
        result = run_integrated_controller(
            network_input,
            previous_smoothed_threat=request.previous_smoothed_threat,
            previous_policy=request.previous_policy,
        )
        integrated_result = asdict(result)
        phase1 = integrated_result["phase1_result"]
        response = {
            "input": network_data,
            **phase1,
            **{
                key: value
                for key, value in integrated_result.items()
                if key not in {"network_input", "phase1_result", "risk_aware_result"}
            },
            "phase1_result": phase1,
            "risk_aware_result": integrated_result["risk_aware_result"],
        }
        save_decision(
            session,
            network_data,
            phase1,
            integrated_result=response,
        )
        return response
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/evaluation/scenarios")
def evaluation_scenarios() -> Dict[str, Any]:
    """Expose the fixed software-evaluation matrix without mutating it."""
    return {
        "evaluation_type": "deterministic software-level evaluation",
        "items": [
            {
                "scenario_id": scenario.scenario_id,
                "description": scenario.description,
                "network_input": asdict(scenario.network_input),
            }
            for scenario in get_evaluation_scenarios()
        ],
    }


@app.get("/api/evaluation/ablation")
def ablation_evaluation() -> Dict[str, Any]:
    """Return the existing fixed Phase 1–4 ablation run and summary."""
    runs = run_ablation_matrix()
    return {
        "evaluation_type": "deterministic software-level ablation",
        "runs": [run.to_dict() for run in runs],
        "summary": summarize_ablation_runs(runs).to_dict(),
    }


@app.get("/api/testbed/status")
def testbed_status() -> Dict[str, Any]:
    """Read actual telemetry if present; do not alter tc state or synthesize it."""
    try:
        telemetry = collect_network_telemetry(DEFAULT_INTERFACE)
    except Exception as error:
        return {
            "connected": False,
            "interface": DEFAULT_INTERFACE,
            "message": f"Controlled Mininet testbed not connected: {error}",
            "telemetry": None,
        }
    return {
        "connected": True,
        "interface": DEFAULT_INTERFACE,
        "message": "Read-only controlled testbed telemetry available.",
        "telemetry": telemetry.to_dict(),
    }


@app.get("/api/decisions")
def list_decisions(
    q: str = "",
    qos_policy: str = "",
    security_action: str = "",
    sort_by: str = "created_at",
    order: str = "desc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    records, total = query_decisions(
        session,
        query=q,
        qos_policy=qos_policy,
        security_action=security_action,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [decision_to_dict(record) for record in records],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/decisions/{decision_id}")
def decision_detail(
    decision_id: int,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    record = find_decision(session, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision record not found.")
    return decision_to_dict(record)


@app.delete("/api/decisions/{decision_id}", status_code=204)
def remove_decision(
    decision_id: int,
    session: Session = Depends(get_db),
) -> Response:
    record = find_decision(session, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision record not found.")
    delete_decision(session, record)
    return Response(status_code=204)


@app.get("/api/scenarios")
def list_scenarios(session: Session = Depends(get_db)) -> Dict[str, List[Dict[str, Any]]]:
    scenarios = session.scalars(
        select(ScenarioRecord).order_by(ScenarioRecord.is_default.desc(), ScenarioRecord.name)
    ).all()
    return {"items": [scenario_to_dict(scenario) for scenario in scenarios]}


@app.post("/api/scenarios", status_code=201)
def create_scenario(
    request: ScenarioRequest,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    scenario = ScenarioRecord(**request.model_dump(), is_default=False)
    session.add(scenario)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="A scenario with this name already exists.") from error
    session.refresh(scenario)
    return scenario_to_dict(scenario)


@app.put("/api/scenarios/{scenario_id}")
def update_scenario(
    scenario_id: int,
    request: ScenarioRequest,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    scenario = session.get(ScenarioRecord, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    for key, value in request.model_dump().items():
        setattr(scenario, key, value)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="A scenario with this name already exists.") from error
    session.refresh(scenario)
    return scenario_to_dict(scenario)


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def remove_scenario(
    scenario_id: int,
    session: Session = Depends(get_db),
) -> Response:
    scenario = session.get(ScenarioRecord, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    if scenario.is_default:
        raise HTTPException(status_code=409, detail="Predefined scenarios cannot be deleted.")
    if session.scalar(
        select(func.count()).select_from(DecisionRecord).where(DecisionRecord.scenario_id == scenario_id)
    ):
        raise HTTPException(status_code=409, detail="Scenarios used by decisions cannot be deleted.")
    session.delete(scenario)
    session.commit()
    return Response(status_code=204)


@app.post("/api/simulations", status_code=201)
def create_simulation(
    request: SimulationRequest,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    statement = select(ScenarioRecord).order_by(ScenarioRecord.id)
    if request.scenario_ids:
        statement = statement.where(ScenarioRecord.id.in_(request.scenario_ids))
    selected_scenarios = session.scalars(statement).all()
    if request.scenario_ids and len(selected_scenarios) != len(set(request.scenario_ids)):
        raise HTTPException(status_code=404, detail="One or more requested scenarios do not exist.")
    if not selected_scenarios:
        raise HTTPException(status_code=400, detail="At least one scenario is required to run a simulation.")

    scenarios = [
        {
            "traffic_type": item.traffic_type,
            "threat_level": item.threat_level,
            "congestion": item.congestion,
            "bandwidth_available": item.bandwidth_available,
            "application_priority": item.application_priority,
            "device_trust": item.device_trust,
            "latency": item.latency,
        }
        for item in selected_scenarios
    ]
    simulation_results = run_adaptive_simulation(scenarios)
    comparison = run_evaluation(scenarios)
    for index, (scenario, result) in enumerate(zip(selected_scenarios, simulation_results)):
        result["Scenario Name"] = scenario.name
        save_decision(
            session,
            input_data=scenarios[index],
            result_data={
                "decision_score": result["Decision Score"],
                "priority": result["Priority"],
                "qos_policy": result["QoS Policy"],
                "bandwidth_allocation": result["Bandwidth Allocation"],
                "queue": result["Queue"],
                "security_action": result["Security Action"],
                "reason": result["Reason"],
                "factor_contributions": result["Factor Contributions"],
                "normalized_factors": result["Normalized Factors"],
                "dynamic_weights": result["Dynamic Weights"],
            },
            scenario_id=scenario.id,
        )
        comparison[index]["Scenario Name"] = scenario.name

    record = SimulationRecord(
        name=request.name,
        scenario_ids=[scenario.id for scenario in selected_scenarios],
        results=simulation_results,
        comparison=comparison,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return simulation_to_dict(record)


@app.get("/api/simulations")
def list_simulations(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    records = session.scalars(
        select(SimulationRecord).order_by(SimulationRecord.created_at.desc()).limit(limit)
    ).all()
    return {"items": [simulation_to_dict(record) for record in records]}


@app.get("/api/simulations/{simulation_id}")
def simulation_detail(
    simulation_id: int,
    session: Session = Depends(get_db),
) -> Dict[str, Any]:
    record = session.get(SimulationRecord, simulation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")
    return simulation_to_dict(record)


@app.get("/api/analytics/summary")
def analytics_summary(session: Session = Depends(get_db)) -> Dict[str, Any]:
    records = session.scalars(
        select(DecisionRecord).order_by(DecisionRecord.created_at.desc()).limit(1000)
    ).all()
    count = session.scalar(select(func.count()).select_from(DecisionRecord)) or 0
    averages = session.execute(
        select(
            func.avg(DecisionRecord.decision_score),
            func.avg(DecisionRecord.bandwidth_allocation),
            func.avg(DecisionRecord.latency),
        )
    ).one()
    policy_distribution = session.execute(
        select(DecisionRecord.qos_policy, func.count())
        .group_by(DecisionRecord.qos_policy)
        .order_by(func.count().desc())
    ).all()
    security_distribution = session.execute(
        select(DecisionRecord.security_action, func.count())
        .group_by(DecisionRecord.security_action)
        .order_by(func.count().desc())
    ).all()
    traffic_distribution = session.execute(
        select(DecisionRecord.traffic_type, func.count())
        .group_by(DecisionRecord.traffic_type)
        .order_by(func.count().desc())
    ).all()
    chronological = list(reversed(records))

    def time_point(record: DecisionRecord, key: str, value: Any) -> Dict[str, Any]:
        return {
            "time": record.created_at.isoformat(timespec="seconds"),
            "traffic_type": record.traffic_type,
            key: value,
        }

    return {
        "total_decisions": count,
        "average_score": round(averages[0], 2) if averages[0] is not None else None,
        "security_overrides": session.scalar(
            select(func.count())
            .select_from(DecisionRecord)
            .where(DecisionRecord.security_action.in_(["RESTRICT", "QUARANTINE"]))
        )
        or 0,
        "most_common_policy": policy_distribution[0][0] if policy_distribution else None,
        "average_bandwidth_allocation": round(averages[1], 2) if averages[1] is not None else None,
        "average_latency": round(averages[2], 2) if averages[2] is not None else None,
        "decision_score_over_time": [
            time_point(record, "value", record.decision_score) for record in chronological
        ],
        "threat_level_over_time": [
            time_point(record, "value", record.threat_level) for record in chronological
        ],
        "congestion_over_time": [
            time_point(record, "value", record.congestion) for record in chronological
        ],
        "policy_distribution": [
            {"name": name, "value": value} for name, value in policy_distribution
        ],
        "security_distribution": [
            {"name": name, "value": value} for name, value in security_distribution
        ],
        "traffic_distribution": [
            {"name": name, "value": value} for name, value in traffic_distribution
        ],
    }
