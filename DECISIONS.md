DECISIONS.md — AI Behavior Rules
> This file defines how Claude Code behaves during implementation.
> System design lives in ARCHITECTURE.md. Execution state lives in SPRINT.md.
---
0. V2 Migration Principles
V2 introduces a link-centric probe model and stricter truthfulness requirements for telemetry.
These principles apply whenever V2 work is being implemented:
Real telemetry before visualizations.
Simplicity before resilience.
Complete the current step before starting the next step.
Evidence before metrics.
No hidden recovery.
Do not invent a source for a metric after defining the metric.
Do not mix legacy node telemetry and V2 probe telemetry in the same data path.
If a task can be completed cleanly without adding abstraction, fallback layers, retry chains, or defensive wrappers, prefer the simpler implementation.
Fixed Logic, Configurable Policy.
  — Measurement logic (probe interval, metric formulas, packet evidence generation, alert evaluation logic, incident lifecycle, status classification) is FIXED and cannot be changed from the UI.
  — Operational policy (alert thresholds, display windows, probe endpoints, chaos parameters) is CONFIGURABLE from the UI with sensible defaults.
  — Users can change what thresholds trigger alerts but cannot change how the platform calculates telemetry.
---
1. Autonomy Model
Default: decide independently.
You may autonomously decide:
function names, variable names, type hints
component decomposition and internal file organization
helper functions and utility abstractions
error message wording
small UI layout choices
test structure within the testing layers defined in ARCHITECTURE.md
which library import to use when multiple valid options exist
Stop and flag to the user only when:
The metrics schema (Section 6 of ARCHITECTURE.md) needs to change
The WebSocket event schemas (Section 7) need to change
A DB table structure (Section 8) needs to add/remove columns
A new infrastructure dependency would be added (new Docker service, new DB, new queue)
The same error repeats 3 times with different fix attempts and none work
A module boundary violation is required to make something work (e.g. simulator.py needing to import chaos.py)
A V2 telemetry value cannot be explained from a concrete probe action or derived aggregation
For everything else: make a decision and proceed.
V2 note: if a change would require inventing synthetic telemetry, do not proceed; stop and redesign the path to use real probe-derived evidence.
---
2. Architecture Protection
ARCHITECTURE.md is locked. You MUST NOT:
change module responsibilities (simulator vs chaos boundary)
add Redis Pub/Sub, Celery, Prometheus, or any new infrastructure
introduce multi-user auth
change the overlay pipeline order
bypass the services layer for DB writes
add passive packet sniffing, tcpdump-style capture, or host-level packet interception for V2
mix legacy node metrics with V2 probe telemetry in a single pipeline
If an implementation path requires any of the above: stop, explain why, propose a simpler alternative that stays within bounds.
V2 implementation rule: use the existing stack and add only the minimum necessary code paths to support probe telemetry, packet evidence, and isolated network chaos.
---
3. Repetition Rule
First occurrence of a pattern: implement it
Second occurrence: consider if abstraction helps
Third occurrence: refactor into shared helper/utility — no exceptions
Do not introduce abstraction early just because a future path might need it.
---
4. Failure Recovery Rule
If you hit a blocker:
Attempt 1: try the obvious fix
Attempt 2: investigate root cause carefully
Attempt 3: STOP — do not attempt a third variation. Explain the problem clearly and ask the user.
Do not stack fallback layers.
Do not hide errors with broad try/except.
Do not add retry chains, recovery managers, or shadow fallback behaviors unless ARCHITECTURE.md explicitly requires them.
V2 note: failure should remain visible and explainable in telemetry and logs rather than being masked by silent recovery logic.
---
5. Code Quality Rules
All timestamps: ISO8601 UTC
No null metric fields
No hidden mutable global state
No silent fallback behavior
Logs must include timestamps and source module
Do not spam logs on every scheduler tick
Prefer explicit code over magic abstractions
Zustand selectors MUST NOT create new object/array references. Use module-level frozen constants for defaults (e.g. `EMPTY_ARR = Object.freeze([])`, `EMPTY_OBJ = Object.freeze({})`). Creating `[]` or `{}` inside a selector causes infinite re-render loops because `useSyncExternalStore` uses `Object.is` comparison, and `[] !== []`.
For V2 telemetry, every value must be explainable from a concrete probe action, packet evidence, or a clearly stated aggregation window.
Do not create a metric first and later invent a source for it.
Prefer the simplest correct implementation over a more resilient but more complex one.
Do not add defensive layers that only exist to hide uncertainty.
---
6. Testing Philosophy
Tests exist to guarantee correctness and support the demo, not to inflate coverage numbers.
Priority:
Unit tests for alert evaluation, chaos overlay, incident lifecycle, metrics normalization, and V2 telemetry explainability
Integration tests for DB + Redis + API interaction
WebSocket tests (must use explicit timeout, must teardown cleanly, no infinite listeners)
Coverage report output (pytest-cov) is a bonus — include if straightforward
All tests must terminate cleanly and run in CI without manual steps.
Chaos tests validate overlay behavior only — never touch host infrastructure.
V2 testing note: probe telemetry tests should verify that values are derived from real probe runs or from explicit aggregations of those runs, not from arbitrary random generation.
---
7. Deployment Philosophy
Docker Compose is the only deployment topology. No Kubernetes, no Swarm.
CI/CD pipeline (GitHub Actions) must:
lint (flake8 + ESLint)
run unit + integration tests
build Docker images
validate Compose startup
A passing pipeline is required. It does not need to auto-deploy to GCP — manual SSH deploy is acceptable.
V2 deployment note: do not add infrastructure services merely to make the V2 model easier; stay within the existing deployment shape unless ARCHITECTURE.md explicitly changes it.
---
8. What "Done" Means
The project is done when a video demo can show:
real-time metrics updating on the dashboard
an alert firing and an incident opening
chaos injection visibly degrading a node
recovery restoring normal state
Docker Compose starting cleanly with one command
Tests passing and CI pipeline green are supporting evidence, not the primary goal.
V2 note: when the V2 path is being demonstrated, the demo must also show:
real probe telemetry updating in real time
packet evidence visible on the dashboard
link-centric monitoring as the default view
historical aggregation behaving correctly over the configured windows
isolated chaos affecting only the probe environment