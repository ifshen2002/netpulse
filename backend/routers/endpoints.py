"""V2 endpoint management REST API."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from db import engine
from redis_client import client as redis
from routers.probes import _validate_endpoint

router = APIRouter(prefix="/api", tags=["endpoints"])


class EndpointCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_host: str = Field(min_length=1, max_length=256)

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


class EndpointUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_host: str | None = Field(default=None, min_length=1, max_length=256)
    enabled: bool | None = None

    @field_validator("target_host")
    @classmethod
    def _target_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_endpoint(v)


def _next_ids(next_num: int):
    if next_num <= 26:
        return (
            f"probe-{chr(96 + next_num)}",
            f"link-{chr(96 + next_num)}",
            f"endpoint-{chr(96 + next_num)}",
        )
    return f"probe-{next_num}", f"link-{next_num}", f"endpoint-{next_num}"


@router.get("/endpoints")
async def list_endpoints():
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT e.id, e.name, e.target_host, e.enabled, e.created_at, "
                "COALESCE(p.status, 'gray') AS probe_status, "
                "p.id AS probe_id, l.id AS link_id "
                "FROM endpoints e "
                "LEFT JOIN probes p ON p.endpoint_id = e.id "
                "LEFT JOIN links l ON l.probe_id = p.id "
                "ORDER BY e.created_at"
            )
        )).fetchall()

    endpoints = []
    for row in rows:
        endpoints.append({
            "id": row[0],
            "name": row[1],
            "target_host": row[2],
            "enabled": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "probe_status": row[5],
            "probe_id": row[6],
            "link_id": row[7],
        })

    return {"success": True, "data": endpoints}


@router.get("/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str):
    async with engine.begin() as conn:
        row = (await conn.execute(
            text(
                "SELECT e.id, e.name, e.target_host, e.enabled, e.created_at, "
                "p.id AS probe_id, l.id AS link_id, p.status AS probe_status "
                "FROM endpoints e "
                "LEFT JOIN probes p ON p.endpoint_id = e.id "
                "LEFT JOIN links l ON l.probe_id = p.id "
                "WHERE e.id = :id"
            ),
            {"id": endpoint_id},
        )).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

    return {
        "success": True,
        "data": {
            "id": row[0],
            "name": row[1],
            "target_host": row[2],
            "enabled": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "probe_id": row[5],
            "link_id": row[6],
            "probe_status": row[7],
        },
    }


@router.post("/endpoints", status_code=201)
async def create_endpoint(body: EndpointCreateIn):
    try:
        async with engine.begin() as conn:
            count_row = (await conn.execute(
                text("SELECT COUNT(*) FROM endpoints")
            )).fetchone()
            next_num = count_row[0] + 1
            probe_id, link_id, endpoint_id = _next_ids(next_num)

            now = datetime.now(timezone.utc)

            await conn.execute(
                text(
                    "INSERT INTO endpoints (id, name, target_host, enabled, created_at) "
                    "VALUES (:id, :name, :target_host, true, :now)"
                ),
                {"id": endpoint_id, "name": body.name, "target_host": body.target_host, "now": now},
            )
            await conn.execute(
                text(
                    "INSERT INTO probes (id, name, protocol, endpoint, "
                    "endpoint_id, status, last_seen, created_at) "
                    "VALUES (:id, :name, 'icmp', :endpoint, :eid, 'gray', :now, :now)"
                ),
                {
                    "id": probe_id, "name": body.name, "endpoint": body.target_host,
                    "eid": endpoint_id, "now": now,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO links "
                    "(id, probe_id, endpoint, protocol, status, last_seen, created_at) "
                    "VALUES (:id, :probe_id, :endpoint, 'icmp', 'gray', :now, :now)"
                ),
                {"id": link_id, "probe_id": probe_id, "endpoint": body.target_host, "now": now},
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "success": True,
        "data": {
            "id": endpoint_id,
            "name": body.name,
            "target_host": body.target_host,
            "enabled": True,
            "probe_id": probe_id,
            "link_id": link_id,
        },
    }


@router.put("/endpoints/{endpoint_id}")
async def update_endpoint(endpoint_id: str, body: EndpointUpdateIn):
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT id, name, target_host, enabled FROM endpoints WHERE id = :id"),
            {"id": endpoint_id},
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        new_name = body.name if body.name is not None else existing[1]
        new_target = body.target_host if body.target_host is not None else existing[2]
        new_enabled = body.enabled if body.enabled is not None else existing[3]

        await conn.execute(
            text(
                "UPDATE endpoints SET name = :name, target_host = :target, enabled = :enabled "
                "WHERE id = :id"
            ),
            {"name": new_name, "target": new_target, "enabled": new_enabled, "id": endpoint_id},
        )

        # Sync probe name and endpoint
        await conn.execute(
            text(
                "UPDATE probes SET name = :name, endpoint = :target "
                "WHERE endpoint_id = :eid"
            ),
            {"name": new_name, "target": new_target, "eid": endpoint_id},
        )

        await conn.execute(
            text(
                "UPDATE links SET endpoint = :target "
                "WHERE probe_id = (SELECT id FROM probes WHERE endpoint_id = :eid)"
            ),
            {"target": new_target, "eid": endpoint_id},
        )

    return {
        "success": True,
        "data": {
            "id": endpoint_id,
            "name": new_name,
            "target_host": new_target,
            "enabled": new_enabled,
        },
    }


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str):
    async with engine.begin() as conn:
        row = (await conn.execute(
            text(
                "SELECT p.id AS probe_id, l.id AS link_id "
                "FROM probes p JOIN links l ON l.probe_id = p.id "
                "WHERE p.endpoint_id = :eid"
            ),
            {"eid": endpoint_id},
        )).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        probe_id, link_id = row[0], row[1]

        # Cascade order — child tables first, then parents
        await conn.execute(text("DELETE FROM probe_metrics WHERE probe_id = :id"), {"id": probe_id})
        await conn.execute(
            text("DELETE FROM packet_evidence WHERE probe_id = :id"), {"id": probe_id})
        await conn.execute(
            text("DELETE FROM alerts WHERE probe_id = :id"), {"id": probe_id})
        await conn.execute(
            text("DELETE FROM incidents WHERE probe_id = :id"), {"id": probe_id})
        await conn.execute(text("DELETE FROM links WHERE id = :id"), {"id": link_id})
        await conn.execute(text("DELETE FROM probes WHERE id = :id"), {"id": probe_id})
        await conn.execute(text("DELETE FROM endpoints WHERE id = :id"), {"id": endpoint_id})

    # Clear Redis cache so stale keys don't keep broadcasting
    await redis.delete(f"metrics:latest:probe:{probe_id}")
    await redis.delete(f"packet_evidence:latest:{probe_id}")

    return {"success": True, "data": {"deleted": endpoint_id}}


@router.patch("/endpoints/{endpoint_id}/toggle")
async def toggle_endpoint(endpoint_id: str):
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT enabled FROM endpoints WHERE id = :id"),
            {"id": endpoint_id},
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        new_val = not existing[0]
        await conn.execute(
            text("UPDATE endpoints SET enabled = :enabled WHERE id = :id"),
            {"enabled": new_val, "id": endpoint_id},
        )

    return {"success": True, "data": {"id": endpoint_id, "enabled": new_val}}
