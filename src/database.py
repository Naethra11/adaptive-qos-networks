import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "decisions.sqlite3"
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    traffic_type: Mapped[str] = mapped_column(String(100), index=True)
    threat_level: Mapped[float] = mapped_column(Float)
    congestion: Mapped[float] = mapped_column(Float)
    bandwidth_available: Mapped[float] = mapped_column(Float)
    application_priority: Mapped[float] = mapped_column(Float)
    device_trust: Mapped[float] = mapped_column(Float)
    latency: Mapped[float] = mapped_column(Float)
    decision_score: Mapped[float] = mapped_column(Float, index=True)
    priority: Mapped[str] = mapped_column(String(40), index=True)
    qos_policy: Mapped[str] = mapped_column(String(80), index=True)
    bandwidth_allocation: Mapped[float] = mapped_column(Float)
    queue: Mapped[str] = mapped_column(String(80))
    security_action: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(String)
    factor_contributions: Mapped[Dict[str, float]] = mapped_column(JSON, default=dict)
    normalized_factors: Mapped[Dict[str, float]] = mapped_column(JSON, default=dict)
    dynamic_weights: Mapped[Dict[str, float]] = mapped_column(JSON, default=dict)
    integrated_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    legacy_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)

    scenario: Mapped[Optional["ScenarioRecord"]] = relationship(back_populates="decisions")


class ScenarioRecord(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    traffic_type: Mapped[str] = mapped_column(String(100))
    threat_level: Mapped[float] = mapped_column(Float)
    congestion: Mapped[float] = mapped_column(Float)
    bandwidth_available: Mapped[float] = mapped_column(Float)
    application_priority: Mapped[float] = mapped_column(Float)
    device_trust: Mapped[float] = mapped_column(Float)
    latency: Mapped[float] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    decisions: Mapped[list["DecisionRecord"]] = relationship(back_populates="scenario")


class SimulationRecord(Base):
    __tablename__ = "simulation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    scenario_ids: Mapped[list[int]] = mapped_column(JSON)
    results: Mapped[list[Dict[str, Any]]] = mapped_column(JSON)
    comparison: Mapped[list[Dict[str, Any]]] = mapped_column(JSON)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def serialize_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + ("Z" if value.tzinfo is None else "")


def scenario_to_dict(scenario: ScenarioRecord) -> Dict[str, Any]:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "traffic_type": scenario.traffic_type,
        "threat_level": scenario.threat_level,
        "congestion": scenario.congestion,
        "bandwidth_available": scenario.bandwidth_available,
        "application_priority": scenario.application_priority,
        "device_trust": scenario.device_trust,
        "latency": scenario.latency,
        "is_default": scenario.is_default,
        "created_at": serialize_datetime(scenario.created_at),
    }


def decision_to_dict(record: DecisionRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "created_at": serialize_datetime(record.created_at),
        "input": {
            "traffic_type": record.traffic_type,
            "threat_level": record.threat_level,
            "congestion": record.congestion,
            "bandwidth_available": record.bandwidth_available,
            "application_priority": record.application_priority,
            "device_trust": record.device_trust,
            "latency": record.latency,
        },
        "result": {
            "decision_score": record.decision_score,
            "priority": record.priority,
            "qos_policy": record.qos_policy,
            "bandwidth_allocation": record.bandwidth_allocation,
            "queue": record.queue,
            "security_action": record.security_action,
            "reason": record.reason,
            "factor_contributions": record.factor_contributions,
            "normalized_factors": record.normalized_factors,
            "dynamic_weights": record.dynamic_weights,
        },
        "integrated_result": record.integrated_result,
        "scenario_id": record.scenario_id,
    }


def simulation_to_dict(record: SimulationRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "created_at": serialize_datetime(record.created_at),
        "scenario_ids": record.scenario_ids,
        "results": record.results,
        "comparison": record.comparison,
    }


DEFAULT_SCENARIOS = [
    {
        "name": "Normal Video Call",
        "description": "A trusted video call with ordinary network conditions.",
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 3,
        "bandwidth_available": 20,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 50,
    },
    {
        "name": "High Threat Traffic",
        "description": "Suspicious traffic under a high threat classification.",
        "traffic_type": "Suspicious Traffic",
        "threat_level": 9,
        "congestion": 4,
        "bandwidth_available": 30,
        "application_priority": 9,
        "device_trust": 20,
        "latency": 60,
    },
    {
        "name": "Severe Network Congestion",
        "description": "High congestion and latency while a high-priority call is active.",
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 9,
        "bandwidth_available": 15,
        "application_priority": 9,
        "device_trust": 90,
        "latency": 180,
    },
    {
        "name": "Low Bandwidth",
        "description": "A lower-priority file download with limited available capacity.",
        "traffic_type": "File Download",
        "threat_level": 1,
        "congestion": 5,
        "bandwidth_available": 5,
        "application_priority": 4,
        "device_trust": 80,
        "latency": 100,
    },
    {
        "name": "Low-Latency Gaming",
        "description": "A trusted gaming flow that benefits from responsive network conditions.",
        "traffic_type": "Gaming",
        "threat_level": 1,
        "congestion": 4,
        "bandwidth_available": 25,
        "application_priority": 9,
        "device_trust": 95,
        "latency": 30,
    },
]


def _migrate_legacy_decisions() -> None:
    if not inspect(engine).has_table("decisions"):
        return

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("decisions")}
        if not {"id", "created_at", "input_json", "result_json"}.issubset(columns):
            return
        rows = connection.execute(
            text("SELECT id, created_at, input_json, result_json FROM decisions ORDER BY id")
        ).mappings().all()

    with SessionLocal() as session:
        for row in rows:
            if session.scalar(select(DecisionRecord).where(DecisionRecord.legacy_id == row["id"])):
                continue
            input_data = json.loads(row["input_json"])
            result = json.loads(row["result_json"])
            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except (TypeError, ValueError):
                created_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(
                DecisionRecord(
                    created_at=created_at,
                    traffic_type=input_data["traffic_type"],
                    threat_level=input_data["threat_level"],
                    congestion=input_data["congestion"],
                    bandwidth_available=input_data["bandwidth_available"],
                    application_priority=input_data["application_priority"],
                    device_trust=input_data["device_trust"],
                    latency=input_data["latency"],
                    decision_score=result["decision_score"],
                    priority=result["priority"],
                    qos_policy=result["qos_policy"],
                    bandwidth_allocation=result["bandwidth_allocation"],
                    queue=result["queue"],
                    security_action=result["security_action"],
                    reason=result["reason"],
                    factor_contributions=result.get("factor_contributions", {}),
                    normalized_factors=result.get("normalized_factors", {}),
                    dynamic_weights=result.get("dynamic_weights", {}),
                    legacy_id=row["id"],
                )
            )
        session.commit()


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_integrated_result_column()
    _migrate_legacy_decisions()
    with SessionLocal() as session:
        if session.scalar(select(ScenarioRecord.id).limit(1)) is None:
            session.add_all(
                ScenarioRecord(**scenario, is_default=True)
                for scenario in DEFAULT_SCENARIOS
            )
            session.commit()


def _ensure_integrated_result_column() -> None:
    """Add nullable integration metadata to existing SQLite decision tables."""
    if not inspect(engine).has_table("decision_records"):
        return
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("decision_records")
    }
    if "integrated_result" in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE decision_records ADD COLUMN integrated_result JSON")
        )
