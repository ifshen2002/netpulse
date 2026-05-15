# ARCHITECTURE.md — NetPulse System Design

> Highest-priority source of truth. All other documents defer to this one.
> Implementation contracts are included here. No separate CONTRACTS.md exists.

---

# 1. System Definition

**NetPulse** monitors three nodes:

- **Node-1**: read-only host observer (real psutil metrics)
- **Node-2 / Node-3**: synthetic cloud service nodes (simulator-generated, chaos-capable)

No real physical network devices. No auth. Single VM deployment.

---

# 2. Locked Stack Decisions

| Concern | Decision |
|---|---|
| Frontend | React + Recharts + TailwindCSS + Zustand |
| Backend | FastAPI monolith, layered internally |
| Realtime | WebSocket + in-memory broadcast manager |
| Cache | Redis, latest metrics per node only (no Pub/Sub) |
| DB | PostgreSQL, source of truth |
| Scheduler | Single APScheduler instance |
| Deployment | Docker Compose, single VM |
| Auth | None (out of scope) |
| Simulated nodes | Generated inside backend simulator module |
| Chaos model | Overlay only — raw metrics never mutated |
| Incident model | One Incident contains many Alerts |
| Chaos recovery | Registry mechanism, recover_all clears registry |
| Node status | green / yellow / red / gray |
| Metrics retention | 72 hours |
| Alert dedup | 60-second cooldown per (node_id, alert_type) |
| Incident auto-close | 3 consecutive clean evaluations |
| Packet loss sim | Deterministic |
| Burst mode | Reporting frequency increase only (5s → 1s) |
| Docker logging | Rotation required on all containers |

---

# 3. System Architecture

```
Browser
  React Dashboard (Recharts + TailwindCSS + Zustand)
       │
       │ HTTP REST + WebSocket
       ▼
    Nginx
      /api  → backend:8000
      /ws   → backend:8000
      /     → frontend:3000
       │
       ▼
  FastAPI Backend
  ┌─────────────────────────────────────────┐
  │ routers/      services/     scheduler/  │
  │ - nodes       - monitoring  APScheduler │
  │ - metrics     - alerting    5s collect  │
  │ - alerts      - incident    1s push     │
  │ - incidents   - chaos       15s hb chk  │
  │ - chaos       - simulator               │
  │ - websocket                             │
  └──────────────┬──────────────────────────┘
                 │
              Redis (cache only)
              PostgreSQL (source of truth)
```

---

# 4. Module Boundaries

## simulator.py
- Generates baseline fake metrics for Node-2 and Node-3
- Values within normal operating ranges
- Exposes node on/off toggle and burst mode
- **MUST NOT import chaos.py**
- **MUST NOT know about chaos state**

## chaos.py
- Maintains chaos registry in memory
- `apply_overlay(raw_metrics)` is the ONLY mutation point
- **MUST NOT generate baseline metrics**
- **MUST NOT import simulator.py**

## Pipeline (never reverse this):
```
simulator.py → baseline metrics → chaos.py overlay → display/storage
```

---

# 5. Host Safety — Non-Negotiable

Node-1 is strictly read-only. Forbidden on Node-1:
- CPU stress, memory pressure, network/DNS/firewall modification
- Any chaos injection

Chaos operates ONLY on synthetic nodes via overlay metrics. The VM must never be intentionally destabilized.

---

# 6. Unified Metrics Schema

Every metrics object from any node MUST match exactly:

```json
{
  "node_id": "string",
  "timestamp": "ISO8601 UTC",
  "cpu": 0.0,
  "memory": 0.0,
  "disk": 0.0,
  "latency_ms": 0.0,
  "packet_loss_pct": 0.0,
  "status": "green|yellow|red|gray"
}
```

Rules: no null fields, all values numeric, bounded (cpu/memory/disk: 0-100, latency_ms: ≥0, packet_loss_pct: 0-100), no NaN, no negative percentages.

Display metrics always = `chaos.apply_overlay(raw_metrics)`. Raw metrics never modified in-place.

---

# 7. WebSocket Event Schemas

Backend pushes normalized events only — no full snapshots.

### metric_update
```json
{"type": "metric_update", "node_id": "node-1", "cpu": 45.2, "memory": 62.1, "disk": 38.0, "latency_ms": 12.0, "packet_loss_pct": 0.0, "status": "green", "timestamp": "..."}
```

### alert_fired
```json
{"type": "alert_fired", "alert_id": "uuid", "node_id": "node-1", "alert_type": "cpu_high", "message": "CPU at 82%", "timestamp": "..."}
```

### incident_opened
```json
{"type": "incident_opened", "incident_id": "uuid", "title": "...", "timestamp": "..."}
```

### incident_closed
```json
{"type": "incident_closed", "incident_id": "uuid", "timestamp": "..."}
```

### node_status_changed
```json
{"type": "node_status_changed", "node_id": "node-2", "status": "red", "timestamp": "..."}
```

Zustand stores handle each event independently. No snapshot replacement.

---

# 8. Database Schema

### nodes
```sql
id VARCHAR PRIMARY KEY, name VARCHAR, type VARCHAR,
status VARCHAR, last_seen TIMESTAMP, created_at TIMESTAMP
```

