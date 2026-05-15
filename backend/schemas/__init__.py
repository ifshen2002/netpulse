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
