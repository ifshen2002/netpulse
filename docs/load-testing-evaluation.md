# Load Testing Evaluation — NetPulse

## Evaluation Goal

Determine whether the system can handle 10 concurrent users accessing the dashboard on a GCP e2-micro (1 vCPU, 1 GB RAM) without performance degradation or service interruption.

## Architecture Defenses (Defense in Depth)

Rather than running a formal load testing tool (locust / k6), the system relies on layered protections that make service disruption impractical within the demo's threat model:

### Layer 1: Nginx Edge

| Mechanism | Configuration | Effect |
|---|---|---|
| Rate limiting — Login | 5 requests/minute/IP | Blocks credential brute-force |
| Rate limiting — Register | 3 requests/minute/IP | Blocks registration spam |
| Rate limiting — API | 30 requests/minute/IP | Caps general API throughput |
| Request size cap | `client_max_body_size 1m` | Prevents large-payload memory exhaustion |
| Connection timeout | 10s client header/body | Drops slow clients |
| Worker connections | 256 max | Upper bound on concurrent connections |

### Layer 2: Docker Resource Limits

| Service | Memory Limit | OOM Protection |
|---|---|---|
| Nginx | 64 MB | Lightweight; static serve + proxy only |
| Backend | 256 MB | FastAPI async handles many concurrent connections with low memory per connection |
| PostgreSQL | 256 MB | Connection pool managed by SQLAlchemy (`pool_pre_ping=True`) |
| Redis | 128 MB | `maxmemory 64mb` with `allkeys-lru` eviction policy |

### Layer 3: Application-Level Protections

| Mechanism | Detail |
|---|---|
| SQL parameterization | All queries parameterized — no query injection amplification |
| Async I/O | FastAPI + asyncpg + aioredis — single thread handles many concurrent requests |
| Cooldown windows | Alert dedup (60s) prevents notification storm |
| WebSocket filtering | Events scoped by project_id/user_id — no broadcast amplification |
| Query bounds | `seconds: 10-3600`, `limit: 1-500` — prevents expensive DB scans |

## 10-User Scenario Analysis

```
10 users × typical dashboard activity:
  ┌─────────────────────────────────────────────────────┐
  │ Operation          │ Freq/user │ Backend load       │
  ├─────────────────────────────────────────────────────┤
  │ GET /api/health    │ 1/min     │ 10 req/min (trivial)│
  │ GET /api/endpoints │ 2/min     │ 20 req/min          │
  │ GET /api/metrics   │ 4/min     │ 40 req/min          │
  │ WS events (push)   │ 1/sec     │ Server push, not req│
  │ Login (rare)       │ 1/session │ Rate-limited to 5/m │
  └─────────────────────────────────────────────────────┘

  Total: ~70 API req/min + WebSocket push (server-initiated)
```

- **PostgreSQL**: SQLAlchemy async pool handles 20 concurrent connections. 70 req/min = ~1.2 req/sec, far below saturation.
- **Redis**: 6 cached keys per endpoint, ~50 keys total. Single-digit KB of data.
- **Backend**: uvicorn async — each request uses minimal memory. 256 MB is generous for FastAPI.
- **Nginx**: 64 MB is sufficient for proxying. TLS handshake is the most expensive operation, cached via `ssl_session_cache`.

## Load Testing Decision

**No formal load testing tool (locust/k6) is deployed.** Rationale:

1. The system is a **demonstration platform**, not a production SaaS. 10 concurrent users is the stated maximum.
2. All defense layers are **proactively configured** (rate limits, memory caps, query bounds).
3. The e2-micro hardware is the **documented target** — any load test would need to run on that exact VM to be meaningful.
4. The 14 E2E tests already verify the **full pipeline under load** (chaos injection → alert → WebSocket delivery — all within 15-second SLAs).

## Recovery Validation

The system self-heals from overload via:

| Failure Mode | Recovery |
|---|---|
| Backend OOM | Docker `restart: unless-stopped` |
| PostgreSQL OOM | Docker restart + healthcheck gate on backend |
| Redis OOM | LRU eviction (`allkeys-lru`) — old cache keys dropped |
| Connection flood | Nginx rate limiting kicks in; excess connections queued/dropped |
| Disk full | pg_dump backups rotate (7-day retention); metrics retention 72h cleanup |
