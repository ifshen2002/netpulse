# CLAUDE.md — NetPulse Entry Point

## MANDATORY SESSION START

Before ANY implementation, read these files in order:

1. `ARCHITECTURE.md` — system design + contracts (highest authority)
2. `DECISIONS.md` — your behavior rules
3. `SPRINT.md` — current phase, next action, blockers

If any implementation conflicts with ARCHITECTURE.md: STOP and flag it.

---

## PROJECT SNAPSHOT

**NetPulse** — cloud NOC monitoring dashboard for ops teams.

- Node-1: real host metrics (read-only, psutil)
- Node-2/3: synthetic simulated nodes (chaos-capable)
- Stack: FastAPI + PostgreSQL + Redis + React + Nginx + Docker Compose
- Target: GCP e2-micro (1GB RAM, 30GB disk)
- Goal: working demo for recorded video presentation

---

## YOUR THREE HARD CONSTRAINTS

**1. Architecture is locked.**
Do not change system boundaries, module responsibilities, DB schema shape, or WebSocket event schemas without flagging first.

**2. Autonomous by default.**
Make decisions independently on: function names, variable names, component structure, internal logic, file organization within a module, small UI choices. Only flag the situations listed in DECISIONS.md.

**3. File structure discipline.**
Max 5 items per folder level. Keep nesting shallow. Follow the structure in ARCHITECTURE.md Section 15.

---

## PRIORITY ORDER

When documents conflict:
1. ARCHITECTURE.md
2. DECISIONS.md
3. SPRINT.md

---

## DEMO TARGET (NOT NEGOTIABLE)

The system must be recordable as a video demo showing:
- live node metrics updating in real time
- alert firing and incident opening
- chaos injection visibly affecting dashboard
- recovery restoring normal state

This is the definition of done. Tests and CI/CD support this goal, not the reverse.
