"""V2 isolated network chaos via tc netem.

All tc commands execute inside the backend container's network namespace.
Host networking is never touched.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text

from db import engine

# ── in-memory state ──────────────────────────────────────────────
# Only one active chaos injection at a time, system-wide.

_active: dict | None = None  # {probe_id, chaos_type, value, target_ip, started_at}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_target_ip(probe_id: str) -> str:
    """Look up the endpoint for a probe."""
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT endpoint FROM probes WHERE id = :id"),
            {"id": probe_id},
        )).fetchone()

    if row is None:
        raise ValueError(f"Probe {probe_id} not found")

    return row[0]


async def _apply_tc(target_ip: str, chaos_type: str, value: int | float) -> None:
    """Apply tc netem rules for the given target IP.

    Uses a prio qdisc with 3 bands. Normal traffic follows the default
    priomap and never enters band 2 (1:3). A u32 filter matches the target
    destination IP and directs it to band 2, where netem applies chaos.
    """
    if chaos_type == "latency":
        netem = f"delay {int(value)}ms"
    elif chaos_type == "packet_loss":
        netem = f"loss {float(value)}%"
    else:
        raise ValueError(f"Unknown chaos_type: {chaos_type}")

    # Clear any existing tc rules first
    await _clear_tc()

    # Create prio root qdisc (default 3 bands; band 2=1:3 unused by priomap)
    proc = await asyncio.create_subprocess_exec(
        "tc", "qdisc", "add", "dev", "eth0", "root", "handle", "1:", "prio",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        if "RTNETLINK answers: File exists" not in err:
            raise RuntimeError(f"tc qdisc add prio failed: {err}")

    # Add netem to band 2 (handle 1:3) — normal traffic never reaches this band
    tc_args = ["tc", "qdisc", "add", "dev", "eth0", "parent", "1:3",
               "handle", "10:", "netem"] + netem.split()
    proc = await asyncio.create_subprocess_exec(
        *tc_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"tc qdisc add netem failed: {stderr.decode().strip()}")

    # Filter target IP into band 2 (1:3)
    proc = await asyncio.create_subprocess_exec(
        "tc", "filter", "add", "dev", "eth0", "protocol", "ip", "parent", "1:0", "prio", "1",
        "u32", "match", "ip", "dst", target_ip, "flowid", "1:3",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"tc filter add failed: {stderr.decode().strip()}")


async def _clear_tc() -> None:
    """Remove all tc rules from eth0. Idempotent — succeeds even if no rules exist."""
    proc = await asyncio.create_subprocess_exec(
        "tc", "qdisc", "del", "dev", "eth0", "root",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    # Exit code may be non-zero if no qdisc exists — that's fine


async def inject(probe_id: str, chaos_type: str, value: int | float) -> dict:
    """Inject network chaos targeting a specific probe's endpoint.

    Only one chaos injection can be active at a time.
    Calling inject() while another is active will clear the previous one first.
    """
    global _active

    target_ip = await _resolve_target_ip(probe_id)
    await _apply_tc(target_ip, chaos_type, value)

    _active = {
        "probe_id": probe_id,
        "chaos_type": chaos_type,
        "value": value,
        "target_ip": target_ip,
        "started_at": _utcnow(),
    }
    return dict(_active)


async def recover(probe_id: str | None = None) -> dict | None:
    """Recover from network chaos.

    If probe_id is specified, only clears if that probe matches the active chaos.
    If probe_id is None, clears all chaos unconditionally.
    Returns the completed session with ended_at timestamp.
    """
    global _active

    if probe_id is not None and (_active is None or _active["probe_id"] != probe_id):
        return _active

    await _clear_tc()
    previous = _active
    _active = None
    if previous:
        previous["ended_at"] = _utcnow()
    return previous


def status() -> dict | None:
    """Return current active chaos state, or None if no chaos is active."""
    return dict(_active) if _active else None
