"""
End-to-end contract tests: frontend click → backend pipeline → frontend display.

These are BLACK-BOX tests against the live running server on localhost:8000.
They simulate exactly what the browser does:
  1. HTTP POST /api/chaos/inject  (user clicks chaos button)
  2. HTTP GET /api/metrics, /api/alerts, /api/incidents  (frontend reads)
  3. WebSocket receives metric_update, alert_fired, incident_opened

EVERY test completes within 15 seconds — the operator's expectation:
click → visible dashboard change in under 15 s.

These tests depend on the live server being up at localhost:8000.
They self-cleanup by calling /api/chaos/recover after each test.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import websockets
from httpx import AsyncClient

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000/ws"


# ── fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Real HTTP client against the running server."""
    async with AsyncClient(base_url=BASE) as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    """Recover all chaos + resolve alerts after each test so tests are isolated."""
    yield
    async with AsyncClient(base_url=BASE) as c:
        try:
            await c.post("/api/chaos/recover", json={})
        except Exception:
            pass


# ── helpers ───────────────────────────────────────────────────────────

async def _ws_connect():
    return await websockets.connect(WS_BASE)


async def _ws_recv_event(ws, event_type, timeout=12.0):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"No '{event_type}' event within {timeout}s")
        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 3.0))
        event = json.loads(raw)
        if event.get("type") == event_type:
            return event


async def _ws_drain(ws, duration=1.0):
    """Drain pre-existing events from the websocket."""
    try:
        while True:
            await asyncio.wait_for(ws.recv(), timeout=duration)
    except asyncio.TimeoutError:
        pass


# ── E2E: chaos inject → metrics API reflects change ────────────────────

@pytest.mark.asyncio
async def test_e2e_critical_cpu_inject_metrics_api(client):
    """
    Click CRITICAL CPU → /api/metrics/node-2 shows CPU ≥ 90 within 15s.
    """
    t0 = time.monotonic()

    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200, f"Inject failed: {resp.text}"
    assert resp.json()["success"] is True

    # Poll metrics API until CPU reflects injection
    for _ in range(20):
        await asyncio.sleep(0.75)
        resp = await client.get("/api/metrics/node-2?limit=1")
        data = resp.json()
        if data["data"] and data["data"][0]["cpu"] >= 90:
            elapsed = time.monotonic() - t0
            assert elapsed < 15, f"Took {elapsed:.1f}s"
            return

    # Last attempt
    resp = await client.get("/api/metrics/node-2?limit=1")
    last_cpu = resp.json()["data"][0]["cpu"] if resp.json()["data"] else "N/A"
    pytest.fail(f"CPU never reached ≥90. Last CPU={last_cpu}")


@pytest.mark.asyncio
async def test_e2e_high_cpu_inject_metrics_api(client):
    """Click HIGH CPU → metrics show CPU ≥ 80 within 15s."""
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "high"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    for _ in range(20):
        await asyncio.sleep(0.75)
        resp = await client.get("/api/metrics/node-2?limit=1")
        if resp.json()["data"] and resp.json()["data"][0]["cpu"] >= 80:
            return
    pytest.fail("CPU never reached ≥80")


# ── E2E: chaos inject → alert fires ────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_critical_cpu_fires_alert_via_api(client):
    """
    Click CRITICAL CPU → cpu_high alert visible in /api/alerts immediately
    (force-evaluation fires alert in the inject handler itself).
    """
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Force-evaluate fires immediately, so alert should be in the API
    # within a few polls
    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get("/api/alerts?node_id=node-2&limit=5")
        alerts = resp.json()["data"]
        cpu_alerts = [
            a for a in alerts
            if a["alert_type"] == "cpu_high"
            and "CPU at" in a.get("message", "")
        ]
        if cpu_alerts:
            assert cpu_alerts[0]["incident_id"] is not None, "Alert must link to an incident"
            return
    pytest.fail("No cpu_high alert with 'CPU at' found")


