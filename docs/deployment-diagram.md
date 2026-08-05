# Deployment Architecture — NetPulse

## Logical Architecture

The system is organized into four logical tiers, each running as an isolated Docker container on a single GCP e2-micro VM.

### Tier 1: Presentation (Nginx + React SPA)
- **Nginx reverse proxy** is the only container with ports exposed to the public internet (80 → 301 redirect to 443, 443 with TLS)
- TLS termination with self-signed certificate (demo) or Let's Encrypt (production)
- Security headers on every response: HSTS, CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy
- Static file serving: React SPA built output (`dist/`) mounted read-only at `/usr/share/nginx/html`
- Rate limiting: `$binary_remote_addr` zones — 5 requests/minute for `/api/auth/login`, 3/min for `/api/auth/register`, 30/min for general `/api/`
- `client_max_body_size 1m` — prevents large-payload attacks
- `access_log` uses `noquery` format — strips query strings so WebSocket `access_token` does not leak into logs

### Tier 2: Application (FastAPI Backend)
- Python 3.12, uvicorn with async I/O
- Monolithic API server organized into 5 service modules and 12 router modules
- `services/auth.py`: password hashing (scrypt), session management (SHA-256 hashed tokens), RBAC enforcement, audit logging, `project_clause()` helper
- `services/probe.py`: ICMP ping subprocess execution and output parsing
- `services/alerting.py`: state-based rule evaluation engine with dedup cooldowns and clean-evaluation streak tracking
- `services/notifications.py`: subscription matching and in-app notification delivery
- `services/netchaos.py`: `tc netem` traffic control via `asyncio.create_subprocess_exec`
- `scheduler.py`: single APScheduler instance — 5s probe collection, 1s WebSocket push, 5s alert evaluation, 15s heartbeat check, 30s project_id backfill, hourly retention cleanup
- Container runs as root (required for `tc netem` NET_ADMIN capability in chaos lab). `cap_add: NET_ADMIN`, `cap_drop: ALL` in docker-compose

### Tier 3: Data (PostgreSQL + Redis)
- **PostgreSQL 16**: source of truth. 9 tables (8 business + 1 migration tracking). All monitoring tables carry `project_id` for tenant isolation. Connection via asyncpg with `pool_pre_ping=True` and `prepared_statement_cache_size=0`
- **Redis 7**: latest-value cache. Stores per-endpoint metrics and packet evidence as JSON strings. Password-protected. `maxmemory 64mb` with `allkeys-lru` eviction policy. Not used as a message broker — WebSocket broadcast is in-process

### Tier 4: Disaster Recovery (Backup Sidecar)
- PostgreSQL `pg_dump -Fc` (custom format) executed daily at 02:00 UTC
- Output written to `./backups/netpulse_YYYYMMDD.dump` on the host filesystem
- 7-day rolling retention via `find -mtime +7 -delete`
- Recovery command: `pg_restore -h postgres -U netpulse -d netpulse backups/netpulse_YYYYMMDD.dump`

## Physical Deployment

Single GCP e2-micro VM (1 vCPU, 1 GB RAM, 30 GB disk) running Docker Compose with 5 containers on a bridge network:

| Container | Image | Memory | Exposed Ports | Purpose |
|---|---|---|---|---|
| nginx | nginx:1.27-alpine (custom) | 64 MB | 80, 443 → host | TLS + proxy + static files + rate limiting |
| backend | python:3.12.9-slim (custom) | 256 MB | 8000 (internal) | FastAPI API server + scheduler |
| postgres | postgres:16-alpine | 256 MB | 5432 (internal) | Relational source of truth |
| redis | redis:7-alpine | 128 MB | 6379 (internal) | In-memory cache |
| backup | postgres:16-alpine | 64 MB | none | Daily pg_dump cron |

**Note**: No database or cache ports are exposed to the host or internet. Only Nginx ports 80/443 are mapped. Internal communication uses Docker's bridge network DNS resolution (`postgres`, `redis`, `backend`).

## Technology Choices (with Rationale)

| Technology | Rationale |
|---|---|
| **FastAPI** | Async-native Python framework; built-in WebSocket support; Pydantic integration for input validation; OpenAPI auto-documentation |
| **PostgreSQL** | ACID compliance for audit logs; JSONB for flexible details columns; mature async driver (asyncpg); Alembic migration toolchain |
| **Redis** | Sub-millisecond cache reads; key expiry for time-window data; lightweight (< 50 keys in production) |
| **React + Zustand** | Component model for dashboard panels; Zustand for simple global state without Redux boilerplate; Recharts for real-time chart updates |
| **Nginx** | Industry-standard reverse proxy; mature TLS termination; `limit_req` module for rate limiting; WebSocket upgrade proxying |
| **Docker Compose** | Single-VM orchestration without Kubernetes complexity; `restart: unless-stopped` for self-healing; resource limits prevent noisy-neighbor problems |
| **scrypt (stdlib)** | No external crypto dependency; N=16384, r=8, p=1 — tuned for demo deployment; uses `hmac.compare_digest` for constant-time verification |
| **APScheduler** | In-process scheduler for single-instance deployment; no external scheduler dependency (Celery/Redis Queue); 10 jobs at fixed intervals |

## Scalability Constraints (Documented)

- **In-memory WebSocket broadcast**: not horizontally scalable. Multi-instance deployment requires Redis Pub/Sub or an external message broker.
- **In-process APScheduler**: not redundant. A second backend instance would duplicate all scheduled jobs.
- **Single PostgreSQL instance**: no read replicas or connection pooling proxy (pgBouncer).

These constraints are acceptable for the single-VM demo deployment. The architecture document (ARCHITECTURE.md §7) explicitly notes each one and prescribes the replacement (Redis Pub/Sub + external scheduler) for scaling beyond one instance.
