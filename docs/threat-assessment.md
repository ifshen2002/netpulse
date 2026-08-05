# Threat Assessment — NetPulse Observability Platform

> Based on security audit conducted 2026-08-04. All findings tracked to mitigation status.

## Methodology

Reviewed against **STRIDE** model (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) across trust boundaries:

1. Browser ↔ Nginx (public internet)
2. Nginx ↔ Backend (container network)
3. Backend ↔ PostgreSQL / Redis (container network)
4. Backend ↔ External targets (ICMP probes)

## Threat Inventory

### T1. Spoofing — Session Token Theft

| Attribute | Detail |
|---|---|
| **STRIDE** | Spoofing |
| **Asset** | User session |
| **Threat** | Attacker steals session token via XSS (token in localStorage) or log leakage (token in WebSocket URL query string) |
| **Severity** | High |
| **Mitigation** | CSP header blocks inline scripts; nginx access_log strips query strings (`noquery` format); `Content-Security-Policy` in nginx.conf |
| **Residual Risk** | Low — CSP is a secondary defense; token in localStorage remains a concern in production |
| **Status** | ✅ Mitigated for demo |

### T2. Tampering — Cross-Project Resource Modification (IDOR)

| Attribute | Detail |
|---|---|
| **STRIDE** | Tampering |
| **Asset** | alert_rules, endpoint resources |
| **Threat** | Attacker in project A modifies/deletes alert rules or injects chaos on endpoints belonging to project B by guessing resource IDs |
| **Severity** | Critical |
| **Mitigation** | `project_clause()` applied to all mutation endpoints (update, delete, toggle) for alert_rules, chaos inject/recover, subscriptions |
| **Residual Risk** | Low — all write paths verified with project_id |
| **Status** | ✅ Fixed — 2026-08-05 |

### T3. Information Disclosure — Cross-Tenant WebSocket Broadcast

| Attribute | Detail |
|---|---|
| **STRIDE** | Information Disclosure |
| **Asset** | Telemetry data, alerts, notifications |
| **Threat** | Authenticated user in any project receives all projects' metrics, packet evidence (including internal IPs), alerts, and notifications via unfiltered WebSocket broadcast |
| **Severity** | Critical |
| **Mitigation** | `ConnectionManager.broadcast()` now accepts `project_id` and `user_id` filters; all call sites pass appropriate scope |
| **Residual Risk** | Low — V1 legacy node events remain global (synthetic data only) |
| **Status** | ✅ Fixed — 2026-08-05 |

### T4. Information Disclosure — SSRF via Endpoint Creation

| Attribute | Detail |
|---|---|
| **STRIDE** | Information Disclosure |
| **Asset** | Internal network, cloud metadata |
| **Threat** | Editor creates endpoint targeting 10.0.0.0/8, 169.254.169.254, or other private IP; scheduler executes ICMP ping against internal infrastructure every 5 seconds |
| **Severity** | High |
| **Mitigation** | `_is_private_ip()` blocks all RFC 1918, link-local, CGNAT, multicast, and reserved IPv4 ranges; `ping --` separator prevents option injection |
| **Residual Risk** | Medium — hostnames that resolve to private IPs at runtime not blocked (DNS resolution depends on container's resolver) |
| **Status** | ✅ Mitigated for demo |

### T5. Elevation of Privilege — First-User Admin Bootstrap

| Attribute | Detail |
|---|---|
| **STRIDE** | Elevation of Privilege |
| **Asset** | Platform admin role |
| **Threat** | First user to register on an unseeded deployment becomes platform_admin with full system control |
| **Severity** | High |
| **Mitigation** | `NETPULSE_ADMIN_EMAIL` env var explicitly designates the admin; warning logged if unset |
| **Residual Risk** | Medium — if env var is unset in production, first registrant still becomes admin (backward compat dev mode) |
| **Status** | ✅ Mitigated |

### T6. Denial of Service — Unbounded Resource Creation

| Attribute | Detail |
|---|---|
| **STRIDE** | Denial of Service |
| **Asset** | System availability |
| **Threat** | Attacker creates N endpoints → N ping subprocesses every 5 seconds → CPU/memory exhaustion; WebSocket connection flooding; login brute force |
| **Severity** | Medium |
| **Mitigation** | Nginx rate limits (5r/m login, 3r/m register); Docker mem_limit on all services; `client_max_body_size 1m`; query parameter bounds (seconds: 10-3600, limit: 1-500) |
| **Residual Risk** | Low — single VM, authenticated-only endpoint creation |
| **Status** | ✅ Mitigated for demo |

### T7. Repudiation — Missing Audit Trail

| Attribute | Detail |
|---|---|
| **STRIDE** | Repudiation |
| **Asset** | User accountability |
| **Threat** | User performs destructive action that cannot be traced |
| **Severity** | Low |
| **Mitigation** | `audit_logs` table records every privileged action with actor, resource type, resource ID, project, organization, timestamp; 100% of mutation routes call `audit()` |
| **Residual Risk** | Low — audit logs are append-only, retained indefinitely |
| **Status** | ✅ Implemented |

### T8. Elevation of Privilege — Subscription Without Membership

| Attribute | Detail |
|---|---|
| **STRIDE** | Elevation of Privilege |
| **Asset** | Notification data |
| **Threat** | Any authenticated user subscribes to any project and receives its alert notifications |
| **Severity** | High |
| **Mitigation** | `create_subscription` now verifies project membership before allowing subscription creation |
| **Residual Risk** | Low |
| **Status** | ✅ Fixed — 2026-08-05 |

## Risk Matrix

```
                    Likelihood
                    Low       Medium    High
Impact  Critical    —         T2, T3    —
        High        T5        T1, T4    T8
        Medium      —         T6        —
        Low         T7        —         —
```

## Security Controls Summary

| Layer | Controls |
|---|---|
| **Edge** | Nginx TLS 1.2+, HSTS, CSP, X-Frame-Options, rate limiting, request size cap |
| **Application** | scrypt password hashing, SHA-256 session tokens, RBAC (3 roles), project_clause() isolation, input validation (Pydantic), SSRF IP filtering, error sanitization |
| **Data** | AES-256 in transit (TLS), parameterized SQL (no injection), immutable audit logs |
| **Infrastructure** | Docker isolation, no exposed DB/Redis ports, resource limits, daily backups (7-day retention), non-root where possible |
| **CI/CD** | SAST (Bandit), DAST (OWASP ZAP), Container Scan (Trivy), automated testing (43 unit + 28 integration + 14 e2e) |
