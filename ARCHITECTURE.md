# ARCHITECTURE.md — NetPulse System Design

> Highest-priority source of truth. All other documents defer to this one.
> Implementation contracts are included here. No separate CONTRACTS.md exists.

\---

# 0\. \[V2] Architecture Revision Notice

> This section extends the original architecture.
> It does not replace the original architecture.
>
> Existing implementation remains valid unless explicitly marked as:
>
> - \\\[DEPRECATED]
> - \\\[SUPERSEDED]
> - \\\[LEGACY]
> - \\\[REMOVE IN V2]
>
> All migration work must preserve compatibility wherever practical.

### Why this revision exists

Supervisor feedback identified a mismatch between the project positioning and the actual monitoring model.

The original architecture successfully demonstrates:

* realtime telemetry
* alerting
* incidents
* chaos injection
* CI/CD

However, the primary monitored entity in V1 is Node, while the V2 direction must focus on:

* Probe
* Endpoint
* Link
* Telemetry
* Packet Evidence

### V1 versus V2

V1 is the legacy model and remains supported for compatibility.

V2 is the primary architecture direction.

### Migration principle

The system must prefer real network evidence over synthetic metric generation whenever technically possible.

All displayed metrics must be explainable, traceable, and grounded in a concrete probe action or derived aggregation of probe results.

\---

# 1\. System Definition

**NetPulse** monitors three nodes in the legacy model:

* **Node-1**: read-only host observer (real psutil metrics)
* **Node-2 / Node-3**: synthetic cloud service nodes (simulator-generated, chaos-capable)

**\[V2] Primary monitoring model:** NetPulse also supports a link-centric probe model:

* **Probe**: a first-class measurement agent that originates telemetry
* **Endpoint**: a real, reachable target such as a public DNS or HTTP endpoint
* **Link**: a source-to-target probe path
* **Packet Evidence**: a compact, structured representation of a real probe packet and its response

No real physical network devices. No auth. Single VM deployment.

**\[LEGACY]** Node monitoring remains available as a compatibility layer and demo fallback.

**\[V2]** Link monitoring is the primary operational view.

\---

# 2\. Locked Stack Decisions

|Concern|Decision|
|-|-|
|Frontend|React + Recharts + TailwindCSS + Zustand|
|Backend|FastAPI monolith, layered internally|
|Realtime|WebSocket + in-memory broadcast manager|
|Cache|Redis, latest metrics per probe/link plus latest legacy node metrics|
|DB|PostgreSQL, source of truth|
|Scheduler|Single APScheduler instance|
|Deployment|Docker Compose, single VM|
|Auth|None (out of scope)|
|Simulated nodes|Generated inside backend simulator module|
|Chaos model|\[LEGACY] Overlay only for V1; \[V2] isolated network chaos for probe traffic|
|Incident model|One Incident contains many Alerts|
|Chaos recovery|Registry mechanism, recover\_all clears registry|
|Node status|green / yellow / red / gray|
|Metrics retention|72 hours|
|Alert dedup|60-second cooldown per (node\_id, alert\_type) or per (probe\_id, alert\_type) in V2|
|Incident auto-close|3 consecutive clean evaluations|
|Packet loss sim|\[LEGACY] deterministic overlay simulation; \[V2] derived from real probe outcomes|
|Burst mode|Reporting frequency increase only (5s → 1s) in V1; probe sampling remains 5s default in V2|
|Docker logging|Rotation required on all containers|

\---

# 3\. System Architecture

```text
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
  ┌──────────────────────────────────────────────────────────┐
  │ routers/      services/        scheduler/                │
  │ - nodes       - monitoring     APScheduler              │
  │ - metrics     - alerting       5s collect               │
  │ - alerts      - incident       1s push                  │
  │ - incidents   - chaos          15s hb chk               │
  │ - chaos       - simulator      \\\[V2] probe, endpoint     │
  │ - websocket   - telemetry      \\\[V2] packet evidence     │
  └──────────────────────────────────────────────────────────┘
                 │
              Redis (cache only)
              PostgreSQL (source of truth)
```

**\[V2] Architecture intent:** the backend remains a FastAPI monolith, but the domain model shifts from node-centric simulation to probe-centric real telemetry.

**\[V2] No new infrastructure services are introduced.** The project continues to use the existing deployment stack.

\---

# 4\. Module Boundaries

