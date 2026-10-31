---
doc_id: RB-DB-006
service: checkout-api
environment: production
version: 2
status: active
owner: commerce-platform
last_reviewed: 2026-10-18
source_type: runbook
---

# Checkout database connection pool saturation

## Alert meaning
`DB-POOL-SATURATION` fires when `checkout-api` database pool utilization remains above 90% for 5 minutes or acquisition timeouts exceed the alert threshold. This is an application-pool signal; it does not prove that the database server is out of capacity.

## Triage
1. Confirm the affected application instances, pool utilization, acquisition wait time, and timeout rate.
2. Compare database CPU, active connections, query latency, and lock waits with their recent baseline.
3. Check application releases, traffic changes, and traces for long-running requests or connections not being returned.
4. Determine whether saturation is isolated to one deployment/instance or is service-wide.
5. Check whether a dependency slowdown is keeping transactions open longer than usual.

## Recovery decision
If pool saturation started with a release and traces show connections held by the new code path, follow `POL-CHANGE-004` and ask the service owner to roll back the release.

If database CPU and active connections are healthy but application acquisition waits rise, investigate connection lifecycle and slow dependency calls. Do not raise the pool limit based only on utilization: that can overload the database and worsen contention.

If database CPU, active connections, or lock waits are also abnormal, escalate to Database on-call before changing pool or database limits.

## Verification
Confirm pool utilization and acquisition waits return to their normal range, database health remains stable, request errors decline, and no elevated connection count persists for 15 minutes.

## Prohibited initial actions
Do not terminate database sessions, increase database maximum connections, or restart the database based on this alert alone. Those actions require Database on-call and an approved incident plan.

## Escalation
Escalate to Commerce Platform for application-level connection leaks and Database on-call for server saturation, lock contention, or uncertain ownership. See `OWNERS-005`.
