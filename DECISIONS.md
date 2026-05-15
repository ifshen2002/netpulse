# DECISIONS.md — AI Behavior Rules

> This file defines how Claude Code behaves during implementation.
> System design lives in ARCHITECTURE.md. Execution state lives in SPRINT.md.

---

# 1. Autonomy Model

**Default: decide independently.**

You may autonomously decide:
- function names, variable names, type hints
- component decomposition and internal file organization
- helper functions and utility abstractions
- error message wording
- small UI layout choices
- test structure within the testing layers defined in ARCHITECTURE.md
- which library import to use when multiple valid options exist

**Stop and flag to the user only when:**
1. The metrics schema (Section 6 of ARCHITECTURE.md) needs to change
2. The WebSocket event schemas (Section 7) need to change
3. A DB table structure (Section 8) needs to add/remove columns
4. A new infrastructure dependency would be added (new Docker service, new DB, new queue)
5. The same error repeats 3 times with different fix attempts and none work
6. A module boundary violation is required to make something work (e.g. simulator.py needing to import chaos.py)

For everything else: make a decision and proceed.

---

# 2. Architecture Protection

ARCHITECTURE.md is locked. You MUST NOT:
- change module responsibilities (simulator vs chaos boundary)
- add Redis Pub/Sub, Celery, Prometheus, or any new infrastructure
- introduce multi-user auth
- change the overlay pipeline order
- bypass the services layer for DB writes

If an implementation path requires any of the above: stop, explain why, propose a simpler alternative that stays within bounds.

---

# 3. Repetition Rule

- First occurrence of a pattern: implement it
- Second occurrence: consider if abstraction helps
- Third occurrence: refactor into shared helper/utility — no exceptions

---

# 4. Failure Recovery Rule

If you hit a blocker:
- Attempt 1: try the obvious fix
- Attempt 2: investigate root cause carefully
- Attempt 3: STOP — do not attempt a third variation. Explain the problem clearly and ask the user.

Do not stack fallback layers. Do not hide errors with broad try/except.

---

# 5. Code Quality Rules

- All timestamps: ISO8601 UTC
- No null metric fields
- No hidden mutable global state
- No silent fallback behavior
- Logs must include timestamps and source module
- Do not spam logs on every scheduler tick
- Prefer explicit code over magic abstractions

---

# 6. Testing Philosophy

Tests exist to guarantee correctness and support the demo, not to inflate coverage numbers.

Priority:
1. Unit tests for alert evaluation, chaos overlay, incident lifecycle, metrics normalization
2. Integration tests for DB + Redis + API interaction
3. WebSocket tests (must use explicit timeout, must teardown cleanly, no infinite listeners)
4. Coverage report output (pytest-cov) is a bonus — include if straightforward

All tests must terminate cleanly and run in CI without manual steps.

Chaos tests validate overlay behavior only — never touch host infrastructure.

---

# 7. Deployment Philosophy

Docker Compose is the only deployment topology. No Kubernetes, no Swarm.

CI/CD pipeline (GitHub Actions) must:
- lint (flake8 + ESLint)
- run unit + integration tests
- build Docker images
- validate Compose startup

A passing pipeline is required. It does not need to auto-deploy to GCP — manual SSH deploy is acceptable.

---

# 8. What "Done" Means

The project is done when a video demo can show:
- real-time metrics updating on the dashboard
- an alert firing and an incident opening
- chaos injection visibly degrading a node
- recovery restoring normal state
- Docker Compose starting cleanly with one command

Tests passing and CI pipeline green are supporting evidence, not the primary goal.
