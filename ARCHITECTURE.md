# ARCHITECTURE.md — NetPulse System Design

> Highest-priority source of truth. All other documents defer to this one.
> Implementation contracts are included here.

---

# PART I — V3 PLATFORM ARCHITECTURE (PRIMARY)

## 1. System definition

NetPulse is a multi-tenant production observability platform. It registers servers and endpoints, executes health and reachability checks on a fixed cadence, collects evidence, detects abnormal conditions, notifies responsible people through in-app notifications, and coordinates incident response.

The current deployment is a single-instance demonstration using the platform runtime itself as a managed server, with public endpoints demonstrating outbound link health. The production target is identical in architecture, differing only in scale (more targets, more users) and deployment hardening (TLS, secrets management, backups).

### 1.1 Production enrollment flow (design contract, not yet implemented)

Enrolling a production server requires establishing trust:

1. Operator creates an enrollment token from the NetPulse dashboard (scoped to a project).
2. Token is deployed to the target server via config management, orchestration, or manual bootstrap.
3. A lightweight agent (future) presents the token to `POST /api/enroll`, exchanges it for a credential, and begins reporting.
4. The platform rejects anonymous metric submissions — every data point is traceable to a registered credential.

Until agents are implemented, the platform runtime performs checks directly. No remote shell access or arbitrary command execution is ever granted.

## 2. Tenancy and identity model

### 2.1 Entities

| Entity | Purpose |
|---|---|
| User | Registered identity with email, display name, password hash |
| Organization | Top-level tenancy boundary; groups projects |
| Project | Resource scope for targets, checks, alerts, incidents |
| Membership | User → Project role binding (viewer / editor) |
| AuthSession | Opaque bearer token, SHA-256 hashed in DB |
| AccessRequest | User-submitted ticket requesting project access |
| AuditLog | Immutable record of every privileged action |
| NotificationSubscription | User preference for alert delivery |
| InAppNotification | Delivered notification with read/ack/resolve lifecycle |

### 2.2 Roles

| Role | Access |
|---|---|
| `platform_admin` | Manage users, organizations, projects, access requests, role grants, platform policy. Implicit read access to everything. |
| `viewer` | Read-only: dashboards, configuration, alerts, incidents, evidence, audit logs. No mutations. |
| `editor` | Viewer + manage project resources: create/update/delete targets, configure alert rules, manage lab chaos, acknowledge incidents. All mutations audited. |

### 2.3 Access request workflow

```
User registers → browses project catalog → submits access request (project + role + reason)
  → platform_admin reviews → approves or rejects
    → approved: membership created with requested role
    → rejected: request closed, no membership created
  → audit log records every step
```

### 2.4 Authentication contract

- Passwords: salted scrypt hash (N=16384, r=8, p=1), stored as `scrypt$N$r$p$salt_b64$digest_b64`.
- Sessions: 256-bit opaque token (`secrets.token_urlsafe(48)`), SHA-256 hash stored in `auth_sessions.token_hash`, expiry default 7 days.
- Every authenticated request carries `Authorization: Bearer <token>`.
- Project context: `X-Project-ID` header from the browser.
- Logout revokes the session (sets `revoked_at`).
- First registered user becomes bootstrap `platform_admin`.

## 3. Notification system

### 3.1 Subscription model

Users subscribe to alerts by:
- Project (required)
- Resource type (endpoint, node — or ANY)
- Severity (warning, critical — or ANY)

When an alert fires, the platform evaluates all subscriptions for that project. Every matching subscriber receives an in-app notification.

### 3.2 Notification lifecycle

```
unread → read → acknowledged → resolved
```

- `unread`: delivered, not yet seen
- `read`: user has viewed the notification
- `acknowledged`: user has explicitly acknowledged (for critical alerts)
- `resolved`: underlying alert/incident is resolved, notification auto-resolved

### 3.3 Delivery

Notifications are delivered via WebSocket (`notification_created` event) for real-time display and stored in PostgreSQL for persistence. The notification center in the frontend polls on mount and receives live updates.

External channels (email, SMS, webhook) are out of scope for the first platform release.

## 4. Authorization enforcement

### 4.1 Route categories

