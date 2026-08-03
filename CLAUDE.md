# NETPULSE — PRODUCTION OBSERVABILITY PLATFORM

## Product narrative

Production servers and cloud workloads run business continuously — often in numbers too large for manual inspection. A team might operate hundreds of instances across regions, each one capable of failing silently at 3 AM. When every minute of downtime costs revenue, operators cannot afford to discover outages from customer complaints.

NetPulse is a multi-tenant server and network observability platform built for this reality. Operators register their production assets, configure health and reachability checks, and let the platform collect evidence on a fixed cadence. When a check crosses a threshold, NetPulse detects the abnormal condition, notifies the right people through in-app notifications, and coordinates recovery through its incident lifecycle.

The current self-observation deployment is a cost-conscious demonstration of the same model: its local collector is one managed server and its public endpoints demonstrate outbound link health. It proves the platform works — but it must never be presented as equivalent to monitoring every production server.

### How production servers enroll

In a full production deployment, enrolling a server requires establishing cryptographic trust between the server and the platform:

1. An operator generates a per-server enrollment token from the NetPulse dashboard.
2. The token is deployed to the target server (via config management, orchestration, or manual bootstrap).
3. A lightweight agent on the server presents the token to the platform API, exchanges it for a short-lived client certificate or key, and begins reporting health metrics.
4. The platform verifies every metric submission against the registered credential; no anonymous data is accepted.

Until a later architecture revision introduces deployable agents, the platform runtime itself performs configured checks. The trust bootstrap flow is documented here as the intended production path, not as currently implemented code.

## Core concepts

`Organization → Project → Target / Check → Alert → Incident → Notification`

- An **Organization** groups projects, users, and billing scope.
- A **Project** scopes resources, policies, subscriptions, and incidents. Every monitored asset belongs to exactly one project.
- A **Target** is a business endpoint, server address, or cloud resource being checked.
- A **Check** is a configured probe (ICMP, TCP, HTTP, DNS) that executes against a target on a fixed interval.
- An **Alert** is generated from real collected evidence when a check crosses a configured threshold.
- An **Incident** opens on the first non-deduplicated alert and groups related alerts for coordinated response.
- A **Notification** is delivered in-app to each user who subscribes to alerts for that project, resource, and severity level.

## Access model

- Anyone may register and sign in, but starts with no project access.
- A user submits an access request (ticket) for a specific project, selecting a requested role.
- A `platform_admin` reviews pending requests and approves or rejects each one.
- `viewer` — read-only access to dashboards, configuration, alerts, incidents, evidence, and audit logs. Cannot modify anything.
- `editor` — may manage approved project resources: create/update/delete targets, configure alert rules, manage chaos tests (lab only), acknowledge incidents. All destructive or privileged actions are audited.
- `platform_admin` — manages users, organizations, projects, access requests, role grants, and platform-wide safety policy. Has implicit read access to everything.

## Alert subscriptions and notifications

- Any project member may subscribe to alerts by project, resource type, and severity level.
- When an alert fires, each matching subscriber receives an in-app notification.
- Notification lifecycle: `unread → read → acknowledged → resolved`.
- External messaging (email, SMS, webhook) is explicitly out of scope for the first platform release.
- Delivery attempts and user actions on notifications are auditable.

## Product boundary

Legacy synthetic nodes (Node-2, Node-3) and chaos injection are demonstration/lab features. They must be visually and logically separated from production telemetry. The production value is trustworthy server health, active reachability checks, alert delivery, and incident handling.

The platform runtime performs configured checks directly (no remote agent yet). Agent-based host metrics, multi-location probes, and production-network enrollment are deferred to a later architecture revision.

## Current implementation boundary

- The first registered user becomes the bootstrap `platform_admin` and gets a default organization and project.
- Authentication uses an opaque, high-entropy server-side session token; only its SHA-256 hash is stored in PostgreSQL. Logout revokes the session.
- Identity, projects, access requests, and audit records share the same PostgreSQL database as telemetry.
- All monitoring APIs and the WebSocket feed require authenticated project membership. Mutation routes require editor or admin permission.
- Existing monitoring resources have nullable `project_id` columns backfilled to the bootstrap project — a compatibility bridge, not the final steady state.
- In-app notifications and alert subscriptions are the next delivery milestone.

## Stack

FastAPI + PostgreSQL + Redis + React + Recharts + TailwindCSS + Zustand + Nginx + Docker Compose

## Target deployment

GCP e2-micro (1 GB RAM, 30 GB disk), single VM, Docker Compose. Production deployment adds TLS termination at the reverse proxy, environment-managed secrets, migration-on-release, backups, and health checks.

## Hard constraints

1. Architecture is locked. Do not change system boundaries, module responsibilities, DB schema shape, or WebSocket event schemas without flagging first.
2. Autonomous by default. Make decisions independently on function names, variable names, component structure, internal logic, file organization, small UI choices. Only flag the situations listed in DECISIONS.md.
3. File structure discipline. Max 5 items per folder level. Keep nesting shallow.

## Priority order (when documents conflict)

1. ARCHITECTURE.md
2. DECISIONS.md
3. SPRINT.md

## Demo target (not negotiable)

The system must be recordable as a video demonstration showing:

- Real probe telemetry updating in real time
- Packet evidence visible on dashboard
- Alert firing and incident opening
- Chaos injection visibly affecting dashboard
- Recovery restoring normal state
- A platform administrator approving a user access request
- A viewer observing dashboards (read-only)
- An editor adding a target
- An in-app notification delivered to a subscriber

## Session start protocol

Before ANY implementation, read in order:
1. `ARCHITECTURE.md`
2. `DECISIONS.md`
3. `SPRINT.md`

If any implementation conflicts with ARCHITECTURE.md: STOP and flag it.
