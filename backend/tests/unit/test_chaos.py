import pytest

import services.chaos as chaos_svc


def _clean_state():
    chaos_svc._active.clear()
    chaos_svc._loss_counter.clear()
    chaos_svc._effect_values.clear()


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


def _set_active(node_id, chaos_type, intensity, value):
    chaos_svc._active.setdefault(node_id, {})[chaos_type] = intensity
    chaos_svc._set_effect(node_id, chaos_type, value)


# Node-1 passthrough

def test_apply_overlay_node1_passthrough():
    _set_active("node-1", "cpu_spike", "high", 88.0)
    original = _base_metrics("node-1")
    result = chaos_svc.apply_overlay(original)
    assert result is original


def test_apply_overlay_node1_always_returns_unchanged():
    _set_active("node-1", "latency_spike", "low", 80.0)
    _set_active("node-1", "packet_loss", "critical", 2)
    _set_active("node-1", "cpu_spike", "high", 90.0)
    original = _base_metrics("node-1", status="green")
    result = chaos_svc.apply_overlay(original)
    assert result is original


# latency_spike

def test_apply_overlay_latency_spike_adds_delay():
    _set_active("node-2", "latency_spike", "high", 600.0)
    m = _base_metrics(latency_ms=100.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["latency_ms"] == 700.0  # 100 + 600


def test_apply_overlay_latency_spike_medium_triggers_yellow_status():
    _set_active("node-2", "latency_spike", "medium", 450.0)
    m = _base_metrics(latency_ms=100.0)
    result = chaos_svc.apply_overlay(m)
    # 100 + 450 = 550 > 500 -> yellow
    assert result["status"] == "yellow"


def test_apply_overlay_latency_spike_critical_triggers_red_status():
    _set_active("node-2", "latency_spike", "critical", 1000.0)
    m = _base_metrics(latency_ms=100.0)
    result = chaos_svc.apply_overlay(m)
    # 100 + 1000 = 1100 > 1000 -> red
    assert result["status"] == "red"


# cpu_spike

def test_apply_overlay_cpu_spike_high_target():
    _set_active("node-2", "cpu_spike", "high", 88.0)
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 88.0


def test_apply_overlay_cpu_spike_when_baseline_already_high():
    _set_active("node-2", "cpu_spike", "high", 88.0)
    m = _base_metrics(cpu=95.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 95.0  # already above 88 target -> unchanged


def test_apply_overlay_cpu_spike_critical_target():
    _set_active("node-2", "cpu_spike", "critical", 98.0)
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 98.0


def test_apply_overlay_cpu_spike_medium_target():
    _set_active("node-2", "cpu_spike", "medium", 42.0)
    m = _base_metrics(cpu=50.0)
    result = chaos_svc.apply_overlay(m)
    assert result is not None
    assert result["cpu"] == 50.0  # baseline above medium target -> stays baseline


# packet_loss

def test_apply_overlay_packet_loss_drops_every_4th_high():
    _set_active("node-2", "packet_loss", "high", 4)
    m = _base_metrics()

    for _ in range(3):
        result = chaos_svc.apply_overlay(m)
        assert result is not None
    result = chaos_svc.apply_overlay(m)
    assert result is None
    for _ in range(3):
        result = chaos_svc.apply_overlay(m)
        assert result is not None
    result = chaos_svc.apply_overlay(m)
    assert result is None


def test_apply_overlay_packet_loss_critical_every_2nd():
    _set_active("node-2", "packet_loss", "critical", 2)
    m = _base_metrics()

    assert chaos_svc.apply_overlay(m) is not None
    assert chaos_svc.apply_overlay(m) is None
    assert chaos_svc.apply_overlay(m) is not None
    assert chaos_svc.apply_overlay(m) is None


def test_apply_overlay_packet_loss_counter_per_node():
    _set_active("node-2", "packet_loss", "high", 4)
    _set_active("node-3", "packet_loss", "high", 4)
    m2 = _base_metrics("node-2")
    m3 = _base_metrics("node-3")

    for _ in range(3):
        chaos_svc.apply_overlay(m2)
    assert chaos_svc.apply_overlay(m3) is not None
    assert chaos_svc.apply_overlay(m2) is None


# copy semantics

def test_apply_overlay_does_not_mutate_input():
    _set_active("node-2", "latency_spike", "low", 100.0)
    _set_active("node-2", "cpu_spike", "high", 88.0)
    original = _base_metrics(cpu=40.0, latency_ms=50.0)
    chaos_svc.apply_overlay(original)
    assert original["cpu"] == 40.0
    assert original["latency_ms"] == 50.0
    assert original["status"] == "green"


# no active chaos

def test_apply_overlay_no_active_chaos_returns_unchanged():
    m = _base_metrics()
    result = chaos_svc.apply_overlay(m)
    assert result["cpu"] == m["cpu"]
    assert result["latency_ms"] == m["latency_ms"]
    assert result["status"] == m["status"]


# inject stores effect values

@pytest.mark.asyncio
async def test_inject_stores_effect_value():
    import services.chaos as cs
    cs.engine = cs.engine  # noop, just to avoid import issues

    # We can't easily mock the DB, so test _set_effect directly
    cs._set_effect("node-2", "cpu_spike", 88.5)
    assert cs._get_effect("node-2", "cpu_spike") == 88.5

    cs._clear_effect("node-2", "cpu_spike")
    assert cs._get_effect("node-2", "cpu_spike") is None


# intensity ranges are valid

def test_cpu_ranges_are_within_expected_bounds():
    for intensity, (lo, hi) in chaos_svc._CPU_RANGES.items():
        for _ in range(20):
            val = chaos_svc._random_in_range(intensity, chaos_svc._CPU_RANGES)
            assert lo <= val <= hi, f"{intensity}: {val} not in [{lo}, {hi}]"

    # CRITICAL always >= 95
    for _ in range(20):
        val = chaos_svc._random_in_range("critical", chaos_svc._CPU_RANGES)
        assert val >= 95, f"critical CPU must be >= 95, got {val}"

    # LOW always < 80 (won't trigger alert)
    for _ in range(20):
        val = chaos_svc._random_in_range("low", chaos_svc._CPU_RANGES)
        assert val < 80, f"low CPU must be < 80, got {val}"

    # HIGH always >= 80 (crosses alert threshold)
    for _ in range(20):
        val = chaos_svc._random_in_range("high", chaos_svc._CPU_RANGES)
        assert val >= 80, f"high CPU must be >= 80, got {val}"


def test_latency_ranges():
    for intensity, (lo, hi) in chaos_svc._LATENCY_RANGES.items():
        for _ in range(10):
            val = chaos_svc._random_in_range(intensity, chaos_svc._LATENCY_RANGES)
            assert lo <= val <= hi

    # HIGH always >= 500 (crosses threshold)
    for _ in range(10):
        val = chaos_svc._random_in_range("high", chaos_svc._LATENCY_RANGES)
        assert val >= 500

    # LOW always < 500 (won't trigger)
    for _ in range(10):
        val = chaos_svc._random_in_range("low", chaos_svc._LATENCY_RANGES)
        assert val < 500
