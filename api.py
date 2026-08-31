from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models import NetworkInput
from src.decision_engine import make_decision


app = FastAPI(
    title="Adaptive Smart QoS",
    description="Multi-Factor Adaptive QoS Decision Engine API",
    version="1.0.0",
)


class NetworkInputRequest(BaseModel):
    traffic_type: str

    threat_level: float = Field(ge=0, le=10)
    congestion: float = Field(ge=0, le=10)
    bandwidth_available: float = Field(ge=0)
    application_priority: float = Field(ge=0, le=10)
    device_trust: float = Field(ge=0, le=100)
    latency: float = Field(ge=0)


@app.get("/")
def home():
    return {
        "message": "Adaptive Smart QoS API is running",
        "status": "online"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.post("/api/decision")
def get_decision(request: NetworkInputRequest):
    try:
        network_input = NetworkInput(
            traffic_type=request.traffic_type,
            threat_level=request.threat_level,
            congestion=request.congestion,
            bandwidth_available=request.bandwidth_available,
            application_priority=request.application_priority,
            device_trust=request.device_trust,
            latency=request.latency,
        )

        result = make_decision(network_input)

        return {
            "decision_score": result.decision_score,
            "priority": result.priority,
            "qos_policy": result.qos_policy,
            "bandwidth_allocation": result.bandwidth_allocation,
            "queue": result.queue,
            "security_action": result.security_action,
            "reason": result.reason,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )