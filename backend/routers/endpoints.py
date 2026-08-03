"""V2 endpoint management REST API — single source of truth for monitoring targets."""

import re
import socket
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from db import engine
from redis_client import client as redis
from services.auth import CurrentUser, audit, project_clause, require_project_editor, require_project_member
from services.probe import get_window_seconds, set_window_seconds

router = APIRouter(prefix="/api", tags=["endpoints"])

_RESERVED = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_LOOPBACK_RE = re.compile(r"^127\.\d+\.\d+\.\d+$")


def _validate_endpoint(v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("endpoint must not be empty")
    lower = stripped.lower()
    if lower in _RESERVED:
        raise ValueError("endpoint is reserved and not monitorable")
    if _LOOPBACK_RE.match(lower):
        raise ValueError("loopback addresses are not monitorable")
    return stripped


class EndpointCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_host: str = Field(min_length=1, max_length=256)
    source_ip: str | None = Field(default=None, min_length=1, max_length=45)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("target_host")
    @classmethod
    def _target_valid(cls, v: str) -> str:
        return _validate_endpoint(v)

    @field_validator("source_ip")
    @classmethod
    def _source_ip_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        return stripped


class EndpointUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_host: str | None = Field(default=None, min_length=1, max_length=256)
    source_ip: str | None = Field(default=None, min_length=1, max_length=45)
    enabled: bool | None = None

    @field_validator("target_host")
    @classmethod
    def _target_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_endpoint(v)


class WindowConfigIn(BaseModel):
    packet_loss_window_s: int = Field(ge=5, le=600)


def _endpoint_id(num: int) -> str:
    if num <= 26:
        return f"endpoint-{chr(96 + num)}"
    return f"endpoint-{num}"


def _detect_source_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


# ── endpoints CRUD ────────────────────────────────────────────


@router.get("/endpoints")
async def list_endpoints(
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    clause, params = project_clause(project_id, "e")
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                f"SELECT e.id, e.name, e.target_host, e.source_ip, e.enabled, "
                f"e.status, e.last_seen, e.protocol, e.created_at "
                f"FROM endpoints e "
                f"WHERE 1=1{clause} ORDER BY e.created_at"
            ), params
        )).fetchall()

    endpoints = []
    for row in rows:
        endpoints.append({
            "id": row[0],
            "name": row[1],
            "target_host": row[2],
            "source_ip": row[3],
            "enabled": row[4],
            "status": row[5],
            "last_seen": row[6].isoformat() if row[6] else None,
            "protocol": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        })

    return {"success": True, "data": endpoints}


