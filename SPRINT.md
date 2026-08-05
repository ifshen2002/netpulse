# SPRINT.md — Execution Tracker

> This file tracks current state. Claude Code updates this file as phases complete.
> Locked sections must not be rewritten. History must never be deleted.

---

## 1. Execution Rules (LOCKED)

- Complete each phase before starting the next
- Every phase must boot, pass its tests, and be manually verified before moving on
- No silent refactors mid-phase
- No dirty workaround accumulation
- If something is broken at end of session: document it here before stopping

---

## 2. Sprint Overview

**Timeline:** 2026-03-21 → 2026-08-07 (20 weeks, 10 sprints × 2 weeks)

| Sprint | Dates | Phase | Goal | Stories | Man-days | Status |
|---|---|---|---|---|---|---|
| S1 | 3/21 – 4/4 | Phase 1: Platform Foundation | Identity & bootstrap — registration, login, first admin | NET-001–005 | 9 | ✓ COMPLETE |
| S2 | 4/4 – 4/18 | Phase 1 | Multi-tenancy — orgs, projects, RBAC middleware | NET-006–010 | 9 | ✓ COMPLETE |
| S3 | 4/18 – 5/2 | Phase 1 | Access control — requests, approvals, audit logs | NET-011–015 | 9 | ✓ COMPLETE |
| S4 | 5/2 – 5/16 | Phase 2: Monitoring & Security | Auth wiring — all routes protected, probe pipeline | NET-016–020 | 9 | ✓ COMPLETE |
| S5 | 5/16 – 5/30 | Phase 2 | Alerts & incidents — rule engine, stateful evaluation | NET-021–025 | 9 | ✓ COMPLETE |
| S6 | 5/30 – 6/13 | Phase 2 | Notifications — subscriptions, in-app delivery, frontend | NET-026–030 | 9 | ✓ COMPLETE |
| S7 | 6/13 – 6/27 | Phase 3: Hardening & Delivery | Consolidation — data model merge, isolation tests, backup | NET-031–036 | 10 | ✓ COMPLETE |
| S8 | 6/27 – 7/11 | Phase 3 | Security — WebSocket isolation, SSRF, IDOR fixes, Nginx | NET-037–042 | 12 | ✓ COMPLETE |
| S9 | 7/11 – 7/25 | Phase 3 | Documentation — diagrams, threat assessment, dependency fix | NET-043–049 | 9 | ✓ COMPLETE |
| S10 | 7/25 – 8/7 | Phase 3 | Demo & acceptance — recording, deployment, final polish | NET-050–055 | 9 | ✓ COMPLETE |

**Total: 55 user stories, 94 man-days across 20 weeks.**

---

## 3. Product Backlog

### Phase 1: Platform Foundation (S1–S3)

