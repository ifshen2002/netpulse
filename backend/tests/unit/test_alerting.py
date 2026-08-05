import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.alerting as alerting


def _make_metric(cpu=35.0, latency=10.0):
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


def _mock_engine():
    conn = AsyncMock()
    fetch_mock = MagicMock()
    fetch_mock.fetchone.return_value = None
    conn.execute = AsyncMock(return_value=fetch_mock)
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
async def test_evaluate_cpu_high_fires_alert():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric(cpu=85.0)

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        result = await alerting.evaluate("node-2")
        assert len(result) == 1
        assert result[0]["alert_type"] == "cpu_high"


@pytest.mark.asyncio
async def test_evaluate_latency_spike_fires_alert():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric(latency=600.0)

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        result = await alerting.evaluate("node-2")
        assert len(result) == 1
        assert result[0]["alert_type"] == "latency_spike"


@pytest.mark.asyncio
async def test_evaluate_normal_metrics_no_alert():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric()

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        result = await alerting.evaluate("node-2")
        assert result == []


@pytest.mark.asyncio
async def test_dedup_cooldown_blocks_repeat():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    alerting._cooldowns[("node-2", "cpu_high")] = datetime.now(timezone.utc)
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric(cpu=90.0)

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        result = await alerting.evaluate("node-2")
        assert result == []


@pytest.mark.asyncio
async def test_dedup_cooldown_expires():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc)
    alerting._cooldowns[("node-2", "cpu_high")] = (
        datetime.now(timezone.utc) - timedelta(seconds=61)
    )
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric(cpu=90.0)

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        result = await alerting.evaluate("node-2")
        assert len(result) == 1


@pytest.mark.asyncio
async def test_heartbeat_timeout_fires():
    alerting._heartbeats["node-2"] = datetime.now(timezone.utc) - timedelta(
        seconds=20
    )
    mock_redis = AsyncMock()
    mock_redis.get.return_value = _make_metric()

    with (
        patch("redis_client.client", mock_redis),
        patch("services.alerting.engine", _mock_engine()),
        patch("services.alerting.manager.broadcast", AsyncMock()),
    ):
        await alerting.check_heartbeats()
        assert ("node-2", "heartbeat_timeout") in alerting._cooldowns
