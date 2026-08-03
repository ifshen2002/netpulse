import asyncio
import json

import pytest
import websockets

_VALID_TYPES = {
    # V1
    "metric_update", "alert_fired", "incident_opened",
    "incident_closed", "node_status_changed",
    # V2
    "endpoint_metric_update", "packet_evidence", "endpoint_status_changed",
}


async def _recv_with_timeout(ws, timeout=5.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def _recv_type(ws, event_type, timeout=5.0):
    """Receive events until we get one matching `event_type` (or timeout)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timed out waiting for {event_type}")
        event = await _recv_with_timeout(ws, timeout=remaining)
        if event.get("type") == event_type:
            return event


async def _connect():
    return await websockets.connect("ws://localhost:8000/ws")


@pytest.mark.asyncio
async def test_websocket_receives_metric_update():
    async with await _connect() as ws:
        event = await _recv_type(ws, "metric_update")
        assert event["node_id"] in {"node-1", "node-2", "node-3"}
        assert isinstance(event["cpu"], (int, float))
        assert isinstance(event["memory"], (int, float))
        assert event["status"] in {"green", "yellow", "red"}


@pytest.mark.asyncio
async def test_websocket_receives_multiple_nodes():
    seen = set()
    async with await _connect() as ws:
        for _ in range(20):
            event = await _recv_with_timeout(ws)
            if event.get("type") == "metric_update":
                seen.add(event["node_id"])
                if len(seen) == 3:
                    break
    assert seen == {"node-1", "node-2", "node-3"}


@pytest.mark.asyncio
async def test_websocket_two_clients_both_receive():
    async with await _connect() as ws1, await _connect() as ws2:
        e1 = await _recv_type(ws1, "metric_update")
        e2 = await _recv_type(ws2, "metric_update")
        assert e1["type"] == "metric_update"
        assert e2["type"] == "metric_update"


@pytest.mark.asyncio
async def test_websocket_disconnect_cleanup():
    ws = await _connect()
    # Receive one event to confirm connection alive
    event = await _recv_with_timeout(ws, timeout=5.0)
    assert event["type"] in _VALID_TYPES
    # Explicit close
    await ws.close()
    # Verify close is idempotent
    await ws.close()


@pytest.mark.asyncio
async def test_websocket_reconnect_after_disconnect():
    async with await _connect() as ws1:
        await _recv_with_timeout(ws1, timeout=5.0)
    # Reconnect — must succeed with fresh connection
    async with await _connect() as ws2:
        event = await _recv_with_timeout(ws2, timeout=5.0)
        assert event["type"] in _VALID_TYPES