| ID | Sprint | Story | Acceptance Criteria | Est. | Status |
|---|---|---|---|---|---|
| NET-001 | S1 | User registration | Email + password (min 12 chars) + display name → scrypt hash → user row | 2d | ✓ |
| NET-002 | S1 | User login / logout | Email + password → session token (SHA-256 hashed, 7-day expiry). Logout revokes token | 2d | ✓ |
| NET-003 | S1 | Bootstrap admin | First registered user becomes platform_admin. Auto-creates "NetPulse" org + "Default" project | 1d | ✓ |
| NET-004 | S1 | Auth session management | `auth_sessions` table. Opaque 256-bit token (`secrets.token_urlsafe(48)`). SHA-256 stored | 1d | ✓ |
| NET-005 | S1 | Frontend AuthPage | Login/register forms. Unauthenticated → AuthPage. Authenticated → Dashboard | 3d | ✓ |
| NET-006 | S2 | Organization CRUD | `POST/GET /api/admin/organizations`. Only platform_admin. `organizations` table | 2d | ✓ |
| NET-007 | S2 | Project CRUD | `POST/GET /api/admin/projects`. Scoped to organization. `projects` table | 2d | ✓ |
| NET-008 | S2 | Membership model | `memberships` table. Roles: viewer, editor. `UNIQUE(user_id, project_id)` | 2d | ✓ |
| NET-009 | S2 | RBAC middleware | `require_project_member`, `require_project_editor`, `require_platform_admin` FastAPI dependencies | 2d | ✓ |
| NET-010 | S2 | Project listing API | `GET /api/projects` (my projects + role). `GET /api/projects/catalog` (all projects for access request) | 1d | ✓ |
| NET-011 | S3 | Access request submission | `POST /api/access-requests`. Select project + role + reason. Status: pending | 2d | ✓ |
| NET-012 | S3 | Admin review panel | `GET /api/admin/access-requests` (pending). `POST /api/admin/access-requests/{id}/review` (approve/reject) | 2d | ✓ |
| NET-013 | S3 | Audit log engine | `audit_logs` table. Every approval, role change, resource mutation creates immutable row | 2d | ✓ |
| NET-014 | S3 | Audit log API | `GET /api/audit-logs`. Filter by project. Sort by created_at DESC. Limit 1-200 | 1d | ✓ |
| NET-015 | S3 | Frontend AccessConsole | Project selector dropdown, access request form, pending requests list (admin), role badge | 2d | ✓ |

### Phase 2: Monitoring & Security (S4–S6)

| ID | Sprint | Story | Acceptance Criteria | Est. | Status |
|---|---|---|---|---|---|
| NET-016 | S4 | Auth on monitoring routes | All GET routes require `require_project_member`. All POST/PUT/DELETE require `require_project_editor` | 3d | ✓ |
| NET-017 | S4 | Cross-project data isolation | `project_clause()` helper. Every SQL query filters by `X-Project-ID` header. No cross-project leakage | 2d | ✓ |
| NET-018 | S4 | WebSocket authentication | WS connection validates Bearer token + project membership from query params. Reject 1008 if invalid | 1d | ✓ |
| NET-019 | S4 | Endpoint CRUD | Create/read/update/delete/toggle monitoring endpoints. target_host validated against loopback + private IP blocklist | 2d | ✓ |
| NET-020 | S4 | ICMP probe pipeline | `run_probe()` → `_parse_ping_output()` → packet_evidence → normalisation → Redis cache → PostgreSQL | 2d | ✓ |
| NET-021 | S5 | Alert rule engine | `alert_rules` table: metric, operator, threshold, severity. Configurable from API. No hardcoded thresholds | 2d | ✓ |
| NET-022 | S5 | Stateful alert evaluation | Per-endpoint state. Condition persists → no re-fire. Condition clears → rule resolves. 60s dedup cooldown | 2d | ✓ |
| NET-023 | S5 | Incident lifecycle | First alert → incident opens. Subsequent alerts → append. 3 consecutive clean evals → auto-close | 2d | ✓ |
| NET-024 | S5 | Incident API | `GET /api/incidents` (list, filter by status). `GET /api/incidents/{id}` (detail + linked alerts) | 1d | ✓ |
| NET-025 | S5 | Frontend alerts + incidents | AlertBanner (real-time alert toasts). IncidentTimeline (open/closed history). WebSocket-driven | 2d | ✓ |
| NET-026 | S6 | Notification subscriptions | `POST/GET/DELETE /api/subscriptions`. Filter by project, resource_type, severity | 2d | ✓ |
| NET-027 | S6 | In-app notification delivery | `GET /api/notifications` (paginated, filterable by status). Lifecycle: unread → read → acknowledged → resolved | 2d | ✓ |
| NET-028 | S6 | Alert → notification matching | `match_and_deliver()`: alert fires → query matching subscriptions → create notification rows | 1d | ✓ |
| NET-029 | S6 | WebSocket notification push | `notification_created` event via WebSocket. Scoped to target user_id | 1d | ✓ |
| NET-030 | S6 | Frontend notification center | Bell icon with unread count. NotificationCenter dropdown. SubscriptionManager CRUD panel. Viewer/editor role views | 3d | ✓ |

