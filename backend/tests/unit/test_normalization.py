import math

from services.normalization import normalize


def test_normalize_passthrough():
    m = normalize({"node_id": "n1", "cpu": 45.0, "memory": 60.0, "disk": 30.0, "latency_ms": 10.0, "packet_loss_pct": 1.0})
    assert m["node_id"] == "n1"
    assert m["cpu"] == 45.0
    assert m["status"] == "green"


def test_normalize_clamps_high():
    m = normalize({"cpu": 150.0, "memory": 200.0, "disk": 200.0, "latency_ms": 5000.0, "packet_loss_pct": 200.0})
    assert m["cpu"] == 100.0
    assert m["memory"] == 100.0
    assert m["disk"] == 100.0
    assert m["packet_loss_pct"] == 100.0


def test_normalize_clamps_low():
    m = normalize({"cpu": -10.0, "memory": -5.0, "disk": -1.0, "latency_ms": -50.0, "packet_loss_pct": -5.0})
    assert m["cpu"] == 0.0
    assert m["memory"] == 0.0
    assert m["latency_ms"] == 0.0
    assert m["packet_loss_pct"] == 0.0


def test_normalize_nan_to_zero():
    m = normalize({"cpu": float("nan"), "memory": float("nan"), "disk": 0.0, "latency_ms": 0.0, "packet_loss_pct": 0.0})
    assert m["cpu"] == 0.0
    assert m["memory"] == 0.0


def test_normalize_missing_fields_default():
    m = normalize({})
    assert m["node_id"] == "unknown"
    assert m["cpu"] == 0.0
    assert m["memory"] == 0.0


def test_normalize_status_red():
    m = normalize({"cpu": 95.0, "memory": 50.0, "disk": 30.0, "latency_ms": 10.0, "packet_loss_pct": 0.0})
    assert m["status"] == "red"


def test_normalize_status_yellow():
    m = normalize({"cpu": 85.0, "memory": 50.0, "disk": 30.0, "latency_ms": 10.0, "packet_loss_pct": 0.0})
    assert m["status"] == "yellow"


def test_normalize_status_green():
    m = normalize({"cpu": 50.0, "memory": 60.0, "disk": 30.0, "latency_ms": 10.0, "packet_loss_pct": 0.0})
    assert m["status"] == "green"
