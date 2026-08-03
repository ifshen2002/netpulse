import math


def normalize(raw: dict) -> dict:
    cpu = _clamp(raw.get("cpu", 0), 0, 100)
    memory = _clamp(raw.get("memory", 0), 0, 100)
    disk = _clamp(raw.get("disk", 0), 0, 100)
    latency_ms = _clamp(raw.get("latency_ms", 0), 0, None)
    packet_loss_pct = _clamp(raw.get("packet_loss_pct", 0), 0, 100)

    return {
        "node_id": raw.get("node_id", "unknown"),
        "timestamp": raw.get("timestamp", ""),
        "cpu": _nan_to_zero(cpu),
        "memory": _nan_to_zero(memory),
        "disk": _nan_to_zero(disk),
        "latency_ms": _nan_to_zero(latency_ms),
        "packet_loss_pct": _nan_to_zero(packet_loss_pct),
        "status": _compute_status(cpu, memory, latency_ms),
    }


def _clamp(value: float, lo: float, hi: float | None) -> float:
    if value is None or math.isnan(value) or math.isinf(value):
        return lo
    if value < lo:
        return lo
    if hi is not None and value > hi:
        return hi
    return value


def _nan_to_zero(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value


def _compute_status(cpu: float, memory: float, latency_ms: float) -> str:
    if cpu > 90 or memory > 95 or latency_ms > 1000:
        return "red"
    if cpu > 80 or memory > 90 or latency_ms > 500:
        return "yellow"
    return "green"


# ── V2 endpoint telemetry normalization ──────────────────────


def normalize_endpoint(
    raw: dict,
    packet_loss_pct: float,
    availability_pct: float,
    has_data: bool,
) -> dict:
    latency_ms = _clamp(raw.get("latency_ms", 0), 0, None)
    loss = _clamp(packet_loss_pct, 0, 100)
    avail = _clamp(availability_pct, 0, 100)

    return {
        "endpoint_id": raw["endpoint_id"],
        "packet_evidence_id": raw.get("packet_evidence_id", ""),
        "timestamp": raw.get("timestamp", ""),
        "latency_ms": _nan_to_zero(latency_ms),
        "packet_loss_pct": _nan_to_zero(loss),
        "availability_pct": _nan_to_zero(avail),
        "status": _compute_endpoint_status(latency_ms, loss, avail, has_data),
    }


def _compute_endpoint_status(
    latency_ms: float,
    packet_loss_pct: float,
    availability_pct: float,
    has_data: bool,
) -> str:
    if not has_data:
        return "gray"
    if availability_pct <= 90 or packet_loss_pct >= 10:
        return "red"
    if latency_ms > 300 or packet_loss_pct >= 5 or availability_pct <= 95:
        return "yellow"
    return "green"