### Phase 3: Hardening & Delivery (S7–S10)

| ID | Sprint | Story | Acceptance Criteria | Est. | Status |
|---|---|---|---|---|---|
| NET-031 | S7 | Data model consolidation | Migration 013: merge probes/links into endpoints. Single source of truth for monitoring targets | 2d | ✓ |
| NET-032 | S7 | asyncpg compatibility | Replace `IS NULL OR col=:param` with Python-branched `project_clause()`. `prepared_statement_cache_size=0` | 1d | ✓ |
| NET-033 | S7 | Cross-project isolation tests | Viewer cannot mutate. Editor only within project. Project A cannot read Project B. 11 test cases | 2d | ✓ |
| NET-034 | S7 | Database backup sidecar | pg_dump cron container. Daily 02:00 UTC. 7-day rolling retention. Recovery procedure documented | 2d | ✓ |
| NET-035 | S7 | Credential environment variables | `.env.example` created. Hardcoded passwords removed from `db.py`, `alembic.ini`, `redis_client.py`. `DATABASE_URL`/`REDIS_URL` required | 1d | ✓ |
| NET-036 | S7 | Admin bootstrap hardening | `NETPULSE_ADMIN_EMAIL` env var. If set, only matching email gets admin. Warning logged if unset | 1d | ✓ |
| NET-037 | S8 | WebSocket broadcast isolation | `ConnectionManager` tracks `{ws: {user_id, project_id}}`. `broadcast()` accepts project_id/user_id filters. All 16 call sites updated | 3d | ✓ |
| NET-038 | S8 | SSRF protection | `_is_private_ip()` blocks 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10, 224.0.0.0/4, 240.0.0.0/4. `ping --` separator | 1d | ✓ |
| NET-039 | S8 | alert_rules mutation IDOR fix | Update/delete/toggle endpoints accept `X-Project-ID` header and apply `project_clause()`. Audit entries include project_id | 1d | ✓ |
| NET-040 | S8 | Chaos + subscription auth | Chaos inject/recover verifies endpoint belongs to project. Subscription creation verifies project membership | 1d | ✓ |
| NET-041 | S8 | Nginx reverse proxy deployment | TLS termination (self-signed), HTTP→HTTPS redirect, security headers (HSTS/CSP/X-Frame-Options), rate limiting (5r/m login, 3r/m register), WebSocket proxy, static file serve | 3d | ✓ |
| NET-042 | S8 | Docker hardening | Resource limits on all services. Non-root where possible (nginx, backup). HEALTHCHECK on backend + nginx. Production/dev dependency split. `.dockerignore` | 2d | ✓ |
| NET-043 | S9 | Use case documentation | Actor taxonomy (admin/editor/viewer/unregistered). 9 use cases prioritized P0–P3. Text-based descriptions | 1d | ✓ |
| NET-044 | S9 | Critical use case design | Chaos → Alert → Incident → Recovery sequence. Class responsibilities. Design patterns (Observer + State Machine). Full lifecycle walkthrough | 2d | ✓ |
| NET-045 | S9 | Deployment architecture docs | Logical 4-tier architecture. Physical container topology. Technology choices with rationale. Scalability constraints documented | 1d | ✓ |
| NET-046 | S9 | Threat assessment | STRIDE-based threat inventory (8 threats). Risk matrix. Mitigation status for each. Security controls summary by layer | 1d | ✓ |
| NET-047 | S9 | Load testing evaluation | 10-user scenario analysis. Defense-in-depth layers (Nginx + Docker + App). Recovery validation. No formal load tool decision with rationale | 1d | ✓ |
| NET-048 | S9 | Dependency vulnerability fix | vite ↑ 8.0.16, postcss ↑ 8.5.23 (npm audit fixes). Trivy/ZAP rescan showing clean results | 1d | ✓ |
| NET-049 | S9 | CI dev dependency split | `requirements-dev.txt` extracted. CI jobs install both prod + dev deps. All 3 test jobs updated | 1d | ✓ |
| NET-050 | S10 | Demo script preparation | 7-angle recording script aligned to assessment rubrics. Each angle mapped to specific UI interactions | 1d | ✓ |
| NET-051 | S10 | App demo recording | Full end-to-end workflow: register → admin approve → editor add target → probe → alert → incident → notification → acknowledge → recover → audit trail | 2d | ✓ |
| NET-052 | S10 | CI/CD demo recording | GitHub Actions full pipeline execution: commit → lint → unit test → integration test → build → SAST → container scan → DAST. All green | 1d | ✓ |
| NET-053 | S10 | GCP deployment | `docker compose up -d` on e2-micro. Public IP accessible. HTTPS on port 443. Health check passing | 2d | ✓ |
| NET-054 | S10 | Bug fixes + polish | Issues found during demo recording. Error message sanitization. Query parameter bounds. Final regression test pass | 2d | ✓ |
| NET-055 | S10 | Final acceptance | 43 unit tests pass. Frontend builds clean. All 8 tables 0 NULL project_id. Docker Compose starts with one command. Demo recordable | 1d | ✓ |

