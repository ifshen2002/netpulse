# Use Case Design — NetPulse Observability Platform

## Actor Taxonomy

### Platform Admin
First user registered with `NETPULSE_ADMIN_EMAIL` env var (or first registrant in dev mode). Has implicit read access to everything.

**Capabilities:**
- Create/read organizations and projects
- Review pending access requests (approve/reject)
- View all audit logs across all projects
- Manage user memberships (implicitly, via access request approval)

### Editor
Project member with `editor` role. All mutations are audited.

**Capabilities:**
- Create, update, delete, enable/disable monitoring endpoints
- Create, update, delete, toggle alert rules
- Inject and recover network chaos on endpoints within their project
- Acknowledge incidents
- Subscribe to alerts

### Viewer
Project member with `viewer` role. Read-only across all monitoring surfaces.

**Capabilities:**
- View real-time endpoint metrics, packet evidence, and status
- View alerts, incidents, and incident timelines
- View audit logs (scoped to project)
- Subscribe to alerts
- Receive and acknowledge in-app notifications

### Unregistered User
No access to any project or monitoring data.

**Capabilities:**
- Register an account (minimum 12-character password)
- Login with existing credentials

---

## Core Use Cases (by priority)

### P0 — Foundation

**UC-01: User Registration & Login**
- Unregistered user submits email + password (min 12 chars) + display name
- Backend uses salted scrypt hashing (N=16384, r=8, p=1)
- On successful registration/login, backend issues an opaque 256-bit session token (SHA-256 hashed in DB)
- Frontend stores token and attaches `Authorization: Bearer <token>` to all API calls

**UC-02: Real-Time Telemetry Viewing**
- Scheduler collects ICMP ping probes against all enabled endpoints every 5 seconds
- Probe results → structured packet evidence → window aggregation → Redis cache
- Scheduler pushes metrics + packet evidence to WebSocket every 1 second, filtered by project_id
- Dashboard renders real-time charts (Recharts) updated via Zustand store

**UC-03: Alert Triggering & Incident Lifecycle**
- Alert engine evaluates each endpoint against configured `alert_rules` every 5 seconds
- When a rule condition is met and cooldown is clear: alert fires, incident opens (or appends to existing open incident)
- 3 consecutive clean evaluations → incident auto-closes
- All state transitions broadcast via WebSocket (scoped to project_id)

### P1 — Authorization

**UC-04: Access Request Workflow**
- Viewer/Editor submits request: target project + desired role + reason
- Platform admin reviews pending requests
- On approval: membership row created with requested role
- On rejection: request closed, no membership created
- Every step recorded in `audit_logs`

**UC-05: Monitoring Target Management**
- Editor creates endpoint: name, target_host (validated against SSRF blocklist), optional source_ip
- Endpoint is immediately eligible for probe collection
- Editor can update, delete, or toggle enable/disable

**UC-06: Alert Rule Configuration**
- Editor creates rule: name, metric (latency/packet_loss/availability), operator (>, <, >=, <=), threshold, severity (warning/critical)
- Rules evaluated per-endpoint, statefully (condition persists → no re-fire; resolves → rule clears)
- Dedup key: (endpoint_id, rule_id), cooldown 60s

### P2 — User Experience

**UC-07: Alert Subscription & Notification**
- User creates subscription: project + optional resource_type (endpoint/node) + optional severity (warning/critical)
- When alert fires, matching subscriptions generate `in_app_notifications` rows
- Notifications pushed via WebSocket filtered by user_id (no cross-user leakage)
- Lifecycle: unread → read → acknowledged → resolved

**UC-08: Audit Trail**
- Every approved/rejected access request, endpoint CRUD, alert rule mutation, chaos injection, configuration change creates an immutable `audit_logs` row
- Logs queryable by project, filterable by resource type, paginated (max 200)

### P3 — Demo/Lab

**UC-09: Network Chaos Injection (Lab)**
- Editor injects latency (10-500ms) or packet loss (1-50%) targeting a specific endpoint via `tc netem`
- Container uses prio qdisc + u32 filter to isolate chaos to target IP only
- Dashboard displays LAB badge on chaos panels, visually separated from production metrics
- Recovery clears tc rules and auto-resolves incidents