## simulator.py

* Generates baseline fake metrics for Node-2 and Node-3
* Values within normal operating ranges
* Exposes node on/off toggle and burst mode
* **MUST NOT import chaos.py**
* **MUST NOT know about chaos state**

**\[LEGACY]** This module remains valid for Node View compatibility.

**\[V2]** simulator.py is no longer the primary telemetry source for the main dashboard.

## chaos.py

* Maintains chaos registry in memory
* `apply\\\_overlay(raw\\\_metrics)` is the ONLY mutation point
* **MUST NOT generate baseline metrics**
* **MUST NOT import simulator.py**

**\[LEGACY]** This module remains the legacy overlay path.

**\[V2]** A new isolated network chaos service may be introduced separately for probe traffic. The legacy overlay pipeline must not be repurposed into the new probe pipeline.

## Probe telemetry modules \[V2]

* Probe collection must be isolated from the legacy node simulator
* Probe traffic must be generated as real network requests
* Packet Evidence must be derived from actual probe runs
* Packet Evidence must not depend on passive sniffing

## Pipeline (never reverse this)

### \[LEGACY] V1 pipeline

```text
simulator.py → baseline metrics → chaos.py overlay → display/storage
```

### \[V2] Probe pipeline

```text
probe.py → endpoint request → telemetry extraction → packet evidence → normalization → cache/storage → display
```

\---

# 5\. Host Safety — Non-Negotiable

Node-1 is strictly read-only. Forbidden on Node-1:

* CPU stress
* memory pressure
* network/DNS/firewall modification
* any chaos injection

Chaos operates ONLY on synthetic nodes via overlay metrics in the legacy path. The VM must never be intentionally destabilized.

**\[V2]** Real network chaos, if used, must be confined to isolated probe environments and must not modify host networking directly.

\---

# 6\. Unified Metrics Schema

Every metrics object from any node MUST match exactly in the legacy model:

```json
{
  "node\\\_id": "string",
  "timestamp": "ISO8601 UTC",
  "cpu": 0.0,
  "memory": 0.0,
  "disk": 0.0,
  "latency\\\_ms": 0.0,
  "packet\\\_loss\\\_pct": 0.0,
  "status": "green|yellow|red|gray"
}
```

Rules: no null fields, all values numeric, bounded (cpu/memory/disk: 0-100, latency\_ms: ≥0, packet\_loss\_pct: 0-100), no NaN, no negative percentages.

Display metrics always = `chaos.apply\\\_overlay(raw\\\_metrics)` in the legacy pipeline. Raw metrics never modified in-place.

## \[V2] Probe telemetry schema

All probe telemetry objects MUST be explainable and derived from real probe activity:

```json
{
  "probe\\\_id": "string",
  "endpoint": "string",
  "protocol": "icmp",
  "timestamp": "ISO8601 UTC",
  "latency\\\_ms": 0.0,
  "packet\\\_loss\\\_pct": 0.0,
  "jitter\\\_ms": 0.0,
  "availability\\\_pct": 0.0,
  "packet\\\_size\\\_bytes": 0,
  "src\\\_ip": "string",
  "dst\\\_ip": "string",
  "ttl": 0,
  "icmp\\\_seq": 0,
  "status": "green|yellow|red|gray"
}
```

### \[V2] Metric interpretation rules

The following values must remain directly explainable:

* **latency\_ms**: derived from observed round-trip time of probe packets
* **packet\_loss\_pct**: derived from unanswered probes within a defined window
* **jitter\_ms**: derived from variation in round-trip time across a window
* **availability\_pct**: derived from successful probes divided by total probes
* **packet\_size\_bytes**: derived from the actual probe packet size
* **src\_ip / dst\_ip**: derived from the real request path
* **ttl**: derived from the packet metadata or response metadata
* **icmp\_seq**: derived from the ICMP sequence number

No value may be generated by arbitrary randomization in the V2 telemetry path.

\---

# 7\. WebSocket Event Schemas

Backend pushes normalized events only — no full snapshots.

### metric\_update

```json
{"type": "metric\\\_update", "node\\\_id": "node-1", "cpu": 45.2, "memory": 62.1, "disk": 38.0, "latency\\\_ms": 12.0, "packet\\\_loss\\\_pct": 0.0, "status": "green", "timestamp": "..."}
```

### alert\_fired