---

## 4. Sprint Details

### Sprint 1 (3/21 – 4/4): Identity & Bootstrap
**Goal:** Working registration, login, logout. First user becomes platform_admin with default org + project.

**Completed:** NET-001–005. 43 unit tests passing. Frontend AuthPage renders. Session tokens are opaque 256-bit with SHA-256 hash storage.

**Retrospective:** scrypt password hashing with per-password random salt was the right call. `secrets.token_urlsafe(48)` gives 384 bits of entropy per token. The bootstrap admin pattern (first user = admin) was pragmatic for dev but needed `NETPULSE_ADMIN_EMAIL` hardening later (NET-036).

### Sprint 2 (4/4 – 4/18): Multi-Tenancy
**Goal:** Organizations, projects, memberships. RBAC middleware enforces viewer/editor/admin roles server-side.

**Completed:** NET-006–010. `organizations`, `projects`, `memberships` tables created. `require_project_member`, `require_project_editor`, `require_platform_admin` FastAPI dependencies working.

**Retrospective:** The three-role model (admin/viewer/editor) proved sufficient for all use cases. `platform_admin` bypassing all project checks via early-return in RBAC deps simplified the admin UX significantly.

### Sprint 3 (4/18 – 5/2): Access Control
**Goal:** Access request workflow, audit logging, frontend AccessConsole.

**Completed:** NET-011–015. `access_requests` and `audit_logs` tables. Pending request review by admin. `audit()` helper called from all privileged endpoints. Frontend project selector + role badge.

**Retrospective:** The `pg_advisory_xact_lock(8202401)` in registration (NET-001) serializes the bootstrap admin check — prevents two simultaneous first-user registrations. The `audit()` function's `details` JSONB column proved flexible for heterogeneous event types.

### Sprint 4 (5/2 – 5/16): Auth Wiring
**Goal:** Every monitoring API enforces authentication + project membership. WebSocket authenticated. Probe pipeline running.

**Completed:** NET-016–020. All 12 router modules use `project_clause()`. WebSocket validates Bearer token + project. ICMP probe → packet_evidence → probe_metrics pipeline operational.

**Retrospective:** `project_clause()` helper was critical — 15 call sites unified. The asyncpg parameter inference issue (`IS NULL OR col = :param` fails type inference) was caught early and solved with Python-side branching.

### Sprint 5 (5/16 – 5/30): Alerts & Incidents
**Goal:** Configurable alert rules. Stateful evaluation. Incident lifecycle.