| Category | Required permission |
|---|---|
| Registration, login, logout, health | None (public) |
| Read routes (GET endpoints, alerts, incidents, alert-rules, nodes, metrics, audit-logs) | Authenticated + project member |
| Mutation routes (POST/PUT/PATCH/DELETE on resources) | Authenticated + project editor |
| Admin routes (user/org/project/access-request management) | platform_admin |
| WebSocket | Authenticated + project member |

### 4.2 Data isolation

Every query for monitoring resources MUST filter by `project_id` from the `X-Project-ID` header. No cross-project data leakage. `platform_admin` may optionally query across projects for audit purposes.

### 4.3 Audit requirement

Every approval, role change, resource creation, resource deletion, configuration change, and destructive operation creates an AuditLog record with: actor, action, resource type, resource ID, organization, project, details, timestamp.

## 5. API contracts (V3 additions)

All APIs use the standard envelope:
```json
{"success": true, "data": {}}
{"success": false, "error": {"code": "string", "message": "string"}}
```

### 5.1 Identity endpoints (implemented)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | None | Create user; first user = platform_admin |
| POST | `/api/auth/login` | None | Create session, return token |
| POST | `/api/auth/logout` | User | Revoke session |
| GET | `/api/auth/me` | User | Current user info |
| POST | `/api/admin/organizations` | Admin | Create organization |
| POST | `/api/admin/projects` | Admin | Create project |
| GET | `/api/projects` | User | List my projects |
| GET | `/api/projects/catalog` | User | All projects (for requesting access) |
| POST | `/api/access-requests` | User | Submit access request |
| GET | `/api/access-requests/mine` | User | My access requests |
| GET | `/api/admin/access-requests` | Admin | Pending requests |
| POST | `/api/admin/access-requests/{id}/review` | Admin | Approve/reject |
| GET | `/api/audit-logs` | User | Audit trail (scoped) |

### 5.2 Notification endpoints (to implement)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/notifications` | User | List my notifications (paginated, filterable by status) |
| PATCH | `/api/notifications/{id}/read` | User | Mark as read |
| PATCH | `/api/notifications/{id}/acknowledge` | User | Acknowledge |
| GET | `/api/subscriptions` | User | List my subscriptions |
| POST | `/api/subscriptions` | User | Create subscription |
| DELETE | `/api/subscriptions/{id}` | User | Remove subscription |

### 5.3 WebSocket events (V3 additions)

#### notification_created
```json
{"type": "notification_created", "notification_id": "uuid", "title": "...", "body": "...", "severity": "critical", "alert_id": "uuid", "incident_id": "uuid", "project_id": "uuid", "created_at": "..."}
```

## 6. Database schema (V3 additions)

### users
```sql
id VARCHAR PRIMARY KEY, email VARCHAR UNIQUE NOT NULL,
password_hash VARCHAR NOT NULL, display_name VARCHAR NOT NULL,
is_platform_admin BOOLEAN DEFAULT FALSE, is_active BOOLEAN DEFAULT TRUE,
created_at TIMESTAMPTZ
```

### organizations
```sql
id VARCHAR PRIMARY KEY, name VARCHAR UNIQUE NOT NULL,
created_by VARCHAR REFERENCES users(id), created_at TIMESTAMPTZ
```

### projects
```sql
id VARCHAR PRIMARY KEY, organization_id VARCHAR REFERENCES organizations(id),
name VARCHAR NOT NULL, created_at TIMESTAMPTZ,
UNIQUE (organization_id, name)
```

### memberships
```sql
id VARCHAR PRIMARY KEY, user_id VARCHAR REFERENCES users(id),
organization_id VARCHAR REFERENCES organizations(id),
project_id VARCHAR REFERENCES projects(id),
role VARCHAR NOT NULL CHECK (role IN ('viewer', 'editor')),
created_at TIMESTAMPTZ,
UNIQUE (user_id, project_id)
```

### auth_sessions
```sql
id VARCHAR PRIMARY KEY, user_id VARCHAR REFERENCES users(id),
token_hash VARCHAR UNIQUE NOT NULL, expires_at TIMESTAMPTZ,
revoked_at TIMESTAMPTZ NULL, created_at TIMESTAMPTZ
```