### metrics
```sql
id SERIAL PRIMARY KEY, node_id VARCHAR REFERENCES nodes(id),
timestamp TIMESTAMP, cpu FLOAT, memory FLOAT, disk FLOAT,
latency_ms FLOAT, packet_loss_pct FLOAT, status VARCHAR
-- Index: (node_id, timestamp)
-- Retention: delete rows older than 72h
```

### alerts
```sql
id UUID PRIMARY KEY, node_id VARCHAR REFERENCES nodes(id),
incident_id UUID REFERENCES incidents(id) NULL,
alert_type VARCHAR, message VARCHAR,
fired_at TIMESTAMP, resolved_at TIMESTAMP NULL
```

### incidents
```sql
id UUID PRIMARY KEY, title VARCHAR, status VARCHAR,
opened_at TIMESTAMP, closed_at TIMESTAMP NULL
```

### chaos_events
```sql
id UUID PRIMARY KEY, chaos_type VARCHAR, node_id VARCHAR,
started_at TIMESTAMP, ended_at TIMESTAMP NULL, config JSONB
```

---

# 9. Alert & Incident Rules

### Alert Thresholds
| Condition | Alert Type |
|---|---|
| CPU > 80% | cpu_high |
| Latency > 500ms | latency_spike |
| No heartbeat 15s | heartbeat_timeout |

### Deduplication
- Key: `(node_id, alert_type)`
- Cooldown: 60 seconds
- During cooldown: no DB insert, no WebSocket broadcast

### Incident Lifecycle
- Opens on first non-deduplicated alert (one open incident per node max)
- Closes only after 3 consecutive clean evaluations
- Timeline events are append-only

### Node Status Recovery
- Node returns to `green` only after 3 consecutive healthy evaluations

---

# 10. Chaos Injection

### Types
| Type | Effect |
|---|---|
| latency_spike | latency_ms += random(200, 800) |
| packet_loss | drop every 5th heartbeat |
| cpu_spike | cpu += injected_value (cap 100) |
| db_exhaustion | simulated alert only, no real DB harm |
| cache_unavailable | simulated alert only, no real Redis harm |
| recover_all | clear entire chaos registry |

### Registry pattern
```python
active_chaos = {"node-2": ["latency_spike"]}
```

`recover_all()` clears registry, restores overlays, preserves historical chaos_events rows.

---

# 11. Scheduler (Single Instance)

APScheduler responsibilities:
- 5s: metrics collection (1s in burst mode)
- 1s: WebSocket metric push
- 15s: heartbeat evaluation
- periodic: alert evaluation, incident evaluation, retention cleanup (72h)

**One APScheduler only. No child schedulers. No recursive scheduling.**

---

# 12. Resource Budget

| Resource | Limit |
|---|---|
| VM | GCP e2-micro |
| RAM | 1GB |
| Disk | 30GB |
| Max nodes | 3 |
| Max WebSocket clients | 5 |
| Metrics retention | 72 hours |

Docker Compose services: `nginx`, `frontend`, `backend`, `redis`, `postgres`

All containers MUST use log rotation:
```yaml
logging:
  options:
    max-size: "10m"
    max-file: "3"
```

Startup order: postgres → redis → backend → frontend → nginx

---

# 13. API Response Envelope

Success: `{"success": true, "data": {}}`
Error: `{"success": false, "error": {"code": "string", "message": "string"}}`

Node IDs are locked: `node-1`, `node-2`, `node-3`

---

# 14. Frontend Rules

- Zustand is the ONLY global state system (no Redux, no MobX)
- WebSocket disconnect: show degraded badge, keep dashboard mounted, bounded reconnect retry
- Charts render bounded data only, support realtime updates
- Max 4 major dashboard panels

---

# 15. File Structure

```
netpulse/
├── CLAUDE.md
├── ARCHITECTURE.md
├── DECISIONS.md
├── SPRINT.md
├── docker-compose.yml
├── docker-compose.test.yml
│
├── backend/
│   ├── main.py
│   ├── db.py
│   ├── redis_client.py
│   ├── scheduler.py
│   ├── routers/
│   │   ├── nodes.py
│   │   ├── metrics.py
│   │   ├── alerts.py
│   │   ├── incidents.py
│   │   ├── chaos.py
│   │   └── websocket.py
│   ├── services/
│   │   ├── monitoring.py
│   │   ├── simulator.py
│   │   ├── chaos.py
│   │   ├── alerting.py
│   │   └── incident.py
│   ├── models/
│   ├── schemas/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── websocket/
│       └── chaos/
│
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── store/
│       ├── hooks/
│       │   └── useWebSocket.js
│       └── components/
│           ├── NodeCard.jsx
│           ├── MetricsChart.jsx
│           ├── AlertBanner.jsx
│           ├── IncidentTimeline.jsx
│           ├── ChaosPanel.jsx
│           └── NodeControls.jsx
│
├── nginx/
│   └── nginx.conf
│
└── .github/
    └── workflows/
        └── ci.yml
```

**Folder discipline: max 5 items per folder level. Keep nesting shallow.**
