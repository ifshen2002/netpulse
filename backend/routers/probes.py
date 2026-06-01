"""V2 probe and link REST API endpoints."""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from db import engine
from services.alerting import get_probe_thresholds, set_probe_threshold
from services.probe import get_window_seconds, set_window_seconds

router = APIRouter(prefix="/api", tags=["probes"])

_RESERVED = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}  # nosec B104 — block-list, not a bind
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


class ProbeCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=256)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def _endpoint_valid(cls, v: str) -> str:
        return _validate_endpoint(v)


class ProbeUpdateIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=256)

    @field_validator("endpoint")
    @classmethod
    def _endpoint_valid(cls, v: str) -> str:
        return _validate_endpoint(v)


class WindowConfigIn(BaseModel):
    packet_loss_window_s: int = Field(ge=5, le=600)


class AlertThresholdsIn(BaseModel):
    latency_ms: int | None = Field(default=None, ge=10, le=2000)
    packet_loss_pct: float | None = Field(default=None, ge=0.1, le=100.0)
    availability_pct: float | None = Field(default=None, ge=0.0, le=100.0)


# ── probes ──────────────────────────────────────────────────


@router.get("/probes")
async def list_probes():
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT p.id, p.name, p.protocol, p.endpoint, p.status, "
                "p.last_seen, p.created_at, "
                "l.id AS link_id "
                "FROM probes p "
                "JOIN links l ON l.probe_id = p.id "
                "ORDER BY p.id"
            )
        )
        rows = result.fetchall()

    probes = []
    for row in rows:
        probes.append({
            "id": row[0],
            "name": row[1],
            "protocol": row[2],
            "endpoint": row[3],
            "status": row[4],
            "last_seen": row[5].isoformat() if row[5] else None,
            "created_at": row[6].isoformat() if row[6] else None,
            "link_id": row[7],
        })

    return {"success": True, "data": {"probes": probes, "window_s": get_window_seconds()}}


@router.get("/probes/{probe_id}")
async def get_probe(probe_id: str):
    async with engine.begin() as conn:
        row = (await conn.execute(
            text(
                "SELECT p.id, p.name, p.protocol, p.endpoint, p.status, "
                "p.last_seen, p.created_at, l.id AS link_id "
                "FROM probes p "
                "JOIN links l ON l.probe_id = p.id "
                "WHERE p.id = :id"
            ),
            {"id": probe_id},
        )).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Probe not found")

        metric_row = (await conn.execute(
            text(
                "SELECT latency_ms, packet_loss_pct, availability_pct, "
                "packet_evidence_id, status, timestamp "
                "FROM probe_metrics "
                "WHERE probe_id = :id "
                "ORDER BY timestamp DESC LIMIT 1"
            ),
            {"id": probe_id},
        )).fetchone()

    probe = {
        "id": row[0],
        "name": row[1],
        "protocol": row[2],
        "endpoint": row[3],
        "status": row[4],
        "last_seen": row[5].isoformat() if row[5] else None,
        "created_at": row[6].isoformat() if row[6] else None,
        "link_id": row[7],
    }

    if metric_row:
        probe["latest_metric"] = {
            "latency_ms": metric_row[0],
            "packet_loss_pct": metric_row[1],
            "availability_pct": metric_row[2],
            "packet_evidence_id": metric_row[3],
            "status": metric_row[4],
            "timestamp": metric_row[5].isoformat() if metric_row[5] else None,
        }
    else:
        probe["latest_metric"] = None

    return {"success": True, "data": probe}


@router.post("/probes", status_code=201)
async def create_probe(body: ProbeCreateIn):
    async with engine.begin() as conn:
        count_row = (await conn.execute(
            text("SELECT COUNT(*) FROM probes")
        )).fetchone()
        next_num = count_row[0] + 1
        probe_id = f"probe-{chr(96 + next_num)}" if next_num <= 26 else f"probe-{next_num}"
        link_id = f"link-{chr(96 + next_num)}" if next_num <= 26 else f"link-{next_num}"

        now = datetime.now(timezone.utc)

        await conn.execute(
            text(
                "INSERT INTO probes (id, name, protocol, endpoint, status, last_seen, created_at) "
                "VALUES (:id, :name, 'icmp', :endpoint, 'gray', :now, :now)"
            ),
            {"id": probe_id, "name": body.name, "endpoint": body.endpoint, "now": now},
        )
        await conn.execute(
            text(
                "INSERT INTO links "
                "(id, probe_id, endpoint, protocol, status, last_seen, created_at) "
                "VALUES (:id, :probe_id, :endpoint, 'icmp', 'gray', :now, :now)"
            ),
            {"id": link_id, "probe_id": probe_id, "endpoint": body.endpoint, "now": now},
        )

    return {
        "success": True,
        "data": {
            "id": probe_id,
            "name": body.name,
            "protocol": "icmp",
            "endpoint": body.endpoint,
            "link_id": link_id,
            "status": "gray",
        },
    }