### access_requests
```sql
id VARCHAR PRIMARY KEY, user_id VARCHAR REFERENCES users(id),
organization_id VARCHAR REFERENCES organizations(id),
project_id VARCHAR REFERENCES projects(id),
requested_role VARCHAR NOT NULL CHECK (role IN ('viewer', 'editor')),
reason TEXT, status VARCHAR NOT NULL CHECK (status IN ('pending','approved','rejected')),
reviewer_id VARCHAR REFERENCES users(id), review_note TEXT,
created_at TIMESTAMPTZ, reviewed_at TIMESTAMPTZ NULL
-- Partial unique index: (user_id, project_id) WHERE status = 'pending'
```

### audit_logs
```sql
id VARCHAR PRIMARY KEY, actor_user_id VARCHAR REFERENCES users(id),
organization_id VARCHAR, project_id VARCHAR,
action VARCHAR NOT NULL, resource_type VARCHAR NOT NULL,
resource_id VARCHAR, details JSONB DEFAULT '{}',
created_at TIMESTAMPTZ
-- Index: (project_id, created_at)
```

### notification_subscriptions
```sql
id VARCHAR PRIMARY KEY, user_id VARCHAR REFERENCES users(id),
project_id VARCHAR REFERENCES projects(id) NOT NULL,
resource_type VARCHAR,  -- 'probe','endpoint','node', or NULL = all
severity VARCHAR,         -- 'warning','critical', or NULL = all
enabled BOOLEAN DEFAULT TRUE,
created_at TIMESTAMPTZ,
UNIQUE (user_id, project_id, resource_type, severity)
```

### in_app_notifications
```sql
id VARCHAR PRIMARY KEY, user_id VARCHAR REFERENCES users(id),
alert_id VARCHAR REFERENCES alerts(id),
incident_id VARCHAR REFERENCES incidents(id),
project_id VARCHAR REFERENCES projects(id),
title VARCHAR NOT NULL, body TEXT,
severity VARCHAR NOT NULL CHECK (severity IN ('warning','critical')),
status VARCHAR NOT NULL DEFAULT 'unread'
  CHECK (status IN ('unread','read','acknowledged','resolved')),
created_at TIMESTAMPTZ, read_at TIMESTAMPTZ NULL,
acknowledged_at TIMESTAMPTZ NULL, resolved_at TIMESTAMPTZ NULL
-- Index: (user_id, status, created_at)
```

## 7. Production deployment topology

```
Browser → HTTPS (TLS) → Nginx → /api  → backend:8000
                                  /ws   → backend:8000
                                  /     → frontend:3000

Backend: FastAPI monolith
  - Identity & auth (services/auth.py, routers/auth.py)
  - Notification engine (services/notifications.py, routers/notifications.py)
  - Monitoring (services/monitoring.py, services/probe.py)
  - Alerting (services/alerting.py)
  - Incident management (services/incident.py)
  - Scheduling (scheduler.py — single APScheduler)
  - Data: PostgreSQL (source of truth) + Redis (latest-value cache)

Single-instance constraints:
  - In-memory WebSocket broadcast (not horizontally scalable)
  - In-process APScheduler (not redundant)
  - Replace with Redis Pub/Sub + external scheduler before scaling beyond 1 instance
```

## 8. Stack decisions (locked)

| Concern | Decision |
|---|---|
| Frontend | React + Recharts + TailwindCSS + Zustand |
| Backend | FastAPI monolith, layered internally |
| Realtime | WebSocket + in-memory broadcast manager |
| Cache | Redis, latest metrics + evidence per endpoint/node |
| DB | PostgreSQL, source of truth |
| Scheduler | Single APScheduler instance |
| Deployment | Docker Compose, single VM |
| Auth | Opaque session token (SHA-256 hashed), scrypt passwords |
| RBAC | platform_admin / viewer / editor, server-side enforcement |
| Notifications | In-app only for first release; WebSocket delivery + DB persistence |
| Simulated nodes | Legacy compatibility layer; labeled as lab/demo |
| Chaos model | [LEGACY] Overlay for V1 nodes; [V2] Isolated tc netem for endpoints; both labeled as lab |
| Incident model | One Incident contains many Alerts |
| Chaos recovery | Registry mechanism; recover_all clears registry |
| Endpoint/node status | green / yellow / red / gray |
| Metrics retention | 72 hours |
| Alert dedup | 60-second cooldown per (endpoint_id/node_id, alert_type) |
| Incident auto-close | 3 consecutive clean evaluations |
| Audit retention | Indefinite (compliance) |

