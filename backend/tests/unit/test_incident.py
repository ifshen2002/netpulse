import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.alerting as alerting


def _metric(cpu=35.0):
    return json.dumps(
        {
            "node_id": "node-2",
            "cpu": cpu,
            "memory": 55.0,
            "disk": 30.0,
            "latency_ms": 10.0,
            "packet_loss_pct": 0.0,
            "status": "green",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _mock_engine():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__.return_value = conn
    return engine


@pytest.fixture(autouse=True)
def reset_state():
    alerting._cooldowns.clear()
    alerting._clean_streaks.clear()
    alerting._open_incidents.clear()
    alerting._heartbeats.clear()


@pytest.mark.asyncio
async def test_first_alert_creates_incident():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _metric(cpu=85.0)

    with (
        patch("services.alerting.redis", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.evaluate("node-2")
        assert "node-2" in alerting._open_incidents


@pytest.mark.asyncio
async def test_second_alert_same_incident():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    incident_id = "existing-incident-id"
    alerting._open_incidents["node-2"] = incident_id

    mock_redis = AsyncMock()
    mock_redis.get.return_value = _metric(cpu=90.0)

    with (
        patch("services.alerting.redis", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.evaluate("node-2")
        assert alerting._open_incidents["node-2"] == incident_id


@pytest.mark.asyncio
async def test_three_clean_evals_close_incident():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    alerting._open_incidents["node-2"] = "inc-1"
    alerting._clean_streaks["node-2"] = 2

    mock_redis = AsyncMock()
    mock_redis.get.return_value = _metric()

    with (
        patch("services.alerting.redis", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.evaluate("node-2")
        assert "node-2" not in alerting._open_incidents


@pytest.mark.asyncio
async def test_close_already_closed_incident_noop():
    alerting._open_incidents.pop("node-2", None)

    with (
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting._resolve_incident("node-2")
        assert "node-2" not in alerting._open_incidents


@pytest.mark.asyncio
async def test_alert_after_close_creates_new_incident():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = _metric(cpu=85.0)

    # First alert → opens incident
    with (
        patch("services.alerting.redis", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.evaluate("node-2")
        first_id = alerting._open_incidents["node-2"]

    # Close incident
    alerting._open_incidents.pop("node-2", None)

    # Second alert → creates new incident
    alerting._cooldowns.clear()
    with (
        patch("services.alerting.redis", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.evaluate("node-2")
        second_id = alerting._open_incidents.get("node-2")
        assert second_id is not None
        assert second_id != first_id
