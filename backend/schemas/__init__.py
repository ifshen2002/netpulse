from pydantic import BaseModel, Field


class MetricOut(BaseModel):
    node_id: str
    timestamp: str
    cpu: float
    memory: float
    disk: float
    latency_ms: float
    packet_loss_pct: float
    status: str


class NodeOut(BaseModel):
    id: str
    name: str
    type: str
    status: str
    last_seen: str | None = None
    created_at: str | None = None


class AlertOut(BaseModel):
    id: str
    node_id: str
    incident_id: str | None = None
    alert_type: str
    message: str
    fired_at: str
    resolved_at: str | None = None


class IncidentOut(BaseModel):
    id: str
    title: str
    status: str
    opened_at: str
    closed_at: str | None = None


class ChaosInjectIn(BaseModel):
    node_id: str = Field(min_length=1)
    chaos_type: str = Field(min_length=1)
    config: dict | None = None


class ChaosRecoverIn(BaseModel):
    node_id: str | None = None


class ChaosEventOut(BaseModel):
    id: str
    chaos_type: str
    node_id: str
    started_at: str
    ended_at: str | None = None
    config: dict | None = None
