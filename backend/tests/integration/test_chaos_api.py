import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
import services.chaos as chaos_svc


def _clean_state():
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()
    chaos_svc._config_cache.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    _clean_state()
    yield
    _clean_state()


@pytest.mark.asyncio
async def test_inject_latency_spike_returns_event_id(client):
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "latency_spike"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "event_id" in data["data"]
    assert "latency_spike" in chaos_svc._active.get("node-2", [])


@pytest.mark.asyncio
async def test_recover_clears_registry(client):
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "cpu_spike"},
    )
    assert "node-2" in chaos_svc._active

    resp = await client.post(
        "/api/chaos/recover",
        json={"node_id": "node-2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["removed"] >= 1
    assert "node-2" not in chaos_svc._active


@pytest.mark.asyncio
async def test_recover_all_no_body_clears_everything(client):
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "latency_spike"},
    )
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-3", "chaos_type": "cpu_spike"},
    )
    assert len(chaos_svc._active) == 2

    resp = await client.post("/api/chaos/recover", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["removed"] == 2
    assert len(chaos_svc._active) == 0


@pytest.mark.asyncio
async def test_chaos_status_returns_active(client):
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "packet_loss"},
    )

    resp = await client.get("/api/chaos/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "node-2" in data["data"]["active"]
    assert "packet_loss" in data["data"]["active"]["node-2"]


@pytest.mark.asyncio
async def test_inject_unknown_type_returns_error(client):
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "nuclear_meltdown"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_inject_alert_only_type(client):
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "db_exhaustion"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "event_id" in data["data"]
    # Alert-only types don't go in _active (they're one-shot)
    # The alert is verified separately