```json
{"type": "alert\\\_fired", "alert\\\_id": "uuid", "node\\\_id": "node-1", "alert\\\_type": "cpu\\\_high", "message": "CPU at 82%", "timestamp": "..."}
```

### incident\_opened

```json
{"type": "incident\\\_opened", "incident\\\_id": "uuid", "title": "...", "timestamp": "..."}
```

### incident\_closed

```json
{"type": "incident\\\_closed", "incident\\\_id": "uuid", "timestamp": "..."}
```

### node\_status\_changed

```json
{"type": "node\\\_status\\\_changed", "node\\\_id": "node-2", "status": "red", "timestamp": "..."}
```

**\[V2] Probe event additions**

### probe\_metric\_update

```json
{"type": "probe\\\_metric\\\_update", "probe\\\_id": "probe-a", "endpoint": "8.8.8.8", "latency\\\_ms": 12.4, "packet\\\_loss\\\_pct": 0.0, "jitter\\\_ms": 1.2, "availability\\\_pct": 100, "status": "green", "timestamp": "..."}
```

### packet\_evidence

```json
{"type": "packet\\\_evidence", "probe\\\_id": "probe-a", "endpoint": "8.8.8.8", "protocol": "icmp", "src\\\_ip": "10.0.0.5", "dst\\\_ip": "8.8.8.8", "ttl": 117, "packet\\\_size\\\_bytes": 64, "icmp\\\_seq": 218, "rtt\\\_ms": 12.4, "timestamp": "..."}
```

### link\_status\_changed

```json
{"type": "link\\\_status\\\_changed", "link\\\_id": "link-a", "status": "red", "timestamp": "..."}
```

Zustand stores handle each event independently. No snapshot replacement.

**\[V2]** Node events remain for compatibility, and probe events are added alongside them.

\---

# 8\. Database Schema

### nodes

```sql
id VARCHAR PRIMARY KEY, name VARCHAR, type VARCHAR,
status VARCHAR, last\\\_seen TIMESTAMP, created\\\_at TIMESTAMP
```

### metrics

```sql
id SERIAL PRIMARY KEY, node\\\_id VARCHAR REFERENCES nodes(id),
timestamp TIMESTAMP, cpu FLOAT, memory FLOAT, disk FLOAT,
latency\\\_ms FLOAT, packet\\\_loss\\\_pct FLOAT, status VARCHAR
-- Index: (node\\\_id, timestamp)
-- Retention: delete rows older than 72h
```

### alerts

```sql
id UUID PRIMARY KEY, node\\\_id VARCHAR REFERENCES nodes(id),
incident\\\_id UUID REFERENCES incidents(id) NULL,
alert\\\_type VARCHAR, message VARCHAR,
fired\\\_at TIMESTAMP, resolved\\\_at TIMESTAMP NULL
```

### incidents

```sql
id UUID PRIMARY KEY, title VARCHAR, status VARCHAR,
opened\\\_at TIMESTAMP, closed\\\_at TIMESTAMP NULL
```

### chaos\_events

```sql
id UUID PRIMARY KEY, chaos\\\_type VARCHAR, node\\\_id VARCHAR,
started\\\_at TIMESTAMP, ended\\\_at TIMESTAMP NULL, config JSONB
```

## \[V2] Additional tables

### probes

```sql
id VARCHAR PRIMARY KEY,
name VARCHAR,
protocol VARCHAR,
endpoint VARCHAR,
status VARCHAR,
last\\\_seen TIMESTAMP,
created\\\_at TIMESTAMP
```

### links

```sql
id VARCHAR PRIMARY KEY,
probe\\\_id VARCHAR REFERENCES probes(id),
endpoint VARCHAR,
protocol VARCHAR,
status VARCHAR,
last\\\_seen TIMESTAMP,
created\\\_at TIMESTAMP
```

### probe\_metrics

```sql
id SERIAL PRIMARY KEY,
probe\\\_id VARCHAR REFERENCES probes(id),
link\\\_id VARCHAR REFERENCES links(id),
timestamp TIMESTAMP,
latency\\\_ms FLOAT,
packet\\\_loss\\\_pct FLOAT,
jitter\\\_ms FLOAT,
availability\\\_pct FLOAT,
packet\\\_size\\\_bytes INT,
src\\\_ip VARCHAR,
dst\\\_ip VARCHAR,
ttl INT,
icmp\\\_seq INT,
status VARCHAR
-- Index: (probe\\\_id, timestamp)
-- Index: (link\\\_id, timestamp)
```