---

# PART II — V2 ENDPOINT ARCHITECTURE (ACTIVE)

> [2026-08-04] Probes and links tables were merged into endpoints (migration 013). Endpoint is the single source of truth for monitoring targets.

## V2.1 Endpoint telemetry model

The system prefers real network evidence over synthetic metric generation. Every displayed metric must be traceable to actual probe activity.

### Endpoint schema
```
endpoints: id, name, target_host, source_ip, protocol, status, last_seen, enabled, project_id, created_at
```

### V2 Pipeline (never reverse)
```
probe.py → ICMP ping → packet_evidence → normalization → cache/storage → display
                                                                       ↓
                                                            alert_rules evaluation
                                                                       ↓
                                                            alerts → incidents → notifications
```

## V2.2 WebSocket events (active)

| Event | Fields |
|---|---|
| `endpoint_metric_update` | endpoint_id, endpoint, latency_ms, packet_loss_pct, availability_pct, status, timestamp |
| `packet_evidence` | evidence_id, endpoint_id, endpoint, protocol, src_ip, dst_ip, ttl, packet_size_bytes, icmp_seq, rtt_ms, timestamp, raw_output |
| `endpoint_status_changed` | endpoint_id, status, previous_status, timestamp |
| `alert_fired` | alert_id, incident_id, endpoint_id, alert_type, message, evidence_id, timestamp |
| `incident_opened` / `incident_closed` | incident_id, endpoint_id, title, timestamp |

## V2.3 Database tables

`endpoints`, `probe_metrics` (historical name), `packet_evidence`, `alert_rules`, `alerts`, `incidents`

All carry `project_id` for tenant isolation. Scheduler writes `project_id` on every INSERT. `services/auth.py:project_clause()` provides asyncpg-safe filtering across all routers.

## V2.4 Alert evaluation

Rule-based stateful evaluation via `alert_rules` table — no legacy hardcoded thresholds. Rules define `metric`, `operator`, `threshold`, `severity`. Per-endpoint state-based: condition persists → no re-fire; resolves → rule alert resolved; incident closes when ALL rules for the endpoint clear.

Dedup key: `(endpoint_id, rule_id)`, cooldown 60s, recovery streak 3.

## V2.5 Isolated network chaos (lab feature)

- `tc netem` inside container, u32 filter on destination IP
- One active injection at a time
- Value bounds: latency 10-500ms, loss 1-50%
- `cap_add: NET_ADMIN` on backend container
- Must be visually separated from production telemetry

---

# PART III — V1 NODE ARCHITECTURE (LEGACY COMPATIBILITY)

> V1 Node View remains operational but is now legacy. Node-2 and Node-3 are synthetic/demo only.

## V3.1 Legacy unified metrics schema
```json
{
  "node_id": "string", "timestamp": "ISO8601 UTC",
  "cpu": 0.0, "memory": 0.0, "disk": 0.0,
  "latency_ms": 0.0, "packet_loss_pct": 0.0,
  "status": "green|yellow|red|gray"
}
```

## V3.2 Legacy pipeline
```
simulator.py → baseline metrics → chaos.py overlay → display/storage
```

## V3.3 Legacy alert thresholds

| Condition | Alert Type |
|---|---|
| CPU > 80% | cpu_high |
| Latency > 500ms | latency_spike |
| No heartbeat 15s | heartbeat_timeout |

## V3.4 Host safety (non-negotiable)

Node-1 is strictly read-only. Chaos operates ONLY on synthetic nodes via overlay in the legacy path, or on isolated probe containers via tc netem in the V2 path. The host VM must never be intentionally destabilized.

---

# PART IV — CROSS-CUTTING RULES

