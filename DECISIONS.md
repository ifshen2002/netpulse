# DECISIONS.md — AI Behavior Rules

> This file defines how Claude Code behaves during implementation.
> System design lives in ARCHITECTURE.md. Execution state lives in SPRINT.md.

---

## V3 Platform Decisions (2026-08)

1. Continue from the current codebase. Reuse FastAPI, PostgreSQL, Redis, Alembic, the real probe pipeline, alerts, incidents, React dashboard, and the existing auth foundation. Do not rewrite the project from scratch.

2. Authentication, multi-tenant authorization, project scoping, in-app notifications, and access-request workflow are approved architectural work. Deployable agents are deferred to a later architecture revision.

3. No data may be read, mutated, broadcast, or subscribed to without an authenticated principal and organization/project authorization — except registration, login, logout, and health check endpoints.

4. Role policy is fixed: `platform_admin` approves access and administers the platform; `viewer` is read-only; `editor` manages authorized project resources. Permission checks happen server-side, never only in the UI.

5. Alerts are evidence-driven. Synthetic alert injection and chaos remain a separately labeled lab/demo path and cannot create production-looking data.

6. In-app notifications are the first delivery channel. Their lifecycle is `unread → read → acknowledged → resolved`. Delivery attempts and user actions are auditable.

7. Do not add deployable agents in the current platform phases. Never add remote shell execution, arbitrary user-defined commands, or unrestricted private-address probing. Existing abnormal injection remains a clearly labeled editor-controlled demo capability.

8. Any production-scale replacement for in-memory scheduling or WebSocket broadcast requires an explicit architecture update and integration tests.

9. The identity migration is intentionally two-stage: (1) create and test users, sessions, projects, requests, and audit logs; (2) tenant-scope the existing monitoring resources and enforce roles across their APIs. Stage 1 is complete; stage 2 is in progress.

10. All monitoring APIs and the WebSocket feed require authenticated project membership. Read access is granted through any project membership; mutation routes require editor or admin permission.

11. The active project context is carried by `X-Project-ID` from the authenticated web client. APIs filter resources by that context. Absence is a compatibility fallback for single-project users only.

12. Lab/demo features (V1 synthetic nodes, chaos injection panels) must be visually and logically separated from production monitoring. They must not appear to be production data.

13. Notification subscriptions are per-user, per-project, with optional resource_type and severity filters. When an alert fires, every matching subscriber receives an in-app notification via WebSocket and DB persistence.

14. Every approval, role change, configuration change, resource deletion, and destructive action creates an immutable audit log record.

15. [2026-08-04] Endpoint is the single source of truth for monitoring targets. The `probes` and `links` tables were merged into `endpoints` (migration 013). No new table or field may duplicate endpoint identity data.

16. [2026-08-04] Alert evaluation uses ONLY the `alert_rules` table. No hardcoded legacy thresholds exist. If no rules are loaded, no alerts fire — the system stays silent rather than guessing.

17. [2026-08-04] All `project_id` filtering in SQL uses `project_clause()` from `services/auth.py`. The asyncpg-incompatible pattern `:project_id IS NULL OR col = :project_id` is banned. Python-side branching replaces SQL NULL-check patterns.

18. [2026-08-04] Every scheduler INSERT must include `project_id` from the parent record. A periodic backfill (30s) catches any NULL rows as a safety net, but the primary guarantee is correct writes.

---

## V2 Migration Principles (retained)

Real telemetry before visualizations.
Simplicity before resilience.
Complete the current step before starting the next step.
Evidence before metrics.
No hidden recovery.
Do not invent a source for a metric after defining the metric.
Do not mix legacy node telemetry and V2 probe telemetry in the same data path.
If a task can be completed cleanly without adding abstraction, fallback layers, retry chains, or defensive wrappers, prefer the simpler implementation.

Fixed Logic, Configurable Policy:
- Measurement logic (probe interval, metric formulas, packet evidence generation, alert evaluation logic, incident lifecycle, status classification) is FIXED and cannot be changed from the UI.
- Operational policy (alert thresholds, display windows, probe endpoints, chaos parameters) is CONFIGURABLE from the UI with sensible defaults.
- Users can change what thresholds trigger alerts but cannot change how the platform calculates telemetry.

---

## 1. Autonomy Model

Default: decide independently.

