"""
Demo-flow validation test.

Covers the full operational cycle for the video demo:
  normal metrics → inject chaos → alert fires → incident lifecycle →
  recover → incident close → back to normal

Uses only the public API surface — no internal service calls.
"""
import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from redis_client import client as redis
from services.alerting import (
    _clean_streaks,
    _cooldowns,
    _heartbeats,
    _open_incidents,
    evaluate as evaluate_node,
)


def _reset():
    _cooldowns.clear()
    _clean_streaks.clear()
    _open_incidents.clear()
    _heartbeats.clear()


def _metrics_json(node_id="node-2", cpu=35.0, latency=10.0):
    return json.dumps(
        {
            "node_id": node_id,
            "cpu": cpu,
            "memory": 55.0,
            "disk": 30.0,
            "latency_ms": latency,
            "packet_loss_pct": 0.0,
            "status": "green",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_everything():
    _reset()
    # Also clear chaos state
    import services.chaos as chaos_svc
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()
    chaos_svc._config_cache.clear()
    yield
    _reset()
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()
    chaos_svc._config_cache.clear()


@pytest.mark.asyncio
async def test_demo_flow_full_cycle(client):
    # ═══ Phase 1: Normal operation ═══════════════════════════════════
    _heartbeats["node-2"] = datetime.now(timezone.utc)

    resp = await client.get("/api/metrics/node-2?limit=1")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp = await client.get("/api/chaos/status")
    assert resp.status_code == 200
    status_data = resp.json()
    assert status_data["success"] is True
    assert status_data["data"]["active"] == {}

    # ═══ Phase 2: Inject chaos ════════════════════════════════════════
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "cpu_spike", "config": {"value": 50}},
    )
    assert resp.status_code == 200
    inject_data = resp.json()
    assert inject_data["success"] is True
    event_id = inject_data["data"]["event_id"]
    assert event_id is not None

    # Verify chaos appears in status
    resp = await client.get("/api/chaos/status")
    status_data = resp.json()
    assert "cpu_spike" in status_data["data"]["active"].get("node-2", [])

    # ═══ Phase 3: Trigger alert with high CPU ═════════════════════════
    await redis.set("metrics:latest:node-2", _metrics_json(cpu=92.0))
    fired = await evaluate_node("node-2")
    assert len(fired) == 1
    assert fired[0]["alert_type"] == "cpu_high"

    # Verify alert visible via API
    resp = await client.get("/api/alerts?node_id=node-2&limit=5")
    alert_data = resp.json()
    assert alert_data["success"] is True
    assert len(alert_data["data"]) >= 1
    assert alert_data["data"][0]["alert_type"] == "cpu_high"

    # ═══ Phase 4: Verify incident opened ══════════════════════════════
    resp = await client.get("/api/incidents?status=open&limit=5")
    incident_data = resp.json()
    assert incident_data["success"] is True
    assert len(incident_data["data"]) >= 1
    incident_id = incident_data["data"][0]["id"]
    assert incident_data["data"][0]["status"] == "open"

    # ═══ Phase 5: Recover ═════════════════════════════════════════════
    resp = await client.post("/api/chaos/recover", json={"node_id": "node-2"})
    recover_data = resp.json()
    assert recover_data["success"] is True
    assert recover_data["data"]["removed"] >= 1

    resp = await client.get("/api/chaos/status")
    status_data = resp.json()
    assert status_data["data"]["active"].get("node-2", []) == []

    # ═══ Phase 6: Close incident (3 clean evaluations) ════════════════
    for _ in range(3):
        await redis.set("metrics:latest:node-2", _metrics_json())
        await evaluate_node("node-2")

    resp = await client.get(f"/api/incidents/{incident_id}")
    detail = resp.json()
    assert detail["success"] is True
    assert detail["data"]["status"] == "closed"
    assert detail["data"]["closed_at"] is not None

    # ═══ Phase 7: Verify alerts linked to incident ════════════════════
    assert len(detail["data"]["alerts"]) >= 1
    assert detail["data"]["alerts"][0]["alert_type"] == "cpu_high"
