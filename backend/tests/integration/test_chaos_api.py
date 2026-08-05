import pytest

from main import app  # noqa: F401  (kept for consistency with other test files)
import services.chaos as chaos_svc


def _clean_state():
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()


@pytest.fixture(autouse=True)
def reset_state():
    _clean_state()
    yield
    _clean_state()


@pytest.mark.asyncio
async def test_inject_latency_spike_returns_event_id(client, editor_headers_no_project):
    """V1 synthetic-node chaos; query without X-Project-ID."""
    h = editor_headers_no_project
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "latency_spike"},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "event_id" in data["data"]
    assert "latency_spike" in chaos_svc._active.get("node-2", {})


@pytest.mark.asyncio
async def test_recover_clears_registry(client, editor_headers_no_project):
    h = editor_headers_no_project
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "cpu_spike"},
        headers=h,
    )
    assert "node-2" in chaos_svc._active

    resp = await client.post(
        "/api/chaos/recover",
        json={"node_id": "node-2"},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["removed"] >= 1
    assert "node-2" not in chaos_svc._active


@pytest.mark.asyncio
async def test_recover_all_no_body_clears_everything(client, editor_headers_no_project):
    h = editor_headers_no_project
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "latency_spike"},
        headers=h,
    )
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-3", "chaos_type": "cpu_spike"},
        headers=h,
    )
    assert len(chaos_svc._active) == 2

    resp = await client.post("/api/chaos/recover", json={}, headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["removed"] == 2
    assert len(chaos_svc._active) == 0


@pytest.mark.asyncio
async def test_chaos_status_returns_active(client, editor_headers_no_project):
    h = editor_headers_no_project
    await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "packet_loss"},
        headers=h,
    )

    resp = await client.get("/api/chaos/status", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "node-2" in data["data"]["active"]
    assert "packet_loss" in data["data"]["active"]["node-2"]


@pytest.mark.asyncio
async def test_inject_unknown_type_returns_error(client, editor_headers_no_project):
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "nuclear_meltdown"},
        headers=editor_headers_no_project,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_inject_alert_only_type(client, editor_headers_no_project):
    resp = await client.post(
        "/api/chaos/inject",
        json={"node_id": "node-2", "chaos_type": "db_exhaustion"},
        headers=editor_headers_no_project,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "event_id" in data["data"]
    # Alert-only types don't go in _active (they're one-shot)
    # The alert is verified separately
