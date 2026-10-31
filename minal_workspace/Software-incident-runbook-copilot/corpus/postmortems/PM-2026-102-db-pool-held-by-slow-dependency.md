---
doc_id: PM-2026-102
service: checkout-api
environment: production
version: 1
status: reviewed
owner: commerce-platform
last_reviewed: 2026-10-19
occurred_at: 2026-10-12T09:10:00Z
severity: SEV-2
source_type: postmortem
---

# Checkout database pool saturation during inventory latency

## Impact
Checkout requests intermittently timed out for 11 minutes. PostgreSQL remained within its normal CPU and active-connection range.

## Evidence and timeline
- 09:10 UTC: `DB-POOL-SATURATION` fired on checkout-api.
- Database CPU, lock waits, and server connections stayed near baseline.
- Traces showed requests waiting on inventory-service while holding application database connections.
- No checkout-api deployment occurred in the incident window.

## Root cause
A latency increase in inventory-service extended request duration. The checkout-api request path held a database connection while awaiting the dependency, exhausting the application pool. The database server itself was not saturated.

## Resolution
Commerce Platform reduced the affected request path's connection-hold duration through an approved configuration change after confirming inventory-service recovery. Pool wait time and checkout errors returned to baseline.

## Lessons
Application pool saturation is not proof of database server saturation. Compare application wait metrics with database CPU, active connections, locks, and dependency traces. Raising the pool limit without evidence could have shifted overload to PostgreSQL. See `RB-DB-006`.
