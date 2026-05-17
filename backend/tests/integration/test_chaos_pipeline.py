"""
Contract tests: chaos injection MUST trigger alerts and incidents within 30s.

These tests exercise the full runtime pipeline:
  simulator → normalize → overlay → Redis → evaluate → incident

They do NOT mock or stub any internal functions — they call the same
code paths the scheduler calls at runtime.
"""
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from redis_client import client as redis
from services.chaos import (
    _active,
    _effect_values,
    _loss_counter,
    apply_overlay,
    inject,
    recover_all,
)
from services.alerting import (
    _clean_streaks,
    _cooldowns,
    _heartbeats,
    _open_incidents,
    evaluate as evaluate_node,
)
from services.simulator import generate as generate_synthetic
from services.normalization import normalize


def _clean_state():
    _active.clear()
    _loss_counter.clear()
    _effect_values.clear()
    _cooldowns.clear()
    _clean_streaks.clear()
    _open_incidents.clear()
    _heartbeats.clear()


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


# ── helpers ─────────────────────────────────────────────────────────

def _run_pipeline(node_id="node-2"):
    """Simulate one scheduler collection cycle for a synthetic node."""
    raw = generate_synthetic(node_id)
    assert raw is not None, f"Simulator must return metrics for {node_id}"
    m = normalize(raw)
    m = apply_overlay(m)
    return m


async def _write_and_evaluate(m):
    """Write metrics to Redis and run alert evaluation (as scheduler does)."""
    if m is None:
        return []
    await redis.set(f"metrics:latest:{m['node_id']}", json.dumps(m))
    return await evaluate_node(m["node_id"])


# ── contract tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critical_cpu_injection_sets_cpu_above_95():
    """CRITICAL CPU must set CPU to 95-100%."""
    await inject("node-2", "cpu_spike", {"intensity": "critical"})
    m = _run_pipeline("node-2")
    assert m is not None
    assert m["cpu"] >= 95.0, f"CRITICAL CPU must be >= 95%, got {m['cpu']}%"


@pytest.mark.asyncio
async def test_high_cpu_injection_sets_cpu_above_80():
    """HIGH CPU must set CPU ≥ 80% (above alert threshold)."""
    await inject("node-2", "cpu_spike", {"intensity": "high"})
    m = _run_pipeline("node-2")
    assert m is not None
    assert m["cpu"] >= 80.0, f"HIGH CPU must be >= 80%, got {m['cpu']}%"


@pytest.mark.asyncio
async def test_critical_cpu_triggers_alert_and_incident():
    """
    CONTRACT: CRITICAL CPU injection MUST trigger a cpu_high alert and
    open an incident within a single pipeline cycle.
    """
    await inject("node-2", "cpu_spike", {"intensity": "critical"})
    m = _run_pipeline("node-2")
    fired = await _write_and_evaluate(m)

    assert len(fired) > 0, (
        f"No alert fired after CRITICAL CPU injection! "
        f"CPU was {m['cpu']}% (threshold: 80%)"
    )
    alert = fired[0]
    assert alert["alert_type"] == "cpu_high", (
        f"Expected cpu_high alert, got {alert.get('alert_type')}"
    )

    # Verify incident is open
    assert "node-2" in _open_incidents, (
        "No open incident for node-2 after CRITICAL CPU alert"
    )


@pytest.mark.asyncio
async def test_high_cpu_triggers_alert_and_incident():
    """CONTRACT: HIGH CPU injection MUST trigger alert + incident."""
    await inject("node-2", "cpu_spike", {"intensity": "high"})
    m = _run_pipeline("node-2")
    fired = await _write_and_evaluate(m)

    assert len(fired) > 0, (
        f"No alert fired after HIGH CPU injection! "
        f"CPU was {m['cpu']}% (threshold: 80%)"
    )
    assert fired[0]["alert_type"] == "cpu_high"
    assert "node-2" in _open_incidents


