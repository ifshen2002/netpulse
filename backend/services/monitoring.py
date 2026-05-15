from datetime import datetime, timezone

import psutil

NODE_ID = "node-1"


def collect() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    return {
        "node_id": NODE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": round(cpu, 2),
        "memory": round(memory, 2),
        "disk": round(disk, 2),
        "latency_ms": 0.0,
        "packet_loss_pct": 0.0,
        "status": "green",
    }