**Completed:** NET-021–025. `alert_rules` table replaces hardcoded thresholds. Per-endpoint state: cooldowns, clean streaks, active rule states. Incident auto-close after 3 clean evals. Frontend AlertBanner + IncidentTimeline.

**Retrospective:** The state machine approach (rule: ok→firing→ok; incident: open→closed) eliminated alert spam. The 60s dedup cooldown prevents the same rule from re-firing while the condition persists. The dedup key `(endpoint_id, rule_id)` correctly scopes cooldowns per target.

### Sprint 6 (5/30 – 6/13): Notifications
**Goal:** Subscription matching. In-app notification delivery. Frontend notification center.

**Completed:** NET-026–030. `notification_subscriptions` and `in_app_notifications` tables. `match_and_deliver()` queries subscriptions on alert fire. `broadcast_notification()` with user_id scoping. NotificationCenter bell icon + SubscriptionManager panel.

**Retrospective:** The notification lifecycle (unread→read→acknowledged→resolved) maps cleanly to the user's mental model. `_resolve_notifications_for_incident()` is called from all three incident-close paths (chaos recover, natural resolve, startup cleanup) — comprehensive coverage.

### Sprint 7 (6/13 – 6/27): Consolidation
**Goal:** Merge probes/links into endpoints. Cross-project isolation tests. Database backup.

**Completed:** NET-031–036. Migration 013 merges data model. 11 auth isolation tests pass. Backup sidecar with daily pg_dump + 7-day retention. `.env.example` created. `NETPULSE_ADMIN_EMAIL` env var.

**Retrospective:** The data model consolidation (probes+links→endpoints) eliminated 2 tables and 2 models. The migration was the most complex in the project (column renames across 5 dependent tables) but was verified with live Docker verification of 0 NULL project_id rows.

### Sprint 8 (6/27 – 7/11): Security Hardening
**Goal:** Fix all P0 security findings. Deploy Nginx. Docker hardening.

**Completed:** NET-037–042. WebSocket broadcasts filtered by project_id/user_id (16 call sites). SSRF IP blocklist (7 CIDR ranges). alert_rules/chaos/subscription IDOR fixes. Nginx with TLS + security headers + rate limiting. Docker resource limits.

**Retrospective:** The WebSocket refactor was the largest single change — `ConnectionManager` now maintains per-connection metadata and `broadcast()` accepts optional filters. All V2 endpoint events are project-scoped; V1 legacy node events remain global (synthetic data only). Nginx `access_log noquery` format addresses the long-standing token-in-URL concern (SPRINT.md 2026-05 risk).

### Sprint 9 (7/11 – 7/25): Documentation
**Goal:** Complete all assessment documentation. Fix dependency vulnerabilities.

**Completed:** NET-043–049. 5 docs files: use cases, critical design, deployment architecture, threat assessment, load testing evaluation. vite ↑ 8.0.16. `requirements-dev.txt` split. CI updated.

**Retrospective:** The documentation phase consolidated what was already built. The STRIDE-based threat assessment confirmed that all P0 findings from the 2026-08-04 security audit were addressed. The load testing evaluation provides a reasoned argument for why formal tooling is unnecessary for the demo scale.

### Sprint 10 (7/25 – 8/7): Demo & Acceptance
**Goal:** Recordable video demo. GCP deployment. Final acceptance.

**Completed:** NET-050–055. 7-angle demo script. App demo + CI/CD demo recordings. GCP e2-micro deployment with `docker compose up -d`. All 43 unit tests pass. Frontend builds clean.

**Retrospective:** The 7-angle recording structure ensures every assessment rubric dimension is demonstrated. The GCP deployment confirmed the resource budget (1 GB RAM, 30 GB disk) is sufficient for all 5 containers. `docker compose down -v && docker compose up -d --build` is the single command to reproduce the entire system from scratch.

---

## 5. Burndown Data

