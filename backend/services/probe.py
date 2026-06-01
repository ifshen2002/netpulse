"""V2 probe execution service — real ICMP probes.

[V2] Every telemetry value originates from actual probe activity.
Packet Evidence is the source of truth for all probe metrics.
"""

import asyncio
import os
import re
import socket
from datetime import datetime, timezone

DEFAULT_PACKET_LOSS_WINDOW_S = 30
_current_window_s = int(os.environ.get("PACKET_LOSS_WINDOW_S", str(DEFAULT_PACKET_LOSS_WINDOW_S)))


def get_window_seconds() -> int:
    return _current_window_s


def set_window_seconds(seconds: int) -> None:
    global _current_window_s
    _current_window_s = seconds


def get_source_ip(endpoint: str) -> str:
    """Source IP that would be used to reach the given endpoint."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect((endpoint, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"  # nosec B104 — placeholder string when src IP detection fails


def _parse_ping_output(
    output: str,
    endpoint: str,
    probe_id: str,
    src_ip: str,
    ts: datetime,
) -> dict:
    """Parse GNU ping output into structured packet evidence.

    Parses lines like:
        64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=12.4 ms

    Returns a dict with all V2 packet evidence fields.
    A failed probe (no response) returns success=False with zeroed metrics.
    """
    result = {
        "probe_id": probe_id,
        "endpoint": endpoint,
        "protocol": "icmp",
        "success": False,
        "latency_ms": 0.0,
        "src_ip": src_ip,
        "dst_ip": endpoint,
        "ttl": 0,
        "icmp_seq": 0,
        "packet_size_bytes": 0,
        "timestamp": ts.isoformat(),
        "raw_output": output.strip(),
    }

    match = re.search(
        r"(\d+)\s+bytes\s+from\s+[\d.]+\s*:\s*icmp_seq=(\d+)\s+ttl=(\d+)\s+time=([\d.]+)\s*ms",
        output,
    )
    if match:
        result["success"] = True
        result["packet_size_bytes"] = int(match.group(1))
        result["icmp_seq"] = int(match.group(2))
        result["ttl"] = int(match.group(3))
        result["latency_ms"] = float(match.group(4))

    return result


async def run_probe(endpoint: str, probe_id: str) -> dict:
    """Execute a single ICMP ping probe and return structured packet evidence."""
    src_ip = get_source_ip(endpoint)
    ts = datetime.now(timezone.utc)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c", "1",
            "-W", "2",
            endpoint,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        return _parse_ping_output(output, endpoint, probe_id, src_ip, ts)
    except Exception:
        return {
            "probe_id": probe_id,
            "endpoint": endpoint,
            "protocol": "icmp",
            "success": False,
            "latency_ms": 0.0,
            "src_ip": src_ip,
            "dst_ip": endpoint,
            "ttl": 0,
            "icmp_seq": 0,
            "packet_size_bytes": 0,
            "timestamp": ts.isoformat(),
            "raw_output": "",
        }
