import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from db import engine
from services.auth import hash_session_token

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Per-connection tracking with user/project affinity for scoped broadcasts.

    Each connection is tagged with its authenticated user_id and optional
    project_id so that broadcast() can filter events to the right audience:

    - Notification events → user_id filter (only the target user)
    - Monitoring events  → project_id filter (only members of that project)
    - Legacy V1 events   → no filter (all clients, backward compat)
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, dict] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, *, user_id: str, project_id: str | None = None) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = {"user_id": user_id, "project_id": project_id}

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def broadcast(self, message: str, *, project_id: str | None = None, user_id: str | None = None) -> None:
        """Send message to matching connections.

        - If *only* user_id is set → deliver to that user (notifications).
        - If *only* project_id is set → deliver to connections in that project.
        - If both are set → deliver to that user within that project.
        - If neither is set → broadcast to all (V1 legacy).
        """
        async with self._lock:
            if project_id is not None or user_id is not None:
                targets = [
                    ws for ws, meta in self._connections.items()
                    if (project_id is None or meta["project_id"] == project_id)
                    and (user_id is None or meta["user_id"] == user_id)
                ]
            else:
                targets = list(self._connections)

        if not targets:
            return

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(message)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*[_send(ws) for ws in targets], return_exceptions=True)
        for failed in results:
            if failed is not None and not isinstance(failed, Exception):
                await self.disconnect(failed)

    @property
    def count(self) -> int:
        return len(self._connections)


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
    await manager.connect(websocket, user_id=user_id, project_id=project_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(websocket)
