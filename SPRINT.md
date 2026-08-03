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

## 2. V3 Platform Phases (LOCKED)

```
Phase 1  → Identity, tenancy, and access-request foundation    ✓ COMPLETE
Phase 2  → Wire auth into all monitoring routes                 ✓ COMPLETE
Phase 3  → Notification subscriptions and in-app delivery       ✓ COMPLETE
Phase 4  → Frontend: project selector, notification center, subscription UI  ✓ COMPLETE
Phase 5  → Cross-project isolation and permission enforcement tests  ✓ COMPLETE
Phase 5a → Data model consolidation (probes/links merged into endpoints)  ✓ COMPLETE
Phase 6  → Platform demo and acceptance
```

---

## 3. Current Status (MUTABLE)

**Current phase:** Phase 6 — Platform demo and acceptance

**Latest checkpoint — 2026-08-04:**
- All 8 data tables verified: 0 NULL project_id rows (verified live against running Docker)
- 43/43 unit tests pass. Frontend builds clean.
- Data consistency: scheduler writes project_id on every INSERT; periodic 30s backfill catches strays; `project_clause()` helper unifies all router SQL
- Known admin credential: `ifshen2002@gmail.com` (first registered user, platform_admin)
- Docker commands: `docker compose down -v && docker compose up -d --build` for clean start
- Browser: clear localStorage `netpulse.*` keys before first login after rebuild

**Phase 5a deliverables (data model consolidation, complete):**
- Migration 013 merges `probes` and `links` tables into `endpoints`
- `endpoints` table now carries `status`, `last_seen`, `protocol` (runtime columns)
- `packet_evidence` and `probe_metrics` use `endpoint_id` (not `probe_id` / `link_id`)
- `alerts` and `incidents` use `endpoint_id` (not `probe_id`)
- `models/__init__.py`: Probe/Link models removed; EndpointMetric renamed from ProbeMetric
- `schemas/__init__.py`: ProbeOut/LinkOut removed; EndpointMetricOut introduced
- `routers/probes.py` deleted; metrics/evidence/config endpoints merged into `routers/endpoints.py`
- `services/alerting.py`: legacy threshold variables removed; `evaluate_endpoint()` replaced `evaluate_probe()`; `_fire_endpoint_alert()` etc.
- `services/normalization.py`: `normalize_endpoint()` replaced `normalize_probe()`
- `services/probe.py`: parameter `probe_id` → `endpoint_id`
- `services/netchaos.py`: `_resolve_target_ip()` uses `endpoints` table
- `scheduler.py`: `_collect_endpoints()` (was `_collect_probes`), writes project_id; `_push_endpoint_metrics()` (was `_push_probe_metrics`); `_evaluate_endpoint_alerts()`; `_backfill_project_ids()` periodic job
- WebSocket events: `endpoint_metric_update` (was `probe_metric_update`); `endpoint_status_changed` (was `link_status_changed`)
- `services/auth.py`: `project_clause()` helper — asyncpg-safe conditional project_id filtering; all routers migrated to use it (15 occurrences replaced)
- `db.py`: `prepared_statement_cache_size=0` for asyncpg compatibility
- `services/notifications.py`: `resource_type` passed explicitly by caller (was derived from alert_type prefix)
- Frontend: `probeMetrics` → `endpointMetrics`, `probeHistory` → `endpointHistory`, `visibleProbes` → `visibleEndpoints`, `updateProbeMetric` → `updateEndpointMetric`, `fetchInitialProbes` → `fetchInitialEndpoints` in metricsStore.js
- Frontend: EndpointCard uses `endpoint.status` directly (no more `probe_status`); PacketEvidencePanel, EvidenceInspector use `endpointId`
- Frontend: NetworkChaosPanel uses `endpoint_id`; AlertBanner alert type prefixes updated
- Frontend: EvidenceInspector fetches actual alert_rules from API (was hardcoded thresholds)
- Frontend: `ProjectSelector`, `AccessConsole`, `SubscriptionManager` validate saved project_id against API response
- Frontend: `AccessConsole` and `SubscriptionManager` error/notice messages auto-dismiss after 5 seconds
- Frontend: `authStore.js` clears stale `netpulse.project` on session expiry
- Tests: `test_websocket.py` _VALID_TYPES updated; `test_auth_isolation.py` route list updated

**Phase 5 deliverables (complete):**
- Alert insert now includes `project_id` lookup from nodes/probes tables
- Notification auto-resolve on incident close: `_resolve_notifications_for_incident()` called from all three resolve paths
- Notification delivery functions accept `project_id` directly instead of redundant DB lookup
- Unit test mocks updated for new engine.begin() call patterns

