import random
from datetime import datetime, timezone

SYNTHETIC_NODES = {
    "node-2": {"name": "Cloud Service A"},
    "node-3": {"name": "Cloud Service B"},
}

_on: dict[str, bool] = {"node-2": True, "node-3": True}
_burst: dict[str, bool] = {"node-2": False, "node-3": False}

_state: dict[str, dict] = {
    "node-2": {"cpu": 35.0, "memory": 55.0, "disk": 35.0, "latency_ms": 20.0, "packet_loss_pct": 0.5},
    "node-3": {"cpu": 25.0, "memory": 45.0, "disk": 30.0, "latency_ms": 15.0, "packet_loss_pct": 0.3},
}


def _walk(current: float, lo: float, hi: float, step: float) -> float:
    delta = random.uniform(-step, step)
    return max(lo, min(hi, current + delta))


def generate(node_id: str) -> dict | None:
    if node_id not in SYNTHETIC_NODES:
        return None
    if not _on[node_id]:
        return None

    s = _state[node_id]
    s["cpu"] = _walk(s["cpu"], 5.0, 85.0, 4.0)
    s["memory"] = _walk(s["memory"], 20.0, 90.0, 3.0)
    s["disk"] = _walk(s["disk"], 15.0, 70.0, 1.0)
    s["latency_ms"] = _walk(s["latency_ms"], 2.0, 150.0, 8.0)
    s["packet_loss_pct"] = _walk(s["packet_loss_pct"], 0.0, 5.0, 0.4)

    return {
        "node_id": node_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": round(s["cpu"], 2),
        "memory": round(s["memory"], 2),
        "disk": round(s["disk"], 2),
        "latency_ms": round(s["latency_ms"], 2),
        "packet_loss_pct": round(s["packet_loss_pct"], 2),
        "status": "green",
    }


def set_node_on(node_id: str, on: bool) -> None:
    if node_id in SYNTHETIC_NODES:
        _on[node_id] = on


def set_burst(node_id: str, burst: bool) -> None:
    if node_id in SYNTHETIC_NODES:
        _burst[node_id] = burst


def is_on(node_id: str) -> bool:
    return _on.get(node_id, False)


def any_burst(node_id: str | None = None) -> bool:
    if node_id:
        return _burst.get(node_id, False)
    return any(_burst.values())
