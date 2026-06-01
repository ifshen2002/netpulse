# NETPULSE V2 ARCHITECTURE MIGRATION NOTICE (2026-06)

> IMPORTANT:
>
> This notice extends the original architecture.
> It does NOT replace the original architecture.
>
> Existing implementation remains valid unless explicitly marked as:
>
> - \\\[DEPRECATED]
> - \\\[SUPERSEDED]
> - \\\[LEGACY]
> - \\\[REMOVE IN V2]
>
> All migration work must preserve compatibility wherever practical.

\---

# WHY THIS REVISION EXISTS

Supervisor feedback identified a mismatch between:

Project Positioning:

```text
Network Observability Platform
```

and

Actual Monitoring Model:

```text
Node Monitoring Dashboard
```

The original architecture successfully demonstrates:

* realtime telemetry
* alerting
* incidents
* chaos injection
* CI/CD

However, the primary monitored entity is currently:

```text
Node
```

while network observability should primarily focus on:

```text
Probe
Endpoint
Link
Telemetry
Packet Evidence
```

\---

# V1 VS V2

## V1 (Legacy)

Primary Entity:

```text
Node
```

Examples:

```text
node-1
node-2
node-3
```

Primary Metrics:

```text
cpu
memory
disk
latency
packet\\\_loss
```

Node View remains supported.

Node View is now considered a compatibility layer.

\---

## V2 (Primary)

Primary Entities:

```text
Probe
Endpoint
Link
Telemetry Record
Packet Evidence
```

Examples:

```text
Local Probe
↓
8.8.8.8

Local Probe
↓
1.1.1.1

Local Probe
↓
github.com
```

V2 becomes the primary architecture direction.

\---

# NEW ARCHITECTURAL PRINCIPLE

The system must prefer:

```text
Real Network Evidence
```

over:

```text
Synthetic Metric Generation
```

Telemetry must be explainable.

Every displayed metric should be traceable back to:

```text
Actual Probe Activity
```

whenever technically possible.

\---

# PACKET EVIDENCE REQUIREMENT

V2 introduces Packet Evidence.

The dashboard must be capable of displaying evidence of real network probes.

Examples:

```text
Protocol
Source IP
Destination IP
TTL
Packet Size
Timestamp
RTT
```

The goal is to allow operators to verify:

```text
This packet genuinely existed.
This measurement originated from a real probe.
```

\---

# LINK-CENTRIC MONITORING

V2 changes monitoring priority.

Old priority:

```text
Node First
```

New priority:

```text
Link First
```

Node monitoring remains available.

Link monitoring becomes the primary operational view.

\---

# PROBE MODEL

V2 introduces Probe as a first-class entity.

Example:

```text
Probe A
 └─ ICMP → 8.8.8.8

Probe B
 └─ ICMP → 1.1.1.1

Probe C
 └─ HTTP → github.com
```

All telemetry originates from probes.

\---

# CHAOS MIGRATION POLICY

\[SUPERSEDED]

Original overlay-based chaos remains documented for historical reference.

New implementations should prefer:

```text
Isolated Network Chaos
```

using isolated containers and network namespaces.

Goals:

* real packet delay
* real packet loss
* no host destabilization
* no modification of user workstation networking

Additional requirement:

```text
All chaos effects must be confined to isolated probe environments.

Host networking must never be modified directly.
```

Host safety remains non-negotiable.

\---

# MIGRATION MATRIX

|V1 Component|Status|V2 Direction|
|-|-|-|
|Node-1|LEGACY|Probe Host|
|Node-2|DEPRECATED|Public Endpoint|
|Node-3|DEPRECATED|Public Endpoint|
|Synthetic Metrics|DEPRECATED|Real Probe Telemetry|
|Overlay Latency|DEPRECATED|Isolated tc netem|
|Overlay Packet Loss|DEPRECATED|Isolated tc netem|
|Node View|LEGACY|Link View|
|Simulator-Centric Monitoring|DEPRECATED|Probe-Centric Monitoring|

\---

# MIGRATION STRATEGY

When modifying existing code:

1. Preserve existing Node View whenever practical.
2. Introduce Link View as the default operational view.
3. Prefer extending existing modules rather than rewriting them.
4. Mark deprecated components clearly.
5. Maintain demo functionality throughout migration.
6. Preserve working functionality unless explicitly marked for removal.

\---

# NEW DOCUMENTATION ORDER

Read in this order:

1. ARCHITECTURE.md
2. ARCHITECTURE.md V2 sections
3. DECISIONS.md
4. DECISIONS.md V2 sections
5. SPRINT.md

When V1 and V2 appear to conflict:

```text
Follow the migration notes attached to the affected section.
```

Do not remove V1 functionality unless explicitly marked:

```text
\\\[DEPRECATED]
```

or:

```text
\\\[REMOVE IN V2]
```

Migration and compatibility take priority over rewrites.

MANDATORY SESSION START

Before ANY implementation, read these files in order:

1. `ARCHITECTURE.md` — system design + contracts (highest authority)
2. `DECISIONS.md` — your behavior rules
3. `SPRINT.md` — current phase, next action, blockers

If any implementation conflicts with ARCHITECTURE.md: STOP and flag it.

\---

# PROJECT SNAPSHOT

NetPulse — cloud NOC monitoring dashboard for ops teams.

* Node-1: real host metrics (legacy compatibility)
* Node-2/3: legacy simulated nodes retained for migration support
* Primary V2 direction: Probe → Endpoint telemetry
* Stack: FastAPI + PostgreSQL + Redis + React + Nginx + Docker Compose
* Target: GCP e2-micro (1GB RAM, 30GB disk)
* Goal: working demo for recorded video presentation

\---

# YOUR THREE HARD CONSTRAINTS

1. Architecture is locked.  
Do not change system boundaries, module responsibilities, DB schema shape, or WebSocket event schemas without flagging first.
2. Autonomous by default.  
Make decisions independently on: function names, variable names, component structure, internal logic, file organization within a module, small UI choices. Only flag the situations listed in DECISIONS.md.
3. File structure discipline.  
Max 5 items per folder level. Keep nesting shallow. Follow the structure in ARCHITECTURE.md Section 15.

\---

# PRIORITY ORDER

When documents conflict:

1. ARCHITECTURE.md
2. DECISIONS.md
3. SPRINT.md

\---

# DEMO TARGET (NOT NEGOTIABLE)

The system must be recordable as a video demo showing:

* real probe telemetry updating in real time
* packet evidence visible on dashboard
* alert firing and incident opening
* chaos injection visibly affecting dashboard
* recovery restoring normal state

Legacy Node View demonstrations remain acceptable during migration.

This is the definition of done. Tests and CI/CD support this goal, not the reverse.