@pytest.mark.asyncio
async def test_cpu_injection_via_api_triggers_alert(client):
    """
    CONTRACT: Injecting CRITICAL CPU via the public API must result in
    an alert + incident visible via the alerts API within 30 seconds.
    """
    # Inject CRITICAL CPU chaos
    resp = await client.post(
        "/api/chaos/inject",
        json={
            "node_id": "node-2",
            "chaos_type": "cpu_spike",
            "config": {"intensity": "critical"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # After injection, the router force-evaluates, so alert should be
    # visible immediately via the API.
    resp = await client.get("/api/alerts?node_id=node-2&limit=5")
    data = resp.json()
    assert data["success"] is True
    cpu_alerts = [a for a in data["data"] if a["alert_type"] == "cpu_high"]
    assert len(cpu_alerts) > 0, (
        "No cpu_high alert found via API after CRITICAL CPU injection"
    )

    # Verify the alert is linked to an incident
    alert = cpu_alerts[0]
    assert alert["incident_id"] is not None, "Alert must be linked to an incident"

    # Verify incident exists and is open
    resp = await client.get(f"/api/incidents/{alert['incident_id']}")
    inc_data = resp.json()
    assert inc_data["success"] is True
    assert inc_data["data"]["status"] == "open"


@pytest.mark.asyncio
async def test_medium_cpu_below_threshold_no_alert():
    """MEDIUM CPU (30-50%) should NOT trigger alert since < 80% threshold."""
    await inject("node-2", "cpu_spike", {"intensity": "medium"})
    m = _run_pipeline("node-2")
    fired = await _write_and_evaluate(m)

    assert len(fired) == 0, (
        f"MEDIUM CPU (30-50%) should NOT trigger alert. CPU was {m['cpu']}%"
    )


@pytest.mark.asyncio
async def test_low_cpu_below_threshold_no_alert():
    """LOW CPU (70%) should NOT trigger alert since 70% < 80%."""
    await inject("node-2", "cpu_spike", {"intensity": "low"})
    m = _run_pipeline("node-2")
    fired = await _write_and_evaluate(m)

    assert len(fired) == 0, (
        f"LOW CPU (70%) should NOT trigger alert. CPU was {m['cpu']}%"
    )


@pytest.mark.asyncio
async def test_chaos_injection_clears_cooldown(client):
    """
    CONTRACT: Injecting chaos via the API must clear any existing
    cooldown so the alert fires immediately.
    """
    # First, create a natural alert to set cooldown
    await redis.set(
        "metrics:latest:node-2",
        json.dumps({
            "node_id": "node-2",
            "cpu": 90.0,
            "memory": 55.0,
            "disk": 30.0,
            "latency_ms": 10.0,
            "packet_loss_pct": 0.0,
            "status": "red",
            "timestamp": "2026-01-01T00:00:00Z",
        }),
    )
    await evaluate_node("node-2")
    assert _cooldowns.get(("node-2", "cpu_high")) is not None, "Cooldown should be set"

    # Now inject chaos via the API — the router clears cooldown + force-evaluates
    resp = await client.post(
        "/api/chaos/inject",
        json={
            "node_id": "node-2",
            "chaos_type": "cpu_spike",
            "config": {"intensity": "critical"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # After API inject, verify an alert fired — this proves the cooldown was
    # cleared (otherwise the force-evaluate would have been cooldown-blocked).
    # The new alert sets a fresh cooldown, so we check the API, not _cooldowns.
    resp = await client.get("/api/alerts?node_id=node-2&limit=3")
    data = resp.json()
    assert data["success"] is True
    cpu_alerts = [a for a in data["data"] if a["alert_type"] == "cpu_high"]
    assert len(cpu_alerts) > 0, (
        "Chaos injection must fire alert despite pre-existing cooldown"
    )


@pytest.mark.asyncio
async def test_recover_immediately_closes_incident():
    """CONTRACT: Recovering chaos must immediately close the incident."""
    await inject("node-2", "cpu_spike", {"intensity": "critical"})
    m = _run_pipeline("node-2")
    await _write_and_evaluate(m)
    assert "node-2" in _open_incidents, "Incident must be open before recovery"

    await recover_all("node-2", "cpu_spike")
    assert "node-2" not in _open_incidents, (
        "Incident must be closed immediately after chaos recovery"
    )


@pytest.mark.asyncio
async def test_incident_persists_while_chaos_active():
    """
    CONTRACT: While chaos is active, the incident must NOT auto-close,
    even after multiple clean-looking evaluations.
    """
    await inject("node-2", "cpu_spike", {"intensity": "high"})
    m = _run_pipeline("node-2")
    await _write_and_evaluate(m)
    assert "node-2" in _open_incidents

    incident_id = _open_incidents["node-2"]

    # Run several evaluations with low CPU — incident must stay open
    # because chaos is still active
    for _ in range(5):
        await redis.set(
            "metrics:latest:node-2",
            json.dumps({
                "node_id": "node-2",
                "cpu": 30.0,  # well below any threshold
                "memory": 55.0,
                "disk": 30.0,
                "latency_ms": 10.0,
                "packet_loss_pct": 0.0,
                "status": "green",
                "timestamp": "2026-01-01T00:00:00Z",
            }),
        )
        await evaluate_node("node-2")

    assert _open_incidents.get("node-2") == incident_id, (
        "Incident must NOT auto-close while chaos is still active"
    )


@pytest.mark.asyncio
async def test_latency_spike_triggers_incident():
    """CONTRACT: HIGH latency_spike must trigger alert + incident."""
    await inject("node-2", "latency_spike", {"intensity": "high"})
    m = _run_pipeline("node-2")
    assert m["latency_ms"] >= 500, f"HIGH latency should be >= 500ms, got {m['latency_ms']}"
    fired = await _write_and_evaluate(m)

    assert len(fired) > 0, (
        f"No alert fired after HIGH latency injection! "
        f"Latency was {m['latency_ms']}ms (threshold: 500ms)"
    )
    assert fired[0]["alert_type"] == "latency_spike"