### packet\_evidence

```sql
id UUID PRIMARY KEY,
probe\\\_id VARCHAR REFERENCES probes(id),
link\\\_id VARCHAR REFERENCES links(id),
protocol VARCHAR,
src\\\_ip VARCHAR,
dst\\\_ip VARCHAR,
ttl INT,
packet\\\_size\\\_bytes INT,
icmp\\\_seq INT,
rtt\\\_ms FLOAT,
timestamp TIMESTAMP
```

### \[V2] Storage rule

Redis stores the latest probe metric and latest packet evidence per probe or link.

PostgreSQL stores history, aggregation inputs, incidents, and packet evidence history.

\---

# 9\. Alert \& Incident Rules

### Alert Thresholds

|Condition|Alert Type|
|-|-|
|CPU > 80%|cpu\_high|
|Latency > 500ms|latency\_spike|
|No heartbeat 15s|heartbeat\_timeout|

### Deduplication

* Key: `(node\\\_id, alert\\\_type)`
* Cooldown: 60 seconds
* During cooldown: no DB insert, no WebSocket broadcast

### Incident Lifecycle

* Opens on first non-deduplicated alert (one open incident per node max)
* Closes only after 3 consecutive clean evaluations
* Timeline events are append-only

### Node Status Recovery

* Node returns to `green` only after 3 consecutive healthy evaluations

## \[V2] Probe and link alert rules

### Probe thresholds

|Condition|Alert Type|
|-|-|
|Packet loss above configured threshold|probe\_packet\_loss\_high|
|Latency above configured threshold|probe\_latency\_high|
|Availability below configured threshold|probe\_availability\_low|

### Deduplication

* Key: `(probe\\\_id, alert\\\_type)` or `(link\\\_id, alert\\\_type)`
* Cooldown: 60 seconds
* During cooldown: no DB insert, no WebSocket broadcast

### Incident lifecycle

* Opens on first non-deduplicated probe or link alert
* Closes only after 3 consecutive clean evaluations
* Timeline events are append-only

### Recovery rule

* A probe or link returns to `green` only after 3 consecutive healthy evaluations

### Metric interpretation rule

All thresholds must act on real telemetry values only, not on synthetic placeholders.

\---

# 10\. Chaos Injection

### Types

|Type|Effect|
|-|-|
|latency\_spike|latency\_ms += random(200, 800)|
|packet\_loss|drop every 5th heartbeat|
|cpu\_spike|cpu += injected\_value (cap 100)|
|db\_exhaustion|simulated alert only, no real DB harm|
|cache\_unavailable|simulated alert only, no real Redis harm|
|recover\_all|clear entire chaos registry|

### Registry pattern

```python
active\\\_chaos = {"node-2": \\\["latency\\\_spike"]}
```

`recover\\\_all()` clears registry, restores overlays, preserves historical chaos\_events rows.

## \[V2] Isolated network chaos

The V2 chaos model must not mutate the host network directly.

### Supported V2 approach

* isolated Docker network
* isolated probe container
* `tc netem` applied only inside the isolated environment
* probe traffic toward endpoints is affected within the demo sandbox only

### V2 supported effects

|Type|Effect|
|-|-|
|latency\_spike|add controlled delay to probe traffic inside the isolated environment|
|packet\_loss|introduce controlled packet loss inside the isolated environment|
|jitter\_spike|increase RTT variance inside the isolated environment|
|recover\_all|remove the network impairment and clear the registry|

### V2 rules

* Packet evidence must remain explainable
* Chaos must remain visible in the dashboard
* Host networking must never be modified directly
* The host machine must not be destabilized
* Chaos must be isolated from unrelated services

**\[SUPERSEDED]** The legacy overlay-only chaos path remains documented for historical compatibility.

\---

# 11\. Scheduler (Single Instance)

APScheduler responsibilities:

* 5s: metrics collection
* 1s: WebSocket metric push
* 15s: heartbeat evaluation
* periodic: alert evaluation, incident evaluation, retention cleanup (72h)

**One APScheduler only. No child schedulers. No recursive scheduling.**

## \[V2] Probe scheduling

* 5s: probe collection is the default cadence
* 15s / 30s / 60s / 180s: supported aggregation windows for historical views
* Probe collection values are aggregated into historical buckets for dashboard display and analysis