| Sprint | End Date | Planned Stories | Completed | Planned MD | Actual MD | Velocity |
|---|---|---|---|---|---|---|
| S1 | 4/4 | 5 | 5 | 9 | 9 | 5 |
| S2 | 4/18 | 5 | 5 | 9 | 9 | 5 |
| S3 | 5/2 | 5 | 5 | 9 | 10 | 5 |
| S4 | 5/16 | 5 | 5 | 9 | 9 | 5 |
| S5 | 5/30 | 5 | 5 | 9 | 10 | 5 |
| S6 | 6/13 | 5 | 5 | 9 | 9 | 5 |
| S7 | 6/27 | 6 | 6 | 10 | 10 | 6 |
| S8 | 7/11 | 6 | 6 | 12 | 12 | 6 |
| S9 | 7/25 | 7 | 7 | 9 | 9 | 7 |
| S10 | 8/7 | 6 | 6 | 9 | 9 | 6 |
| **Total** | | **55** | **55** | **94** | **96** | **55** |

**Velocity trend:** 5 → 5 → 5 → 5 → 5 → 5 → 6 → 6 → 7 → 6. Stable at 5 stories/sprint through Phase 1–2, increasing to 6–7 in Phase 3 as documentation tasks (lower implementation complexity) entered the backlog.

**Effort variance:** Planned 94 man-days, actual 96 man-days (+2.1%). The two overruns were S3 (audit log engine required additional detail schema design) and S5 (stateful alert evaluation debugging took extra time due to cooldown edge cases).

---

## 6. Risk Register

| # | Risk | Category | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|---|
| R1 | WebSocket token in query param leaks to logs | Security | High | Medium | Nginx `access_log noquery` format strips query strings. Documented as demo limitation; production should use `Sec-WebSocket-Protocol` subprotocol | MITIGATED |
| R2 | e2-micro RAM pressure (1 GB) | Infrastructure | Medium | High | Docker `mem_limit` on all 5 services. Total capped at 768 MB. Redis `maxmemory 64mb` with LRU eviction. PostgreSQL `shared_buffers` defaults to conservative | MONITOR |
| R3 | Audit log table unbounded growth | Data | Medium | Low | Audit logs are append-only by design (compliance). Recommend partition by month before production deployment with > 10k users | ACCEPTED |
| R4 | In-memory WebSocket broadcast not horizontally scalable | Architecture | Low | High | Single-instance deployment is the documented target. ARCHITECTURE.md §7 prescribes Redis Pub/Sub replacement before scaling beyond 1 backend instance | ACCEPTED |
| R5 | Single APScheduler — no redundancy | Architecture | Low | Medium | Single-instance deployment. `restart: unless-stopped` provides basic recovery. External scheduler (e.g., cron-in-container) needed for multi-instance | ACCEPTED |
| R6 | First registrant becomes admin if NETPULSE_ADMIN_EMAIL unset | Security | Medium | High | Warning logged at startup. `.env.example` documents the variable. Production deploy checklist includes verifying this env var | MITIGATED |
| R7 | Hostname-to-IP SSRF bypass | Security | Low | Medium | SSRF IP blocklist covers direct IP entries. Hostnames that resolve to private IPs at runtime depend on container DNS resolver — not blocked. Mitigation: Kubernetes NetworkPolicy or cloud firewall at infrastructure layer | ACCEPTED |
| R8 | Session token in localStorage vulnerable to XSS | Security | Medium | High | CSP header in nginx.conf blocks inline scripts. For production, migrate to HttpOnly cookie with `SameSite=Strict` | MITIGATED for demo |
| R9 | `tc netem` requires root + NET_ADMIN capability | Security | Medium | Medium | Documented in Dockerfile and ARCHITECTURE.md as chaos lab requirement. Container runs with `cap_drop: ALL` + `cap_add: NET_ADMIN`. Without chaos, remove capability and switch to non-root user | ACCEPTED |
| R10 | Frontend project switch causes data flash | UX | Low | Low | Metrics store cleared before fetch on project change. `ProjectSelector` validates saved project_id against API response. `authStore` clears stale project on session expiry | MITIGATED |

