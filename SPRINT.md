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
Phase 2 — COMPLETE

## Current Focus
Phase 2 exit criteria met. Ready for Phase 3.

## Latest Stable Milestone
Phase 2 Metrics & Nodes: 3 nodes reporting, metrics pipeline running (collect → normalize → DB + Redis), APIs returning data, retention cleanup active, 20 tests passing.

## Next Action
Begin Phase 3 — Realtime Pipeline. First step: WebSocket manager for in-memory broadcast.

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

None recorded yet.

When mistakes occur: document the pattern, the wrong fix tried, and the correct resolution. This section never shrinks.

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

---

# 9. Session Resume Protocol (LOCKED)

At the start of every session:
1. Read CLAUDE.md
2. Read ARCHITECTURE.md
3. Read DECISIONS.md
4. Read SPRINT.md (this file)
5. Identify: current phase, next action, any blockers, any failing tests
6. Begin implementation only after completing steps 1–5
