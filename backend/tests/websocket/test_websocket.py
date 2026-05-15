import asyncio
import json

import pytest
import websockets


async def _recv_with_timeout(ws, timeout=5.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def _connect():
    return await websockets.connect("ws://localhost:8000/ws")


@pytest.mark.asyncio
async def test_websocket_receives_metric_update():
    async with await _connect() as ws:
        event = await _recv_with_timeout(ws)
        assert event["type"] == "metric_update"
        assert event["node_id"] in {"node-1", "node-2", "node-3"}
        assert isinstance(event["cpu"], (int, float))
        assert isinstance(event["memory"], (int, float))
        assert event["status"] in {"green", "yellow", "red"}


@pytest.mark.asyncio
async def test_websocket_receives_multiple_nodes():
    seen = set()
    async with await _connect() as ws:
        for _ in range(6):
            event = await _recv_with_timeout(ws)
            seen.add(event["node_id"])
            if len(seen) == 3:
                break
    assert seen == {"node-1", "node-2", "node-3"}


@pytest.mark.asyncio
async def test_websocket_two_clients_both_receive():
    async with await _connect() as ws1, await _connect() as ws2:
        e1 = await _recv_with_timeout(ws1)
        e2 = await _recv_with_timeout(ws2)
        assert e1["type"] == "metric_update"
        assert e2["type"] == "metric_update"