\---

# 12\. Resource Budget

|Resource|Limit|
|-|-|
|VM|GCP e2-micro|
|RAM|1GB|
|Disk|30GB|
|Max nodes|3|
|Max WebSocket clients|5|
|Metrics retention|72 hours|

Docker Compose services: `nginx`, `frontend`, `backend`, `redis`, `postgres`

All containers MUST use log rotation:

```yaml
logging:
  options:
    max-size: "10m"
    max-file: "3"
```

Startup order: postgres → redis → backend → frontend → nginx

## \[V2] Capacity note

No additional infrastructure services should be introduced for the V2 migration unless explicitly flagged as a new architectural dependency.

\---

# 13\. API Response Envelope

Success: `{"success": true, "data": {}}`
Error: `{"success": false, "error": {"code": "string", "message": "string"}}`

Node IDs are locked: `node-1`, `node-2`, `node-3`

## \[V2] API additions

### Probe list

* List configured probes
* Show probe health and latest telemetry

### Link list

* List configured links
* Show link health and latest telemetry

### Packet evidence

* Return the latest packet evidence per probe or link
* Return historical packet evidence by time window

### Aggregated telemetry

* Return metrics grouped by 15s / 30s / 60s / 180s windows

All V2 API responses must continue to use the same success/error envelope.

\---

# 14\. Frontend Rules

* Zustand is the ONLY global state system (no Redux, no MobX)
* WebSocket disconnect: show degraded badge, keep dashboard mounted, bounded reconnect retry
* Charts render bounded data only, support realtime updates
* Max 4 major dashboard panels

## \[V2] Frontend behavior

* Default view is Link View
* Node View remains available as a legacy compatibility view
* Packet Evidence must be visible in the UI
* The UI must show a clear explanation of each metric value and its origin
* Historical views must support 15s / 30s / 60s / 180s aggregation windows
* The dashboard must make it obvious when a value is real telemetry versus a legacy compatibility metric

\---

# 15\. File Structure

```text
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
│   ├── redis\\\_client.py
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

## \[V2] File mapping

* `backend/services/simulator.py` remains for legacy node simulation
* `backend/services/chaos.py` remains for legacy overlay chaos
* New V2 telemetry logic should be added as separate modules rather than by overloading simulator.py
* New V2 packet evidence logic should be separated from legacy node metrics
* New V2 link and probe services should be added without breaking the existing folder discipline

\---

# 16\. \[V2] Migration Contract

This section defines how V1 and V2 coexist during the migration.

## V1 behavior

* V1 Node View remains valid
* V1 synthetic nodes remain valid for compatibility
* V1 overlay chaos remains valid only for legacy demo paths

## V2 behavior

* V2 Link View is the default operational view
* V2 telemetry must originate from probes
* V2 telemetry must be explainable and traceable
* V2 packet evidence must represent actual probe-generated packets
* V2 chaos must be isolated from the host network

## Coexistence rule

* V1 and V2 may coexist in the codebase
* V1 and V2 must not be mixed inside a single data path
* A dashboard view must clearly indicate whether it is using legacy node metrics or probe telemetry

## Removal rule

* Nothing in V1 should be removed unless explicitly marked \[REMOVE IN V2]
* All removals must be justified with a migration note

\---

# 17\. \[V2] Acceptance Criteria

The migration is complete when all of the following are true:

1. Legacy Node View still works.
2. Link View is the default dashboard mode.
3. Three real endpoints are monitored by probes.
4. All telemetry values are explainable from actual probe activity.
5. Packet Evidence is visible in the dashboard.
6. Historical aggregation works for 15s / 30s / 60s / 180s windows.
7. Alerts and incidents still work end to end.
8. Chaos works in an isolated environment without modifying host networking.
9. Redis still supports latest-value caching.
10. PostgreSQL still stores history and telemetry lineage.
11. The codebase remains within the existing stack and file structure.
12. The migration can be demonstrated in a recorded video.

\---

# 18\. \[V2] Summary of non-goals

The following are not required for V2:

* Prometheus
* Grafana
* Kafka
* OpenTelemetry
* Loki
* Tempo
* Kubernetes
* host-level packet capture
* passive sniffing
* new auth system
* new deployment topology

These are intentionally out of scope unless explicitly reintroduced as a new approved dependency.