**Phase 4 deliverables (complete):**
- `ProjectSelector.jsx`: dropdown in header showing user's projects with role, sets X-Project-ID on change
- `SubscriptionManager.jsx`: create/delete alert subscriptions with project/resource_type/severity filters
- `authStore.js`: `projectRole` tracking (`fetchProjectRole` on init/login, stored per selected project)
- Viewer mode: `canEdit` flag derived from project role, passed to LinkView/NodeView/EndpointCard
- EndpointCard hides toggle/edit/delete buttons for viewers
- NodeView hides ChaosPanel and NodeControls for viewers
- LinkView hides CreateEndpointButton, NetworkChaosPanel, AlertRulesManager for viewers
- LAB badges on chaos panels, CONFIG badge on alert rules manager
- Role badge in header shows viewer/editor/platform_admin with color coding

**Phase 3 deliverables (complete):**
- Migration 011: `notification_subscriptions` and `in_app_notifications` tables
- `services/notifications.py`: subscriber matching (`match_and_deliver`), notification creation
- `routers/notifications.py`: GET/POST/DELETE subscriptions, GET notifications, PATCH read/acknowledge, unread count
- Integration with alerting.py: `_deliver_notifications_for_node` (V1) and `_deliver_notifications_for_endpoint` (V2)
- Frontend `NotificationCenter.jsx`: bell icon with unread count, dropdown list, mark read/acknowledge actions
- Frontend WebSocket handler for `notification_created` event
- Frontend store: `addNotification`, `fetchNotifications`, `markNotificationRead`, `acknowledgeNotification`

**Phase 2 deliverables (complete):**
- All GET routes require authenticated project membership via `Depends(require_project_member)`
- All POST/PUT/PATCH/DELETE routes require editor permission via `Depends(require_project_editor)`
- All DB queries filter by `project_id` from `X-Project-ID` header (using `project_clause()` helper)
- WebSocket validates Bearer token + project membership from query params
- Frontend WebSocket hook sends `access_token` and `project_id` query params
- Cross-project resource ID enumeration blocked (404 if wrong project)

---

## 4. Phase Definitions (LOCKED)

### Phase 1 — Identity, tenancy, and access-request foundation ✓

Deliverables (all complete):
- Registration, login, logout with scrypt password hashing
- Opaque session tokens (SHA-256 hashed in DB, 7-day expiry)
- Bootstrap platform_admin (first registered user)
- Organizations, Projects, Memberships tables and APIs
- platform_admin / viewer / editor RBAC
- Access request submission and approval/rejection workflow
- Audit log for all identity and administrative actions
- Frontend auth gate (AuthPage for unauthenticated, Dashboard for authenticated)

### Phase 2 — Wire auth into all monitoring routes ✓

Goal: Every monitoring API and the WebSocket feed enforces authentication and project membership.

### Phase 3 — Notification subscriptions and in-app delivery ✓

Goal: When an alert fires, matching subscribers receive in-app notifications via WebSocket.

### Phase 4 — Frontend: project selector, notification center, subscription UI ✓

Goal: Complete the user-facing platform experience.

### Phase 5 — Cross-project isolation and permission enforcement tests ✓

Goal: Prove that authorization works correctly.

### Phase 5a — Data model consolidation ✓ [2026-08-04]

Goal: Merge probes/links into endpoints — single source of truth. Remove legacy alert thresholds. Fix asyncpg compatibility. Verify all 8 tables have 0 NULL project_id rows.

### Phase 6 — Platform demo and acceptance

Goal: Recordable video demo showing the complete platform story.

Required:
- Administrator approves a user access request
- Viewer observes dashboards (read-only, no edit controls)
- Editor adds a target and configures an alert rule
- Real probe check produces an in-app notification
- Incident opens, viewer acknowledges notification
- Recovery with complete audit trail
- Lab chaos injection visibly separated from production data

---

## 5. Known Risks

| Risk | Mitigation | Status |
|---|---|---|
| WebSocket auth: token in query param exposes it in logs | Use `?token=` param only for WebSocket; Nginx must strip query strings from access logs | OPEN |
| e2-micro RAM pressure with additional services | No new services added; notification engine runs in-process | MONITOR |
| Frontend project selector causes data flash on switch | Fetch endpoints/metrics eagerly on project change, clear store first | OPEN |
| Audit log table growth | Partition by month or add retention policy before production deployment | MONITOR |

---

## 6. Historical Milestones

| Milestone | Status |
|---|---|
| V1 Phases 1-8 (Node monitoring, alerts, chaos, dashboard, CI/CD) | STABLE |
| V2 Phases 9-14 (Probe telemetry, packet evidence, link view, isolated chaos) | STABLE |
| V2 Phase 15 (Endpoint management, alert rules, evidence inspector, summary bar) | STABLE |
| V3 Phase 1 (Identity, tenancy, access-request foundation) | STABLE |
| V3 Phase 5a (Data model consolidation — 2026-08-04) | STABLE |

---

## 7. Session Resume Protocol (LOCKED)

At the start of every session:
1. Read CLAUDE.md
2. Read ARCHITECTURE.md
3. Read DECISIONS.md
4. Read SPRINT.md (this file)
5. Identify: current phase, next action, blockers, failing tests
6. Begin implementation only after completing steps 1-5

---

## 8. Historical Mistakes (NEVER DELETE)

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