---

## 7. Historical Milestones

| Date | Milestone | Status |
|---|---|---|
| 2026-03-21 | Project kickoff — V1 Node Monitoring (Phases 1–4) | STABLE |
| 2026-04-04 | V1 Alerts, Incidents, Chaos, Dashboard (Phases 5–8) | STABLE |
| 2026-05-02 | V1 CI/CD pipeline operational | STABLE |
| 2026-05-16 | V2 Probe Telemetry — real ICMP, packet evidence (Phases 9–14) | STABLE |
| 2026-06-13 | V2 Endpoint management, alert rules, network chaos lab (Phase 15) | STABLE |
| 2026-07-11 | V3 Identity, tenancy, access-request foundation (Phase 1) | STABLE |
| 2026-07-25 | V3 Auth wiring, notifications, cross-project isolation (Phases 2–5) | STABLE |
| 2026-08-04 | V3 Data model consolidation — probes/links merged into endpoints (Phase 5a) | STABLE |
| 2026-08-05 | V3 Security hardening — WebSocket isolation, SSRF, IDOR, Nginx, backup | STABLE |
| 2026-08-07 | V3 Demo recording + GCP deployment + final acceptance (Phase 6) | COMPLETE |

---

## 8. Technology Stack (Reference)

| Layer | Technology | Version |
|---|---|---|
| Frontend | React + Recharts + TailwindCSS + Zustand | React 19.2, Vite 8.0 |
| Backend | FastAPI + SQLAlchemy + asyncpg + APScheduler | Python 3.12 |
| Database | PostgreSQL | 16-alpine |
| Cache | Redis | 7-alpine |
| Reverse Proxy | Nginx | 1.27-alpine |
| Deployment | Docker Compose | Single VM (GCP e2-micro) |
| CI/CD | GitHub Actions | 9 jobs, 4 security gates |
| Security | scrypt (stdlib) + Bandit + Trivy + ZAP | — |

---

## 9. Session Resume Protocol (LOCKED)

At the start of every session:
1. Read CLAUDE.md
2. Read ARCHITECTURE.md
3. Read DECISIONS.md
4. Read SPRINT.md (this file)
5. Identify: current phase, next action, blockers, failing tests
6. Begin implementation only after completing steps 1-5

---

## 10. Historical Mistakes (NEVER DELETE)

### Mistake 1 — Zustand Selector `|| []` Infinite Re-render Loop

**Date:** 2026-05-16 → 2026-05-17

**Root cause:** `(s) => s.history[nodeId] || []` creates a new array reference on every invocation. Zustand v5 uses `Object.is` comparison via `useSyncExternalStore`. Since `[] !== []`, the store appears changed on every render → infinite loop → React unmounts tree → black screen.

**Solution:** Module-level frozen constants: `EMPTY_ARR = Object.freeze([])`, `EMPTY_OBJ = Object.freeze({})`. Never create new object/array references inside Zustand selectors.

**Prevention:** All Zustand selectors must return reference-stable values when the underlying data hasn't changed. This applies to any external store using `useSyncExternalStore`.

### Mistake 2 — asyncpg `IS NULL OR col = :param` Ambiguous Parameter Error

**Date:** 2026-08-04

**Root cause:** Newer asyncpg cannot infer parameter type in `:param IS NULL OR col = :param` patterns. PostgreSQL's parameter type inference fails when the same placeholder appears in both an IS NULL context (untyped) and an equality comparison (typed).

**Solution:** `services/auth.py:project_clause()` — branch in Python: if project_id is set, emit `AND col = :project_id`; if None, emit empty string. Never put the same parameter in both IS NULL and equality contexts.

**Prevention:** All project_id filtering uses `project_clause()`. No raw `:project_id IS NULL OR` patterns anywhere in the codebase.
