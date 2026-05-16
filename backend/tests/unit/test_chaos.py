from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.chaos as chaos_svc


def _clean_state():
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()
    chaos_svc._config_cache.clear()


@pytest.fixture(autouse=True)
def reset_state():
    _clean_state()
    yield
    _clean_state()


def _base_metrics(node_id="node-2", **overrides):
    m = {
        "node_id": node_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "cpu": 35.0,
        "memory": 55.0,
        "disk": 30.0,
        "latency_ms": 10.0,
        "packet_loss_pct": 0.0,
        "status": "green",
    }
    m.update(overrides)
    return m


# ── Node-1 passthrough ──────────────────────────────────────────────

def test_apply_overlay_node1_passthrough():
    chaos_svc._active["node-1"] = ["cpu_spike"]
    original = _base_metrics("node-1")
    result = chaos_svc.apply_overlay(original)
    assert result is original


def test_apply_overlay_node1_always_returns_unchanged():
    chaos_svc._active["node-1"] = ["latency_spike", "packet_loss", "cpu_spike"]
    original = _base_metrics("node-1", status="green")
    result = chaos_svc.apply_overlay(original)
    assert result is original


# ── latency_spike ───────────────────────────────────────────────────

def test_apply_overlay_latency_spike_adds_delay():
    chaos_svc._active["node-2"] = ["latency_spike"]
    m = _base_metrics(latency_ms=100.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["latency_ms"] >= 300.0   # 100 + min 200
    assert result["latency_ms"] <= 900.0   # 100 + max 800


def test_apply_overlay_latency_spike_may_trigger_yellow_status():
    chaos_svc._active["node-2"] = ["latency_spike"]
    m = _base_metrics(latency_ms=400.0)
    result = chaos_svc.apply_overlay(m)
    # 400 + (200..800) → at least 600 > 500 → yellow
    assert result["status"] in ("yellow", "red")


# ── cpu_spike ───────────────────────────────────────────────────────

def test_apply_overlay_cpu_spike_adds_bonus():
    chaos_svc._active["node-2"] = ["cpu_spike"]
    chaos_svc._config_cache["node-2:cpu_spike"] = {"value": 40}
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 90.0  # 50 + 40


def test_apply_overlay_cpu_spike_caps_at_100():
    chaos_svc._active["node-2"] = ["cpu_spike"]
    chaos_svc._config_cache["node-2:cpu_spike"] = {"value": 60}
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 100.0


def test_apply_overlay_cpu_spike_default_value():
    chaos_svc._active["node-2"] = ["cpu_spike"]
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 80.0  # 50 + default 30


# ── packet_loss ─────────────────────────────────────────────────────

def test_apply_overlay_packet_loss_drops_every_5th():
    chaos_svc._active["node-2"] = ["packet_loss"]
    m = _base_metrics()

    # Calls 1-4: pass through
    for _ in range(4):
        result = chaos_svc.apply_overlay(m)
        assert result is not None

    # Call 5: dropped
    result = chaos_svc.apply_overlay(m)
    assert result is None

    # Calls 6-9: pass through again
    for _ in range(4):
        result = chaos_svc.apply_overlay(m)
        assert result is not None

    # Call 10: dropped again
    result = chaos_svc.apply_overlay(m)
    assert result is None


def test_apply_overlay_packet_loss_counter_per_node():
    chaos_svc._active["node-2"] = ["packet_loss"]
    chaos_svc._active["node-3"] = ["packet_loss"]
    m2 = _base_metrics("node-2")
    m3 = _base_metrics("node-3")

    # Advance node-2 to call 4
    for _ in range(4):
        chaos_svc.apply_overlay(m2)
    # node-3 is at call 1 — should pass
    assert chaos_svc.apply_overlay(m3) is not None
    # node-2 call 5 — should drop
    assert chaos_svc.apply_overlay(m2) is None


# ── copy semantics ──────────────────────────────────────────────────

def test_apply_overlay_does_not_mutate_input():
    chaos_svc._active["node-2"] = ["latency_spike", "cpu_spike"]
    chaos_svc._config_cache["node-2:cpu_spike"] = {"value": 20}
    original = _base_metrics(cpu=40.0, latency_ms=50.0)
    chaos_svc.apply_overlay(original)
    assert original["cpu"] == 40.0
    assert original["latency_ms"] == 50.0
    assert original["status"] == "green"


# ── no active chaos ─────────────────────────────────────────────────

def test_apply_overlay_no_active_chaos_returns_unchanged():
    m = _base_metrics()
    result = chaos_svc.apply_overlay(m)
    assert result["cpu"] == m["cpu"]
    assert result["latency_ms"] == m["latency_ms"]
    assert result["status"] == m["status"]