@pytest.mark.asyncio
async def test_e2e_high_cpu_fires_alert_via_api(client):
    """Click HIGH CPU → cpu_high alert visible via API."""
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "high"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get("/api/alerts?node_id=node-2&limit=5")
        if any(a["alert_type"] == "cpu_high" for a in resp.json()["data"]):
            return
    pytest.fail("No cpu_high alert found")


# ── E2E: incident lifecycle (open → recover → close) ────────────────────

@pytest.mark.asyncio
async def test_e2e_inject_opens_incident_recover_closes_it(client):
    """Full lifecycle: inject → incident open → recover → incident closed."""
    # Inject
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Wait for incident to appear
    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get("/api/incidents?status=open&limit=5")
        incidents = resp.json()["data"]
        if incidents:
            break
    else:
        pytest.fail("No open incident found after inject")

    incident_id = incidents[0]["id"]
    assert incidents[0]["status"] == "open"

    # Recover
    resp = await client.post("/api/chaos/recover", json={"node_id": "node-2"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Incident must now be closed
    resp = await client.get(f"/api/incidents/{incident_id}")
    detail = resp.json()
    assert detail["success"] is True
    assert detail["data"]["status"] == "closed"
    assert detail["data"]["closed_at"] is not None


# ── E2E: chaos status endpoint ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_chaos_status_reflects_active(client):
    """Click inject → /api/chaos/status shows active. Recover → gone."""
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200

    resp = await client.get("/api/chaos/status")
    active = resp.json()["data"]["active"]
    assert "node-2" in active
    assert active["node-2"]["cpu_spike"] == "critical"

    await client.post("/api/chaos/recover", json={"node_id": "node-2"})

    resp = await client.get("/api/chaos/status")
    assert resp.json()["data"]["active"].get("node-2", {}) == {}


# ── E2E: latency spike ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_latency_spike_fires_alert(client):
    """Click HIGH latency_spike → latency_spike alert visible."""
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-3",
        "chaos_type": "latency_spike",
        "config": {"intensity": "high"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get("/api/alerts?node_id=node-3&limit=5")
        if any(a["alert_type"] == "latency_spike" for a in resp.json()["data"]):
            return
    pytest.fail("No latency_spike alert found")


# ── E2E: low intensity → no alert ─────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_low_cpu_no_alert(client):
    """Click LOW CPU (5-15%) → NO alert fires (below 80% threshold)."""
    t0 = datetime.now(timezone.utc).isoformat()

    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "low"},
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    await asyncio.sleep(3)

    resp = await client.get("/api/alerts?node_id=node-2&limit=10")
    recent_alerts = [
        a for a in resp.json()["data"]
        if a["alert_type"] == "cpu_high"
        and a["resolved_at"] is None
        and a["fired_at"] > t0
    ]
    assert len(recent_alerts) == 0, (
        f"LOW CPU must NOT trigger alert. Got: {recent_alerts}"
    )


# ── E2E: node-1 is read-only ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_node1_chaos_does_not_mutate_metrics(client):
    """Injecting chaos on node-1 must NOT change its metrics (read-only)."""
    resp = await client.get("/api/metrics/node-1?limit=1")

    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-1",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200

    # Wait for scheduler cycle
    await asyncio.sleep(6)

    resp = await client.get("/api/metrics/node-1?limit=1")
    after = resp.json()["data"][0]["cpu"] if resp.json()["data"] else 0

    # Node-1 is a real host — metrics should not jump to 100%.
    # The CPU might fluctuate naturally but should stay reasonable.
    assert after < 50, f"node-1 CPU should stay reasonable, got {after}"


# ── E2E: recover all clears everything ─────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_recover_all_clears_all(client):
    """Click RECOVER ALL → all chaos removed, incidents closed."""
    # Inject multiple chaos on multiple nodes
    await client.post("/api/chaos/inject", json={
        "node_id": "node-2", "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    await client.post("/api/chaos/inject", json={
        "node_id": "node-3", "chaos_type": "latency_spike",
        "config": {"intensity": "high"},
    })

    resp = await client.post("/api/chaos/recover", json={})
    assert resp.status_code == 200
    assert resp.json()["data"]["removed"] >= 1

    resp = await client.get("/api/chaos/status")
    active = resp.json()["data"]["active"]
    assert active.get("node-2", {}) == {}
    assert active.get("node-3", {}) == {}


# ── E2E: incident detail includes alerts ───────────────────────────────

@pytest.mark.asyncio
async def test_e2e_incident_detail_includes_alerts(client):
    """GET /api/incidents/{id} returns linked alerts with details."""
    resp = await client.post("/api/chaos/inject", json={
        "node_id": "node-2",
        "chaos_type": "cpu_spike",
        "config": {"intensity": "critical"},
    })
    assert resp.status_code == 200

    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get("/api/incidents?status=open&limit=5")
        if resp.json()["data"]:
            break
    else:
        pytest.fail("No open incident")

    inc_id = resp.json()["data"][0]["id"]
    resp = await client.get(f"/api/incidents/{inc_id}")
    detail = resp.json()
    assert len(detail["data"]["alerts"]) >= 1
    assert detail["data"]["alerts"][0]["alert_type"] == "cpu_high"


# ── E2E: WebSocket receives alert_fired after inject ──────────────────

@pytest.mark.asyncio
async def test_e2e_websocket_receives_alert_after_inject(client):
    """
    Click CRITICAL CPU → WebSocket clients receive alert_fired event
    within 15 seconds.
    """
    ws = await _ws_connect()
    await _ws_drain(ws, duration=1.0)

    try:
        # Inject via API (simulates frontend click)
        await client.post("/api/chaos/inject", json={
            "node_id": "node-2",
            "chaos_type": "cpu_spike",
            "config": {"intensity": "critical"},
        })

        event = await _ws_recv_event(ws, "alert_fired", timeout=12)
        assert event["alert_type"] == "cpu_high"
        assert re.search(r"CPU at \d{2,3}%", event["message"])
        assert event["incident_id"] is not None
    finally:
        await ws.close()


@pytest.mark.asyncio
async def test_e2e_websocket_receives_incident_events_after_inject(client):
    """
    Click CRITICAL CPU → WebSocket receives both incident_opened
    and after recover receives incident_closed.
    """
    ws = await _ws_connect()
    await _ws_drain(ws, duration=1.0)

    try:
        await client.post("/api/chaos/inject", json={
            "node_id": "node-2",
            "chaos_type": "cpu_spike",
            "config": {"intensity": "critical"},
        })

        opened = await _ws_recv_event(ws, "incident_opened", timeout=12)
        assert opened["node_id"] == "node-2"

        # Recover
        await client.post("/api/chaos/recover", json={"node_id": "node-2"})

        closed = await _ws_recv_event(ws, "incident_closed", timeout=12)
        assert closed["node_id"] == "node-2"
    finally:
        await ws.close()


@pytest.mark.asyncio
async def test_e2e_websocket_receives_metric_update_after_inject(client):
    """
    Click CRITICAL CPU → WebSocket receives metric_update with high CPU
    within 15 seconds.  Keeps reading node-2 events until the overlaid
    value arrives (scheduler may broadcast a stale normal metric first).
    """
    ws = await _ws_connect()
    await _ws_drain(ws, duration=1.0)

    try:
        await client.post("/api/chaos/inject", json={
            "node_id": "node-2",
            "chaos_type": "cpu_spike",
            "config": {"intensity": "critical"},
        })

        # Force-evaluate broadcasts immediately, but scheduler push_metrics
        # (1s) may also fire.  Read node-2 metric_update events until we
        # get the one with elevated CPU.
        deadline = time.monotonic() + 12
        found = None
        while time.monotonic() < deadline:
            event = await _ws_recv_event(ws, "metric_update", timeout=3)
            if event.get("node_id") == "node-2" and event.get("cpu", 0) >= 90:
                found = event
                break

        assert found is not None, "Never received node-2 metric_update with CPU >= 90"
        assert found["status"] in ("yellow", "red")
    finally:
        await ws.close()
