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
    node_id: str | None = None
    endpoint_id: str | None = None
    incident_id: str | None = None
    alert_type: str
    message: str
    fired_at: str
    resolved_at: str | None = None


class IncidentOut(BaseModel):
    id: str
    title: str
    status: str
    endpoint_id: str | None = None
    opened_at: str
    closed_at: str | None = None


class ChaosInjectIn(BaseModel):
    node_id: str = Field(min_length=1)
    chaos_type: str = Field(min_length=1)
    config: dict | None = None


class ChaosRecoverIn(BaseModel):
    node_id: str | None = None
    chaos_type: str | None = None


class ChaosEventOut(BaseModel):
    id: str
    chaos_type: str
    node_id: str
    started_at: str
    ended_at: str | None = None
    config: dict | None = None


# ── V2 schemas ─────────────────────────────────────────────


class EndpointOut(BaseModel):
    id: str
    name: str
    target_host: str
    enabled: bool
    created_at: str | None = None


class EndpointCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_host: str = Field(min_length=1, max_length=256)


class EndpointUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_host: str | None = Field(default=None, min_length=1, max_length=256)
    enabled: bool | None = None


class EndpointMetricOut(BaseModel):
    endpoint_id: str
    packet_evidence_id: str
    timestamp: str
    latency_ms: float
    packet_loss_pct: float
    availability_pct: float
    status: str


class AlertRuleOut(BaseModel):
    id: str
    name: str
    metric: str
    operator: str
    threshold: float
    severity: str
    enabled: bool
    created_at: str | None = None


class AlertRuleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    threshold: float
    severity: str = Field(default="critical")


class AlertRuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    severity: str | None = None
    enabled: bool | None = None


class PacketEvidenceOut(BaseModel):
    id: str
    endpoint_id: str
    protocol: str
    src_ip: str
    dst_ip: str
    ttl: int
    packet_size_bytes: int
    icmp_seq: int
    rtt_ms: float
    timestamp: str
