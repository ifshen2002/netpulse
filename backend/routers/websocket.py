import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from db import engine
from services.auth import hash_session_token

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
    token = websocket.query_params.get("access_token")
    project_id = websocket.query_params.get("project_id")
    if not token:
        await websocket.close(code=1008)
        return
    async with engine.connect() as conn:
        row = (await conn.execute(
            text(
                "SELECT u.id FROM auth_sessions s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL "
                "AND s.expires_at > NOW() AND u.is_active = true"
            ),
            {"token_hash": hash_session_token(token)},
        )).fetchone()
        if row is None:
            await websocket.close(code=1008)
            return
        user_id = row[0]
        # Verify project membership
        if project_id:
            member = (await conn.execute(
                text("SELECT 1 FROM memberships WHERE user_id = :user_id AND project_id = :project_id"),
                {"user_id": user_id, "project_id": project_id},
            )).fetchone()
            is_admin = (await conn.execute(
                text("SELECT is_platform_admin FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            )).fetchone()
            if member is None and not (is_admin and is_admin[0]):
                await websocket.close(code=1008)
                return
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