@router.get("/endpoints/{endpoint_id}")
async def get_endpoint(
    endpoint_id: str,
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    clause, params = project_clause(project_id, "e")
    params["id"] = endpoint_id
    async with engine.begin() as conn:
        row = (await conn.execute(
            text(
                f"SELECT e.id, e.name, e.target_host, e.source_ip, e.enabled, "
                f"e.status, e.last_seen, e.protocol, e.created_at "
                f"FROM endpoints e "
                f"WHERE e.id = :id{clause}"
            ),
            params,
        )).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

    return {
        "success": True,
        "data": {
            "id": row[0],
            "name": row[1],
            "target_host": row[2],
            "source_ip": row[3],
            "enabled": row[4],
            "status": row[5],
            "last_seen": row[6].isoformat() if row[6] else None,
            "protocol": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        },
    }


@router.post("/endpoints", status_code=201)
async def create_endpoint(
    body: EndpointCreateIn,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    try:
        async with engine.begin() as conn:
            count_row = (await conn.execute(
                text("SELECT COUNT(*) FROM endpoints")
            )).fetchone()
            endpoint_id = _endpoint_id(count_row[0] + 1)
            now = datetime.now(timezone.utc)
            source_ip = body.source_ip or _detect_source_ip()

            await conn.execute(
                text(
                    "INSERT INTO endpoints (id, name, target_host, source_ip, protocol, "
                    "status, last_seen, enabled, project_id, created_at) "
                    "VALUES (:id, :name, :target_host, :source_ip, 'icmp', "
                    "'gray', :now, true, :project_id, :now)"
                ),
                {
                    "id": endpoint_id, "name": body.name, "target_host": body.target_host,
                    "source_ip": source_ip, "now": now, "project_id": project_id,
                },
            )
            await audit(
                conn,
                action="endpoint.created",
                actor_user_id=user.id,
                resource_type="endpoint",
                resource_id=endpoint_id,
                details={"name": body.name, "target_host": body.target_host},
                project_id=project_id,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "success": True,
        "data": {
            "id": endpoint_id,
            "name": body.name,
            "target_host": body.target_host,
            "source_ip": source_ip,
            "enabled": True,
        },
    }


@router.put("/endpoints/{endpoint_id}")
async def update_endpoint(
    endpoint_id: str,
    body: EndpointUpdateIn,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    async with engine.begin() as conn:
        clause, params = project_clause(project_id)
        params["id"] = endpoint_id
        existing = (await conn.execute(
            text(
                f"SELECT id, name, target_host, source_ip, enabled "
                f"FROM endpoints WHERE id = :id{clause}"
            ),
            params,
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        new_name = body.name if body.name is not None else existing[1]
        new_target = body.target_host if body.target_host is not None else existing[2]
        new_source_ip = body.source_ip if body.source_ip is not None else existing[3]
        new_enabled = body.enabled if body.enabled is not None else existing[4]

        await conn.execute(
            text(
                "UPDATE endpoints SET name = :name, target_host = :target, "
                "source_ip = :source_ip, enabled = :enabled "
                "WHERE id = :id"
            ),
            {
                "name": new_name, "target": new_target,
                "source_ip": new_source_ip, "enabled": new_enabled, "id": endpoint_id,
            },
        )
        await audit(
            conn,
            action="endpoint.updated",
            actor_user_id=user.id,
            resource_type="endpoint",
            resource_id=endpoint_id,
            details={"name": new_name, "target_host": new_target, "source_ip": new_source_ip, "enabled": new_enabled},
            project_id=project_id,
        )

    return {
        "success": True,
        "data": {
            "id": endpoint_id,
            "name": new_name,
            "target_host": new_target,
            "source_ip": new_source_ip,
            "enabled": new_enabled,
        },
    }


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    async with engine.begin() as conn:
        clause, params = project_clause(project_id)
        params["id"] = endpoint_id
        existing = (await conn.execute(
            text(
                f"SELECT 1 FROM endpoints WHERE id = :id{clause}"
            ),
            params,
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        await conn.execute(text("DELETE FROM probe_metrics WHERE endpoint_id = :id"), {"id": endpoint_id})
        await conn.execute(text("DELETE FROM packet_evidence WHERE endpoint_id = :id"), {"id": endpoint_id})
        await conn.execute(text("DELETE FROM alerts WHERE endpoint_id = :id"), {"id": endpoint_id})
        await conn.execute(text("DELETE FROM incidents WHERE endpoint_id = :id"), {"id": endpoint_id})
        await conn.execute(text("DELETE FROM endpoints WHERE id = :id"), {"id": endpoint_id})
        await audit(
            conn,
            action="endpoint.deleted",
            actor_user_id=user.id,
            resource_type="endpoint",
            resource_id=endpoint_id,
            project_id=project_id,
        )

    await redis.delete(f"metrics:latest:endpoint:{endpoint_id}")
    await redis.delete(f"packet_evidence:latest:{endpoint_id}")

    return {"success": True, "data": {"deleted": endpoint_id}}


@router.patch("/endpoints/{endpoint_id}/toggle")
async def toggle_endpoint(
    endpoint_id: str,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    async with engine.begin() as conn:
        clause, params = project_clause(project_id)
        params["id"] = endpoint_id
        existing = (await conn.execute(
            text(
                f"SELECT enabled FROM endpoints WHERE id = :id{clause}"
            ),
            params,
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        new_val = not existing[0]
        await conn.execute(
            text("UPDATE endpoints SET enabled = :enabled WHERE id = :id"),
            {"enabled": new_val, "id": endpoint_id},
        )
        await audit(
            conn,
            action="endpoint.toggled",
            actor_user_id=user.id,
            resource_type="endpoint",
            resource_id=endpoint_id,
            project_id=project_id,
            details={"enabled": new_val},
        )

    return {"success": True, "data": {"id": endpoint_id, "enabled": new_val}}


# ── endpoint metrics ───────────────────────────────────────────


@router.get("/endpoints/{endpoint_id}/metrics")
async def get_endpoint_metrics(
    endpoint_id: str,
    seconds: int = 180,
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    async with engine.begin() as conn:
        clause, params = project_clause(project_id)
        params["id"] = endpoint_id
        ep = (await conn.execute(
            text(
                f"SELECT 1 FROM endpoints WHERE id = :id{clause}"
            ),
            params,
        )).fetchone()
        if ep is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        rows = (await conn.execute(
            text(
                "SELECT endpoint_id, packet_evidence_id, timestamp, "
                "latency_ms, packet_loss_pct, availability_pct, status "
                "FROM probe_metrics "
                "WHERE endpoint_id = :id "
                "AND timestamp > NOW() - :window * INTERVAL '1 second' "
                "ORDER BY timestamp DESC LIMIT 500"
            ),
            {"id": endpoint_id, "window": seconds},
        )).fetchall()

    metrics = []
    for row in rows:
        metrics.append({
            "endpoint_id": row[0],
            "packet_evidence_id": row[1],
            "timestamp": row[2].isoformat() if row[2] else None,
            "latency_ms": row[3],
            "packet_loss_pct": row[4],
            "availability_pct": row[5],
            "status": row[6],
        })

    return {"success": True, "data": {"endpoint_id": endpoint_id, "seconds": seconds, "metrics": metrics}}


# ── packet evidence ────────────────────────────────────────────


@router.get("/endpoints/{endpoint_id}/evidence")
async def get_packet_evidence(
    endpoint_id: str,
    limit: int = 20,
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    async with engine.begin() as conn:
        clause, params = project_clause(project_id)
        params["id"] = endpoint_id
        ep = (await conn.execute(
            text(
                f"SELECT 1 FROM endpoints WHERE id = :id{clause}"
            ),
            params,
        )).fetchone()
        if ep is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        rows = (await conn.execute(
            text(
                "SELECT id, endpoint_id, protocol, src_ip, dst_ip, "
                "ttl, packet_size_bytes, icmp_seq, rtt_ms, timestamp, raw_output "
                "FROM packet_evidence "
                "WHERE endpoint_id = :id "
                "ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"id": endpoint_id, "limit": limit},
        )).fetchall()

    evidence = []
    for row in rows:
        evidence.append({
            "id": row[0],
            "endpoint_id": row[1],
            "protocol": row[2],
            "src_ip": row[3],
            "dst_ip": row[4],
            "ttl": row[5],
            "packet_size_bytes": row[6],
            "icmp_seq": row[7],
            "rtt_ms": row[8],
            "timestamp": row[9].isoformat() if row[9] else None,
            "raw_output": row[10] or "",
        })

    return {"success": True, "data": {"endpoint_id": endpoint_id, "evidence": evidence}}


# ── source IPs ─────────────────────────────────────────────────


@router.get("/source-ips")
async def list_source_ips(user: CurrentUser = Depends(require_project_member)):
    source_ips = [_detect_source_ip()]
    unique = sorted(set(ip for ip in source_ips if ip != "0.0.0.0"))
    return {"success": True, "data": unique}


# ── config ─────────────────────────────────────────────────────


@router.patch("/config/packet-loss-window")
async def update_packet_loss_window(
    body: WindowConfigIn,
    user: CurrentUser = Depends(require_project_editor),
):
    set_window_seconds(body.packet_loss_window_s)
    async with engine.begin() as conn:
        await audit(
            conn,
            action="config.packet_loss_window.updated",
            actor_user_id=user.id,
            resource_type="config",
            resource_id="packet_loss_window",
            details={"packet_loss_window_s": body.packet_loss_window_s},
        )
    return {
        "success": True,
        "data": {"packet_loss_window_s": get_window_seconds()},
    }
