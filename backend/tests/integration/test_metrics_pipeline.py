import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from db import engine
from main import app
from redis_client import client as redis_client


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_nodes_api_returns_three(client):
    response = await client.get("/api/nodes")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 3
    ids = {n["id"] for n in data["data"]}
    assert ids == {"node-1", "node-2", "node-3"}


@pytest.mark.asyncio
async def test_metrics_api_reads_inserted_data(client):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-1', NOW(), 45.0, 60.0, 30.0, 10.0, 0.0, 'green')"
            ),
        )

    response = await client.get("/api/metrics/node-1?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    m = data["data"][0]
    assert m["node_id"] == "node-1"
    assert m["cpu"] == 45.0


@pytest.mark.asyncio
async def test_metrics_api_unknown_node_returns_empty(client):
    response = await client.get("/api/metrics/node-unknown-xyz?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"] == []


@pytest.mark.asyncio
async def test_retention_deletes_old_keeps_recent(client):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-1', NOW() - INTERVAL '73 hours', 50, 60, 30, 10, 0, 'green')"
            ),
        )
        await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-1', NOW(), 20, 40, 25, 5, 1, 'green')"
            ),
        )

    recent_id = None
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id FROM metrics WHERE node_id = 'node-1' ORDER BY id DESC LIMIT 1")
        )
        recent_id = result.scalar()

    from scheduler import _cleanup_retention
    await _cleanup_retention()

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id FROM metrics WHERE node_id = 'node-1' AND id = :rid"),
            {"rid": recent_id},
        )
        kept = result.scalar()
        assert kept is not None, "Recent metric should survive retention cleanup"

        result = await conn.execute(
            text("SELECT count(*) FROM metrics WHERE node_id = 'node-1' AND timestamp < NOW() - INTERVAL '72 hours'")
        )
        old = result.scalar()
        assert old == 0, "Old metrics should be deleted"


@pytest.mark.asyncio
async def test_db_write_then_read(client):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-2', NOW(), 33.0, 44.0, 22.0, 7.0, 0.5, 'green')"
            ),
        )

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT cpu, memory FROM metrics WHERE node_id = 'node-2' ORDER BY id DESC LIMIT 1")
        )
        row = result.first()
        assert row is not None
        assert row.cpu == 33.0


@pytest.mark.asyncio
async def test_redis_cache_read_write():
    test_data = {"node_id": "node-1", "cpu": 55.0, "status": "green"}
    await redis_client.set("metrics:latest:test-key", json.dumps(test_data))

    val = await redis_client.get("metrics:latest:test-key")
    assert val is not None
    parsed = json.loads(val)
    assert parsed["cpu"] == 55.0

    await redis_client.delete("metrics:latest:test-key")
