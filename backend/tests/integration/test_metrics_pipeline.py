import json

import pytest
from sqlalchemy import text

from db import engine
import redis_client


@pytest.mark.asyncio
async def test_nodes_api_returns_three(client, editor_headers_no_project):
    """V1 synthetic nodes have NULL project_id; query without X-Project-ID."""
    response = await client.get("/api/nodes", headers=editor_headers_no_project)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 3
    ids = {n["id"] for n in data["data"]}
    assert ids == {"node-1", "node-2", "node-3"}


@pytest.mark.asyncio
async def test_metrics_api_reads_inserted_data(client, editor_headers_no_project):
    h = editor_headers_no_project
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-1', NOW(), 45.0, 60.0, 30.0, 10.0, 0.0, 'green')"
            ),
        )

    response = await client.get("/api/metrics/node-1?limit=1", headers=h)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    m = data["data"][0]
    assert m["node_id"] == "node-1"
    assert m["cpu"] == 45.0


@pytest.mark.asyncio
async def test_metrics_api_unknown_node_returns_empty(client, editor_headers_no_project):
    response = await client.get("/api/metrics/node-unknown-xyz?limit=5", headers=editor_headers_no_project)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"] == []


@pytest.mark.asyncio
async def test_retention_deletes_old_keeps_recent(client, editor_headers_no_project):
    h = editor_headers_no_project
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
            text(
                "SELECT count(*) FROM metrics "
                "WHERE node_id = 'node-1' "
                "AND timestamp < NOW() - INTERVAL '72 hours'"
            )
        )
        old = result.scalar()
        assert old == 0, "Old metrics should be deleted"

    # Touch headers so the fixture dependency is satisfied
    assert h["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_db_write_then_read():
    """Write a metric with a unique marker value, read it back by that marker."""
    test_cpu = 99.9
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                "latency_ms, packet_loss_pct, status) "
                "VALUES ('node-1', NOW(), :cpu, 44.0, 22.0, 7.0, 0.5, 'green') "
                "RETURNING id"
            ),
            {"cpu": test_cpu},
        )
        row_id = result.scalar()

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT cpu FROM metrics WHERE id = :id"),
            {"id": row_id},
        )
        row = result.first()
        assert row is not None
        assert row.cpu == test_cpu


@pytest.mark.asyncio
async def test_redis_cache_read_write():
    test_data = {"node_id": "node-1", "cpu": 55.0, "status": "green"}
    await redis_client.client.set("metrics:latest:test-key", json.dumps(test_data))

    val = await redis_client.client.get("metrics:latest:test-key")
    assert val is not None
    parsed = json.loads(val)
    assert parsed["cpu"] == 55.0

    await redis_client.client.delete("metrics:latest:test-key")