## File structure

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
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── models/
│   │   └── __init__.py
│   ├── schemas/
│   │   └── __init__.py
│   ├── routers/
│   │   ├── auth.py          (identity, access requests, audit)
│   │   ├── notifications.py (subscriptions, notification CRUD)
│   │   ├── nodes.py         (V1 legacy)
│   │   ├── metrics.py       (V1 legacy)
│   │   ├── alerts.py
│   │   ├── alert_rules.py
│   │   ├── incidents.py
│   │   ├── chaos.py         (V1 legacy)
│   │   ├── netchaos.py      (V2 lab)
│   │   ├── endpoints.py
│   │   └── websocket.py
│   ├── services/
│   │   ├── auth.py          (password hashing, sessions, RBAC, audit)
│   │   ├── notifications.py (subscription matching, delivery)
│   │   ├── monitoring.py
│   │   ├── simulator.py
│   │   ├── chaos.py
│   │   ├── alerting.py
│   │   ├── incident.py
│   │   ├── probe.py
│   │   ├── netchaos.py
│   │   └── normalization.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── websocket/
│       └── e2e/
│
├── frontend/
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       ├── store/
│       │   ├── metricsStore.js
│       │   └── authStore.js
│       ├── hooks/
│       │   └── useWebSocket.js
│       ├── lib/
│       │   ├── api.js
│       │   └── time.js
│       └── components/
│           ├── AuthPage.jsx
│           ├── AccessConsole.jsx
│           ├── NotificationCenter.jsx
│           ├── SubscriptionManager.jsx
│           ├── ViewSwitcher.jsx
│           ├── SummaryBar.jsx
│           ├── EndpointCard.jsx
│           ├── CreateEndpointButton.jsx
│           ├── ProbeTelemetry.jsx
│           ├── PacketEvidencePanel.jsx
│           ├── EvidenceInspector.jsx
│           ├── NetworkChaosPanel.jsx
│           ├── AlertRulesManager.jsx
│           ├── AlertBanner.jsx
│           ├── IncidentTimeline.jsx
│           ├── NodeCard.jsx
│           ├── MetricsChart.jsx
│           ├── ChaosPanel.jsx
│           ├── NodeControls.jsx
│           └── ErrorBoundary.jsx
│
├── nginx/
│   └── nginx.conf
│
└── .github/
    └── workflows/
        └── ci.yml
```

**Folder discipline: max 5 items per folder level. Keep nesting shallow.**

## Resource budget

| Resource | Limit |
|---|---|
| VM | GCP e2-micro |
| RAM | 1 GB |
| Disk | 30 GB |
| Max WebSocket clients | 5 (demo) |
| Metrics retention | 72 hours |
| Audit log retention | Indefinite |

## Migration safety

Identity tables were introduced before telemetry-table ownership columns. During this interim state, identity and administrative APIs require authentication, while the project-scoping migration is in progress. The nullable `project_id` columns with bootstrap-project backfill are a compatibility bridge; they will become NOT NULL after all APIs enforce the project context.

## V1+V2 coexistence rule

- V1 and V2 may coexist in the codebase.
- V1 and V2 must not be mixed inside a single data path.
- A dashboard view must clearly indicate whether it is using legacy node metrics or probe telemetry.
- Lab/demo features (chaos, synthetic nodes) must be visually separated from production monitoring.

## API response envelope (all versions)

Success: `{"success": true, "data": {}}`
Error: `{"success": false, "error": {"code": "string", "message": "string"}}`

## Frontend rules

- Zustand is the ONLY global state system
- WebSocket disconnect: show degraded badge, keep dashboard mounted, bounded reconnect retry
- Charts render bounded data only, support realtime updates
- Max 4 major dashboard panels
- Zustand selectors MUST NOT create new object/array references (use module-level frozen constants)
- Default view is Link View; Node View is legacy compatibility
- Lab features (chaos, synthetic nodes) visually separated from production

## Scheduler (single instance)

Responsibilities:
- 5s: metrics/probe collection
- 1s: WebSocket push
- 15s: heartbeat evaluation
- 5s: alert evaluation
- On alert fire: notification delivery (match subscriptions, create notifications)
- Periodic: retention cleanup (72h metrics), incident evaluation

**One APScheduler only. No child schedulers. No recursive scheduling.**
