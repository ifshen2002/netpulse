# Critical Use Case Design — Chaos → Alert → Incident → Recovery

## Design Overview

The alert pipeline is the most architecturally significant flow in NetPulse. It spans all four system layers (probe → evaluation → incident management → notification delivery) and exercises three cross-cutting concerns: real-time WebSocket push, stateful evaluation, and multi-tenant data isolation.

## Design Pattern: Observer + State Machine

**Observer pattern** connects the backend alert engine to the React frontend via WebSocket broadcast. The `ConnectionManager` acts as the subject; each connected browser tab is an observer. Events are filtered by `project_id` (metrics/alerts/incidents) or `user_id` (notifications) before delivery.

**State Machine pattern** governs two lifecycles:

1. **Alert Rule State** (per endpoint, per rule): `ok → firing → (cooldown) → ok`. The evaluator maintains in-memory dictionaries for cooldowns, clean-evaluation streaks, and active rule states. A rule in `firing` state will not re-fire until the condition clears (condition persists = no spam).

2. **Incident State**: `open → (alerts append) → closed`. A single incident groups all alerts for a given endpoint. It opens on the first non-deduplicated alert and closes after 3 consecutive clean evaluations for all rules on that endpoint.

## Class Responsibilities

### ProbeRunner (`services/probe.py`)
Executes ICMP ping subprocess (`ping -c 1 -W 2 -- <target>`), parses output with regex into structured packet evidence. All telemetry originates here — no synthetic metric generation for V2 endpoints.

### AlertEvaluator (`services/alerting.py`)
Core evaluation engine. For each endpoint: loads enabled `alert_rules` from DB, evaluates current metric against rule threshold, checks cooldown, fires alert if needed. State dictionaries (`_endpoint_cooldowns`, `_active_rule_state`, `_endpoint_clean_streaks`) track per-endpoint evaluation history in memory.

### IncidentManager (same file)
Creates incidents on first alert, appends subsequent alerts to existing incident, resolves after clean streak. Maintains `_endpoint_open_incidents` dict mapping endpoint_id → incident_id.

### NotificationService (`services/notifications.py`)
`match_and_deliver()`: queries `notification_subscriptions` table for matching subscribers (project + resource_type + severity), inserts `in_app_notifications` rows, calls `broadcast_notification()` with `user_id` filter.

### ConnectionManager (`routers/websocket.py`)
Tracks WebSocket connections as `dict[WebSocket, {user_id, project_id}]`. `broadcast(message, project_id, user_id)` delivers only to matching connections. Legacy V1 node events use no filter (global broadcast for synthetic data).

### Scheduler (`scheduler.py`)
Single APScheduler instance running 10 jobs at fixed intervals: endpoint collection (5s), metrics push (1s), alert evaluation (5s), heartbeat check (15s), retention cleanup (hourly), project_id backfill (30s).

## Sequence: Full Chaos → Recovery Lifecycle

### Phase 1: Chaos Injection
1. Editor sends `POST /api/chaos/network/inject` with `{endpoint_id, chaos_type: "latency", value: 200}`
2. Router verifies editor permission (`require_project_editor`) and endpoint belongs to project (`_verify_endpoint_project`)
3. `services/netchaos.py:inject()` resolves target_host → IP, applies `tc qdisc add netem delay 200ms` via u32 filter on the target IP
4. In-memory state records active chaos session; audit log written

### Phase 2: Probe Detects Anomaly
1. Scheduler runs `_collect_endpoints()` every 5 seconds
2. For each enabled endpoint: `run_probe()` executes ICMP ping, parses output
3. `tc netem` adds 200ms delay → ping RTT ~215ms (normal ~12ms)
4. Results stored: `packet_evidence` row + `probe_metrics` row (with project_id) + Redis cache
5. `_push_endpoint_metrics()` broadcasts `endpoint_metric_update` to WebSocket clients in that project

### Phase 3: Alert Evaluation
1. Scheduler runs `_evaluate_endpoint_alerts()` every 5 seconds
2. For each endpoint: loads `alert_rules`, evaluates current Redis-cached metric against threshold
3. Rule "latency > 100ms" matched → severity "warning"
4. Cooldown check passes → `_fire_endpoint_alert()` called
5. `_create_endpoint_incident()`: inserts incident row, broadcasts `incident_opened` (project_id scoped)
6. Alert row inserted with incident_id linkage
7. `alert_fired` broadcast (project_id scoped)
8. `match_and_deliver()`: finds subscribers, creates notification rows, broadcasts `notification_created` (user_id scoped)

### Phase 4: Viewer Response
1. Viewer's NotificationCenter shows unread count badge
2. Viewer clicks notification → `PATCH /notifications/{id}/read` → status = "read"
3. Viewer clicks "Acknowledge" → `PATCH /notifications/{id}/acknowledge` → status = "acknowledged"
4. Dashboard endpoint card shows yellow/red status with degraded metrics

### Phase 5: Recovery
1. Editor sends `POST /api/chaos/network/recover {endpoint_id}`
2. `services/netchaos.py:recover()` clears `tc qdisc del dev eth0 root`
3. Next probe cycle shows normal RTT (~12ms)
4. `evaluate_endpoint()` sees condition cleared → increments clean streak counter
5. After 3 consecutive clean evaluations → `_resolve_endpoint_incident()`: closes incident, resolves all alerts, clears state
6. `incident_closed` broadcast (project_id scoped)
7. `_resolve_notifications_for_incident()`: sets all linked notification statuses to "resolved"
8. Dashboard returns to green

## Data Model (Key Tables in This Flow)

| Table | Key Columns | Role in Flow |
|---|---|---|
| `endpoints` | id, target_host, status, last_seen, project_id | Source of truth for what to probe |
| `alert_rules` | id, metric, operator, threshold, severity, project_id | Configurable thresholds |
| `packet_evidence` | id, endpoint_id, rtt_ms, ttl, timestamp, project_id | Raw probe output, immutable |
| `probe_metrics` | endpoint_id, latency_ms, packet_loss_pct, availability_pct, project_id | Aggregated window metrics |
| `alerts` | id, endpoint_id, incident_id, alert_type, message, fired_at, resolved_at | Individual alert records |
| `incidents` | id, endpoint_id, title, status, opened_at, closed_at | Groups related alerts |
| `notification_subscriptions` | id, user_id, project_id, resource_type, severity | User preferences |
| `in_app_notifications` | id, user_id, alert_id, incident_id, title, body, severity, status | Delivered notifications |
| `audit_logs` | id, actor_user_id, action, resource_type, resource_id, project_id | Immutable trail |
