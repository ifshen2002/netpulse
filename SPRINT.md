# SPRINT.md — Execution Tracker

> This file tracks current state. Claude Code updates this file as phases complete.
> Locked sections must not be rewritten. History must never be deleted.

---

# 1. Execution Rules (LOCKED)

- Complete each phase before starting the next
- Every phase must boot, pass its tests, and be manually verified before moving on
- No silent refactors mid-phase
- No dirty workaround accumulation
- If something is broken at end of session: document it here before stopping

---

# 2. Phase Order (LOCKED)

Phase order is fixed. Skipping is not allowed.
However: Phase 7 (testing) and Phase 8 (CI/CD) are scoped to demo-sufficient coverage — not exhaustive. See phase definitions below.

```
Phase 1 → Backend Foundation
Phase 2 → Metrics & Nodes
Phase 3 → Realtime Pipeline
Phase 4 → Alerts & Incidents
Phase 5 → Chaos System
Phase 6 → Dashboard
Phase 7 → Validation (demo-scoped)
Phase 8 → CI/CD (pipeline-only, no auto-deploy)
```

---

# 3. Current Status (MUTABLE)

## Current Phase
Phase 8 — COMPLETE

## Current Focus
All 8 phases complete. Project is demo-ready.

## Latest Stable Milestone
Phase 8 CI/CD: GitHub Actions pipeline with 6 jobs (lint, unit-tests, frontend-build, integration-tests, live-server-tests, docker-verify). Uses service containers for PostgreSQL 16 + Redis 7. All flake8 issues resolved (F401/F841/E501/E305/E402). Coverage artifact upload on integration tests.

## Next Action
Demo recording — all functionality is operational and tested. Push to main triggers green pipeline.

## Blockers
None.

## Rollback Warning
None.

---

# 4. Phase Definitions (LOCKED)

## Phase 1 — Backend Foundation
Goal: stable backend runtime, nothing more.

Required:
- FastAPI app boots
- PostgreSQL connected, Alembic initialized
- Redis client connected
- APScheduler skeleton (no jobs)
- Docker Compose stable
- Healthcheck endpoint: GET /api/health → 200

Exit: `docker compose up` boots clean, integration test passes.

---

## Phase 2 — Metrics & Nodes
Goal: metrics flowing into DB.

Required:
- Node-1 psutil collection (cpu, memory, disk, latency stub, packet_loss stub)
- Node-2/3 simulator generating baseline metrics
- Metrics normalization to unified schema (ARCHITECTURE.md Section 6)
- Metrics written to PostgreSQL
- Retention cleanup job (delete > 72h)
- APScheduler jobs: 5s collection

Exit: metrics visible in DB, scheduler stable, retention test passes.

---

## Phase 3 — Realtime Pipeline
Goal: metrics pushing to browser in real time.

Required:
- WebSocket manager (in-memory broadcast)
- Events match schemas in ARCHITECTURE.md Section 7
- Frontend Zustand stores wired to WebSocket events
- Reconnect logic with bounded retry
- Degraded banner on disconnect

Exit: open browser, see metric_update events arriving every second.

---

## Phase 4 — Alerts & Incidents
Goal: monitoring lifecycle working end to end.

Required:
- Alert threshold evaluation (cpu_high, latency_spike, heartbeat_timeout)
- 60s deduplication per (node_id, alert_type)
- Incident creation on first alert
- Incident close after 3 consecutive clean evaluations
- alert_fired, incident_opened, incident_closed events over WebSocket

Exit: trigger high CPU on Node-2, see alert fire and incident open in dashboard.

---

## Phase 5 — Chaos System
Goal: controlled degradation overlay working.

Required:
- Chaos registry in memory
- apply_overlay() in pipeline before all storage/push
- All chaos types from ARCHITECTURE.md Section 10
- recover_all() clears registry
- Burst mode: 5s → 1s reporting frequency
- chaos_events written to DB

Exit: inject latency_spike on Node-2, see latency spike in dashboard; recover_all restores normal.

