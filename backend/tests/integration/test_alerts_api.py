import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
import redis_client
from services.alerting import (
    _clean_streaks,
    _cooldowns,
    _heartbeats,
    _open_incidents,
    evaluate as evaluate_node,
)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _reset():
    _cooldowns.clear()
    _clean_streaks.clear()
    _open_incidents.clear()
    _heartbeats.clear()


def _metrics_json(cpu=35.0, latency=10.0):
    return json.dumps(
        {
            "node_id": "node-2",
            "cpu": cpu,
            "memory": 55.0,
            "disk": 30.0,
            "latency_ms": latency,
            "packet_loss_pct": 0.0,
            "status": "green",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@pytest.mark.asyncio
async def test_alerts_api_returns_list(client, editor_headers_no_project):
    """V1 synthetic-node alerts have NULL project_id; query without X-Project-ID."""
    _reset()
    _heartbeats["node-2"] = datetime.now(timezone.utc)
    await redis_client.client.set("metrics:latest:node-2", _metrics_json(cpu=88.0))
    await evaluate_node("node-2")

    response = await client.get("/api/alerts?limit=5", headers=editor_headers_no_project)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    assert data["data"][0]["alert_type"] == "cpu_high"


@pytest.mark.asyncio
async def test_alerts_api_filter_by_node(client, editor_headers_no_project):
    _reset()
    _heartbeats["node-2"] = datetime.now(timezone.utc)
    await redis_client.client.set("metrics:latest:node-2", _metrics_json(cpu=82.0))
    await evaluate_node("node-2")

    response = await client.get("/api/alerts?node_id=node-2", headers=editor_headers_no_project)
    assert response.status_code == 200
    data = response.json()
    for alert in data["data"]:
        assert alert["node_id"] == "node-2"


@pytest.mark.asyncio
async def test_incidents_api_returns_list(client, editor_headers_no_project):
    response = await client.get("/api/incidents?limit=5", headers=editor_headers_no_project)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_incident_lifecycle_via_api(client, editor_headers_no_project):
    h = editor_headers_no_project
    _reset()
    _heartbeats["node-2"] = datetime.now(timezone.utc)

    # Trigger alert — creates incident
    await redis_client.client.set("metrics:latest:node-2", _metrics_json(cpu=95.0))
    await evaluate_node("node-2")

    resp = await client.get("/api/incidents?status=open&limit=5", headers=h)
    data = resp.json()
    open_incidents = data["data"]
    assert len(open_incidents) >= 1
    incident_id = open_incidents[0]["id"]
    assert open_incidents[0]["status"] == "open"

    # Simulate 3 clean evaluations to close incident
    for _ in range(3):
        await redis_client.client.set("metrics:latest:node-2", _metrics_json())
        await evaluate_node("node-2")

    resp = await client.get(f"/api/incidents/{incident_id}", headers=h)
    detail = resp.json()
    assert detail["success"] is True
    assert detail["data"]["status"] == "closed"
    assert detail["data"]["closed_at"] is not None
    assert len(detail["data"]["alerts"]) >= 1