@router.put("/probes/{probe_id}")
async def update_probe(probe_id: str, body: ProbeUpdateIn):
    async with engine.begin() as conn:
        result = await conn.execute(
            text("UPDATE probes SET endpoint = :endpoint WHERE id = :id"),
            {"endpoint": body.endpoint, "id": probe_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Probe not found")

        await conn.execute(
            text("UPDATE links SET endpoint = :endpoint WHERE probe_id = :id"),
            {"endpoint": body.endpoint, "id": probe_id},
        )

    return {"success": True, "data": {"id": probe_id, "endpoint": body.endpoint}}


@router.delete("/probes/{probe_id}")
async def delete_probe(probe_id: str):
    async with engine.begin() as conn:
        exists = (await conn.execute(
            text("SELECT 1 FROM probes WHERE id = :id"), {"id": probe_id}
        )).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Probe not found")

        await conn.execute(
            text("DELETE FROM probe_metrics WHERE probe_id = :id"), {"id": probe_id}
        )
        await conn.execute(
            text("DELETE FROM packet_evidence WHERE probe_id = :id"), {"id": probe_id}
        )
        await conn.execute(
            text("DELETE FROM links WHERE probe_id = :id"), {"id": probe_id}
        )
        await conn.execute(
            text("DELETE FROM probes WHERE id = :id"), {"id": probe_id}
        )

    return {"success": True, "data": {"deleted": probe_id}}


# ── probe metrics ───────────────────────────────────────────


@router.get("/probes/{probe_id}/metrics")
async def get_probe_metrics(probe_id: str, seconds: int = 180):
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT probe_id, link_id, packet_evidence_id, timestamp, "
                "latency_ms, packet_loss_pct, availability_pct, status "
                "FROM probe_metrics "
                "WHERE probe_id = :id "
                "AND timestamp > NOW() - :window * INTERVAL '1 second' "
                "ORDER BY timestamp DESC "
                "LIMIT 500"
            ),
            {"id": probe_id, "window": seconds},
        )).fetchall()

    metrics = []
    for row in rows:
        metrics.append({
            "probe_id": row[0],
            "link_id": row[1],
            "packet_evidence_id": row[2],
            "timestamp": row[3].isoformat() if row[3] else None,
            "latency_ms": row[4],
            "packet_loss_pct": row[5],
            "availability_pct": row[6],
            "status": row[7],
        })

    return {"success": True, "data": {"probe_id": probe_id, "seconds": seconds, "metrics": metrics}}


# ── packet evidence ─────────────────────────────────────────


@router.get("/probes/{probe_id}/evidence")
async def get_packet_evidence(probe_id: str, limit: int = 20):
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT id, probe_id, link_id, protocol, src_ip, dst_ip, "
                "ttl, packet_size_bytes, icmp_seq, rtt_ms, timestamp, raw_output "
                "FROM packet_evidence "
                "WHERE probe_id = :id "
                "ORDER BY timestamp DESC "
                "LIMIT :limit"
            ),
            {"id": probe_id, "limit": limit},
        )).fetchall()

    evidence = []
    for row in rows:
        evidence.append({
            "id": row[0],
            "probe_id": row[1],
            "link_id": row[2],
            "protocol": row[3],
            "src_ip": row[4],
            "dst_ip": row[5],
            "ttl": row[6],
            "packet_size_bytes": row[7],
            "icmp_seq": row[8],
            "rtt_ms": row[9],
            "timestamp": row[10].isoformat() if row[10] else None,
            "raw_output": row[11] or "",
        })

    return {"success": True, "data": {"probe_id": probe_id, "evidence": evidence}}


# ── links ───────────────────────────────────────────────────


@router.get("/links")
async def list_links():
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT l.id, l.probe_id, l.endpoint, l.protocol, l.status, "
                "l.last_seen, l.created_at, p.name AS probe_name "
                "FROM links l "
                "JOIN probes p ON p.id = l.probe_id "
                "ORDER BY l.id"
            )
        )).fetchall()

    links = []
    for row in rows:
        links.append({
            "id": row[0],
            "probe_id": row[1],
            "endpoint": row[2],
            "protocol": row[3],
            "status": row[4],
            "last_seen": row[5].isoformat() if row[5] else None,
            "created_at": row[6].isoformat() if row[6] else None,
            "probe_name": row[7],
        })

    return {"success": True, "data": links}


# ── config ──────────────────────────────────────────────────


@router.patch("/config/packet-loss-window")
async def update_packet_loss_window(body: WindowConfigIn):
    set_window_seconds(body.packet_loss_window_s)
    return {
        "success": True,
        "data": {"packet_loss_window_s": get_window_seconds()},
    }


@router.patch("/config/alert-thresholds")
async def update_alert_thresholds(body: AlertThresholdsIn):
    set_probe_threshold(
        latency_ms=body.latency_ms,
        packet_loss_pct=body.packet_loss_pct,
        availability_pct=body.availability_pct,
    )
    return {
        "success": True,
        "data": get_probe_thresholds(),
    }


@router.get("/config/alert-thresholds")
async def get_alert_thresholds():
    return {
        "success": True,
        "data": get_probe_thresholds(),
    }
