import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active.discard(websocket)

    async def broadcast(self, message: str) -> None:
        async with self._lock:
            clients = list(self._active)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(message)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*[_send(ws) for ws in clients], return_exceptions=True)
        for failed in results:
            if failed is not None and not isinstance(failed, Exception):
                await self.disconnect(failed)

    @property
    def count(self) -> int:
        return len(self._active)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(websocket)
