"""
Load testing for NetPulse — measures response time and throughput
of the running backend under concurrent load.

This is a CI-friendly load test (uses asyncio + httpx, no external tools required).
Runs against a live backend on localhost:8000.

Usage:
    pytest tests/load/ -v --no-cov --tb=short

Output:
    Prints latency statistics per endpoint and saves a JSON report
    to tests/load/load-report.json
"""

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE_URL = os.environ.get("LOAD_TEST_BASE_URL", "http://localhost:8000")
CONCURRENT_USERS = int(os.environ.get("LOAD_TEST_CONCURRENT_USERS", "10"))
DURATION_S = int(os.environ.get("LOAD_TEST_DURATION_S", "15"))


async def hit_endpoint(client: httpx.AsyncClient, method: str, path: str, label: str, results: list) -> None:
    """Make one request and record latency. Never raises — failures are recorded as errors."""
    t0 = time.monotonic()
    try:
        resp = await client.request(method, path, timeout=10.0)
        latency_ms = (time.monotonic() - t0) * 1000
        results.append({
            "label": label,
            "status": resp.status_code,
            "latency_ms": latency_ms,
        })
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        results.append({
            "label": label,
            "status": 0,
            "latency_ms": latency_ms,
            "error": str(e),
        })


async def worker(client: httpx.AsyncClient, end_time: float, results: list, user_id: int) -> None:
    """Simulate one user making requests until DURATION_S elapses."""
    # Mix of read-heavy endpoints (typical dashboard load pattern)
    endpoints = [
        ("GET", "/api/health", "health_check"),
        ("GET", "/api/endpoints", "list_endpoints"),
        ("GET", "/api/incidents", "list_incidents"),
        ("GET", "/api/alerts", "list_alerts"),
    ]
    while time.monotonic() < end_time:
        # Each user picks a random endpoint each iteration
        method, path, label = endpoints[user_id % len(endpoints)]
        await hit_endpoint(client, method, path, f"{label}_user{user_id}", results)


async def main() -> dict:
    """Run the load test and return a structured report."""
    print(f"Load test: {CONCURRENT_USERS} concurrent users, {DURATION_S}s duration, target {BASE_URL}")
    print(f"Starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Warm-up: 1 request to verify backend is up
        try:
            r = await client.get("/api/health", timeout=5.0)
            if r.status_code != 200:
                print(f"Backend health check failed: {r.status_code} {r.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Backend not reachable: {e}")
            sys.exit(1)

        print("Backend healthy. Starting load test...")

        results: list = []
        end_time = time.monotonic() + DURATION_S
        start_time = time.monotonic()

        # Spawn CONCURRENT_USERS concurrent workers
        workers = [
            asyncio.create_task(worker(client, end_time, results, uid))
            for uid in range(CONCURRENT_USERS)
        ]
        await asyncio.gather(*workers)

        actual_duration = time.monotonic() - start_time
        total_requests = len(results)

    # Aggregate per-endpoint statistics
    by_label: dict[str, list] = {}
    for r in results:
        by_label.setdefault(r["label"].rsplit("_user", 1)[0], []).append(r)

    report = {
        "target": BASE_URL,
        "concurrent_users": CONCURRENT_USERS,
        "configured_duration_s": DURATION_S,
        "actual_duration_s": round(actual_duration, 2),
        "total_requests": total_requests,
        "throughput_rps": round(total_requests / actual_duration, 2),
        "endpoints": {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    for label, rs in sorted(by_label.items()):
        latencies = [r["latency_ms"] for r in rs]
        statuses = [r["status"] for r in rs]
        errors = sum(1 for s in statuses if s == 0 or s >= 500)
        successes = sum(1 for s in statuses if 200 <= s < 400)
        report["endpoints"][label] = {
            "count": len(rs),
            "success_count": successes,
            "error_count": errors,
            "error_rate_pct": round(errors / len(rs) * 100, 2) if rs else 0,
            "latency_ms": {
                "min": round(min(latencies), 2) if latencies else 0,
                "max": round(max(latencies), 2) if latencies else 0,
                "mean": round(statistics.mean(latencies), 2) if latencies else 0,
                "median": round(statistics.median(latencies), 2) if latencies else 0,
                "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if len(latencies) >= 20 else (round(max(latencies), 2) if latencies else 0),
                "p99": round(sorted(latencies)[int(len(latencies) * 0.99)], 2) if len(latencies) >= 100 else (round(max(latencies), 2) if latencies else 0),
            },
        }

    return report


def print_report(report: dict) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 70)
    print("LOAD TEST REPORT")
    print("=" * 70)
    print(f"Target:               {report['target']}")
    print(f"Concurrent users:     {report['concurrent_users']}")
    print(f"Duration:             {report['actual_duration_s']}s (configured {report['configured_duration_s']}s)")
    print(f"Total requests:       {report['total_requests']}")
    print(f"Throughput:           {report['throughput_rps']} req/s")
    print()
    print(f"{'Endpoint':<20} {'Count':>6} {'OK':>5} {'Err':>5} {'Err%':>6} {'Mean':>8} {'p95':>8} {'Max':>8}")
    print("-" * 70)
    for label, stats in sorted(report["endpoints"].items()):
        lat = stats["latency_ms"]
        print(
            f"{label:<20} {stats['count']:>6} {stats['success_count']:>5} {stats['error_count']:>5} "
            f"{stats['error_rate_pct']:>6}% {lat['mean']:>7.1f}ms {lat['p95']:>7.1f}ms {lat['max']:>7.1f}ms"
        )
    print("=" * 70)


if __name__ == "__main__":
    report = asyncio.run(main())
    print_report(report)

    # Save to JSON
    out_path = Path(__file__).parent / "load-report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved to {out_path}")