---

## Phase 6 — Dashboard
Goal: operational dashboard, demo-ready.

Required:
- NodeCard (status, live metrics per node)
- MetricsChart (cpu/memory/latency over time, Recharts)
- AlertBanner (recent alerts)
- IncidentTimeline (open/closed incidents)
- ChaosPanel (inject/recover controls)
- NodeControls (on/off, burst mode)

Exit: full demo flow recordable — metrics live, alert fires, chaos injected, recovery works.

---

## Phase 7 — Validation (Demo-Scoped)
Goal: tests that prove the system works correctly.

Required:
- Unit tests: alert evaluation logic, chaos overlay, incident lifecycle, metrics normalization
- Integration tests: metrics API, alert API, chaos API with real DB+Redis
- WebSocket test: connect, receive metric_update, disconnect cleanly (explicit timeout)
- pytest-cov coverage report generated
- All tests pass in CI environment (no manual steps)

Not required:
- 100% coverage
- stress tests
- E2E browser tests

Exit: `pytest` passes, coverage report exists.

---

## Phase 8 — CI/CD
Goal: pipeline that runs on push to main.

Required:
- GitHub Actions workflow
- Jobs: lint (flake8 + ESLint) → unit tests → integration tests → Docker build
- All jobs pass on clean push
- Manual SSH deploy to GCP is acceptable (no auto-deploy required)

Exit: push to main triggers pipeline, pipeline goes green.

---

# 5. Known Risks (MUTABLE)

| Risk | Mitigation | Status |
|---|---|---|
| WebSocket tests hanging | Explicit timeout + teardown, no infinite listeners | OPEN |
| Scheduler duplicate jobs | Singleton guard on startup | OPEN |
| Chaos overlay mutating raw metrics | Copy before overlay, never mutate in-place | OPEN |
| Docker logs exhausting disk | Rotation policy in all compose services | OPEN |
| e2-micro RAM pressure | Monitor during testing, reduce worker count if needed | OPEN |

---

# 6. Historical Mistakes (NEVER DELETE)

## Mistake 1 — Frontend Black Screen: `|| []` in Zustand Selector Causes Infinite Re-render Loop

**Date:** 2026-05-16 → 2026-05-17 (2 sessions, ~4 hours)

**Symptom:**
Frontend rendered as a complete black screen on `localhost:5174`. Brief 1ms flash of content, then entire React tree unmounted. Browser console showed: `Uncaught Error: Maximum update depth exceeded. This can happen when a component repeatedly calls setState inside componentWillUpdate or componentDidUpdate.`

**Root Cause:**
`NodeCard.jsx:38` — Zustand selector `(s) => s.history[nodeId] || []` creates a **new empty array reference** (`[]`) on every invocation. Zustand v5 uses React's `useSyncExternalStore` internally, which compares snapshots with `Object.is`. Since `[] !== []` (different object references), the store appears to have changed on every render → triggers re-render → selector runs again → returns yet another new `[]` → `Object.is` fails again → infinite loop. React detects 50+ nested updates and throws `Maximum update depth exceeded`, unmounting the entire tree. Body background is `#0f1117` (near-black) → black screen.

**Why it was hard to find:**
1. The error message "Maximum update depth exceeded" is generic — doesn't point to which component or what triggered the loop.
2. The Zustand store and selectors look deceptively simple — `|| []` is an idiomatic JavaScript pattern that every developer uses without thinking.
3. The minimal Zustand test (`create(() => ({value: 'hello'}))`) worked because `'hello' === 'hello'` (string value comparison). The bug only manifests with object/array references.
4. Initial hypothesis was wrong: suspected Recharts, Tailwind, React 19 compatibility, WebSocket events, StrictMode. All ruled out through systematic isolation.
5. The "flash then black" pattern was key: it meant initial render succeeded, but a SUBSEQUENT synchronous update caused the loop. This pointed to state/subscription mechanism, not component rendering itself.

