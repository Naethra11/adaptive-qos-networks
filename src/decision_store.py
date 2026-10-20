from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.database import DecisionRecord


def save_decision(
    session: Session,
    input_data: Dict[str, Any],
    result_data: Dict[str, Any],
    scenario_id: Optional[int] = None,
    integrated_result: Optional[Dict[str, Any]] = None,
) -> DecisionRecord:
    record = DecisionRecord(
        traffic_type=input_data["traffic_type"],
        threat_level=input_data["threat_level"],
        congestion=input_data["congestion"],
        bandwidth_available=input_data["bandwidth_available"],
        application_priority=input_data["application_priority"],
        device_trust=input_data["device_trust"],
        latency=input_data["latency"],
        decision_score=result_data["decision_score"],
        priority=result_data["priority"],
        qos_policy=result_data["qos_policy"],
        bandwidth_allocation=result_data["bandwidth_allocation"],
        queue=result_data["queue"],
        security_action=result_data["security_action"],
        reason=result_data["reason"],
        factor_contributions=result_data.get("factor_contributions", {}),
        normalized_factors=result_data.get("normalized_factors", {}),
        dynamic_weights=result_data.get("dynamic_weights", {}),
        integrated_result=integrated_result,
        scenario_id=scenario_id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_decisions(
    session: Session,
    query: str = "",
    qos_policy: str = "",
    security_action: str = "",
    sort_by: str = "created_at",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[DecisionRecord], int]:
    statement = select(DecisionRecord)
    count_statement = select(func.count()).select_from(DecisionRecord)

    if query:
        search = f"%{query.strip()}%"
        search_filter = or_(
            DecisionRecord.traffic_type.ilike(search),
            DecisionRecord.reason.ilike(search),
            DecisionRecord.qos_policy.ilike(search),
            DecisionRecord.priority.ilike(search),
        )
        statement = statement.where(search_filter)
        count_statement = count_statement.where(search_filter)
    if qos_policy:
        statement = statement.where(DecisionRecord.qos_policy == qos_policy)
        count_statement = count_statement.where(DecisionRecord.qos_policy == qos_policy)
    if security_action:
        statement = statement.where(DecisionRecord.security_action == security_action)
        count_statement = count_statement.where(DecisionRecord.security_action == security_action)

    sort_columns = {
        "created_at": DecisionRecord.created_at,
        "decision_score": DecisionRecord.decision_score,
        "threat_level": DecisionRecord.threat_level,
        "latency": DecisionRecord.latency,
        "traffic_type": DecisionRecord.traffic_type,
    }
    sort_column = sort_columns.get(sort_by, DecisionRecord.created_at)
    sort_expression = sort_column.asc() if order.lower() == "asc" else sort_column.desc()
    total = session.scalar(count_statement) or 0
    records = session.scalars(
        statement.order_by(sort_expression, DecisionRecord.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return records, total


def get_decision(session: Session, decision_id: int) -> Optional[DecisionRecord]:
    return session.get(DecisionRecord, decision_id)


def delete_decision(session: Session, record: DecisionRecord) -> None:
    session.delete(record)
    session.commit()