You may autonomously decide:
- function names, variable names, type hints
- component decomposition and internal file organization
- helper functions and utility abstractions
- error message wording
- small UI layout choices
- test structure within the testing layers defined in ARCHITECTURE.md
- which library import to use when multiple valid options exist

Stop and flag to the user only when:
- The metrics schema (ARCHITECTURE.md Part II) needs to change
- The WebSocket event schemas need to change
- A DB table structure needs to add/remove columns beyond the V3 plan
- A new infrastructure dependency would be added (new Docker service, new DB, new queue)
- The same error repeats 3 times with different fix attempts and none work
- A module boundary violation is required to make something work
- A V2 telemetry value cannot be explained from a concrete probe action or derived aggregation

---

## 2. Architecture Protection

ARCHITECTURE.md is locked. You MUST NOT:
- Change module responsibilities (simulator vs chaos boundary, probe pipeline order)
- Add Redis Pub/Sub, Celery, Prometheus, Kafka, or any new infrastructure service
- Change the overlay pipeline order
- Bypass the services layer for DB writes
- Add passive packet sniffing or host-level packet interception
- Mix legacy node metrics with V2 probe telemetry in a single pipeline
- Grant any role permissions beyond what is defined in ARCHITECTURE.md Section 2.2
- Allow unauthenticated access to any monitoring API or WebSocket

If an implementation path requires any of the above: stop, explain why, propose a simpler alternative.

---

## 3. Repetition Rule

First occurrence of a pattern: implement it.
Second occurrence: consider if abstraction helps.
Third occurrence: refactor into shared helper/utility — no exceptions.

Do not introduce abstraction early just because a future path might need it.

---

## 4. Failure Recovery Rule

If you hit a blocker:
- Attempt 1: try the obvious fix
- Attempt 2: investigate root cause carefully
- Attempt 3: STOP — do not attempt a third variation. Explain the problem clearly.

Do not stack fallback layers. Do not hide errors with broad try/except. Do not add retry chains, recovery managers, or shadow fallback behaviors unless ARCHITECTURE.md explicitly requires them.

---

## 5. Code Quality Rules

- All timestamps: ISO8601 UTC
- No null metric fields
- No hidden mutable global state
- No silent fallback behavior
- Logs must include timestamps and source module
- Do not spam logs on every scheduler tick
- Prefer explicit code over magic abstractions
- Zustand selectors MUST NOT create new object/array references (use module-level frozen constants: `EMPTY_ARR`, `EMPTY_OBJ`)
- Every telemetry value must be explainable from a concrete probe action or a clearly stated aggregation window
- Permission checks happen server-side; never rely on UI-only gating
- Do not log sensitive values (passwords, tokens, session secrets)

---

## 6. Testing Philosophy

Tests exist to guarantee correctness and support the demo, not to inflate coverage numbers.

Priority:
1. Unit tests for alert evaluation, chaos overlay, incident lifecycle, metrics normalization, auth (password hashing, session creation, RBAC)
2. Integration tests for DB + Redis + API interaction, auth flows, cross-project isolation
3. WebSocket tests (explicit timeout, clean teardown, no infinite listeners)
4. Coverage report as a bonus

All tests must terminate cleanly and run in CI without manual steps.

Key test scenarios for V3:
- Viewer cannot mutate resources
- Editor can mutate within their project
- Project A cannot read Project B data
- Unauthenticated requests are rejected with 401
- Access request workflow: submit → approve → membership created
- Notification delivery on alert fire

---

## 7. Deployment Philosophy

Docker Compose is the only deployment topology. No Kubernetes, no Swarm.

CI/CD pipeline (GitHub Actions) must:
- Lint (flake8 + ESLint)
- Run unit + integration tests
- Build Docker images
- Validate Compose startup

A passing pipeline is required. Manual SSH deploy to GCP is acceptable.

---

## 8. What "Done" Means

The V3 project is done when a video demo can show:

**Production platform:**
- A platform administrator approving a user access request
- A viewer observing dashboards (read-only, no edit controls visible)
- An editor adding a target and configuring an alert rule
- A real platform-runtime check producing an in-app notification
- An incident opening, the viewer acknowledging the notification, and recovery with a complete audit trail

**Telemetry (retained from V2):**
- Real-time probe metrics updating on the dashboard
- Packet evidence visible and traceable
- Alert firing and incident opening
- Chaos injection visibly affecting dashboard (labeled as lab)
- Recovery restoring normal state

**Operational:**
- Docker Compose starting cleanly with one command
- Tests passing, CI pipeline green