**Debugging methodology (what worked):**
1. **Error visibility first** — Added `window.addEventListener('error', ...)` in `index.html` + wrapped App in `ErrorBoundary` with visible red fallback. Without this, the crash was invisible (just a black page).
2. **Component binary search** — Stripped App to minimal "HELLO" then added components one at a time: NodeCard ✓ → +AlertBanner ✗ → narrowed to store subscription.
3. **Dependency elimination** — Disabled WebSocket, StrictMode, ErrorBoundary, Tailwind classes one by one. None fixed it, ruling them all out.
4. **Minimal reproduction** — Created a bare Zustand store with just `{metrics: {}, history: {}}` and a component with the same nested selector pattern. It crashed → proved the issue was Zustand + reference-creating selectors, not our business logic.
5. **Root cause analysis** — Read Zustand v5 source (`esm/react.mjs`, `esm/vanilla.mjs`) to understand `useSyncExternalStore` + `Object.is` comparison. Identified that `|| []` creates a new reference on every call, which `Object.is` treats as a change.

**Wrong fixes attempted:**
1. Fixing CSS `background`/`color` propagation — irrelevant, page was black because React unmounted, not because styles were wrong.
2. Wrapping MetricsChart in ErrorBoundary — didn't help because the crash was in NodeCard, not in MetricsChart.
3. Adding `setNodeStatus` to avoid partial metric overwrite — a real bug (node_status_changed was corrupting metrics), but not THE bug causing the black screen.
4. Removing StrictMode — didn't help because the loop was in Zustand's subscription, not React's double-render.
5. Removing ErrorBoundary — made it worse because then we couldn't see the error message at all.

**Solution:**
One-line change in `NodeCard.jsx`:
```diff
- const history = useMetricsStore((s) => s.history[nodeId] || [])
+ const history = useMetricsStore((s) => s.history[nodeId] || EMPTY_ARR)
```
Where `EMPTY_ARR = Object.freeze([])` is a module-level constant in `metricsStore.js`. The frozen empty array is the same reference every time, so `Object.is(EMPTY_ARR, EMPTY_ARR)` → `true` → no spurious re-render.

**Prevention rule (add to DECISIONS.md or mental checklist):**
> **NEVER create new object/array/function references inside a Zustand selector.** The return value must be reference-stable when the underlying data hasn't changed. Use module-level constants for default values (`EMPTY_ARR`, `EMPTY_OBJ`). This applies to ANY external store using `useSyncExternalStore` (Redux, Jotai, etc.).

**Affected files:**
- `frontend/src/store/metricsStore.js` — added `export const EMPTY_ARR = Object.freeze([])`
- `frontend/src/components/NodeCard.jsx` — changed `|| []` to `|| EMPTY_ARR`

**Additional bug found during investigation:**
`useWebSocket.js` — `node_status_changed` handler was calling `updateMetric()` with incomplete data (only `{node_id, status, timestamp}`), which overwrote `cpu`/`memory`/`disk`/`latency_ms` with `undefined`. Fixed by adding `setNodeStatus()` action that merges status into existing metrics without touching other fields.

---

# 7. Failing Tests (MUTABLE)

None.

---

# 8. Stable Milestones (MUTABLE)

| Milestone | Status |
|---|---|
| Governance documents finalized | STABLE |
| Phase 1 — Backend Foundation | STABLE |
| Phase 2 — Metrics & Nodes | STABLE |
| Phase 3 — Realtime Pipeline | STABLE |
| Phase 4 — Alerts & Incidents | STABLE |
| Phase 5 — Chaos System | STABLE |
| Phase 6 — Dashboard | STABLE |
| Phase 7 — Validation | STABLE |
| Phase 8 — CI/CD | STABLE |

---

# 9. Session Resume Protocol (LOCKED)

At the start of every session:
1. Read CLAUDE.md
2. Read ARCHITECTURE.md
3. Read DECISIONS.md
4. Read SPRINT.md (this file)
5. Identify: current phase, next action, any blockers, any failing tests
6. Begin implementation only after completing steps 1–5
