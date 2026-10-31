---
doc_id: RB-CHK-002
service: checkout-api
environment: production
version: 4
status: active
owner: commerce-platform
last_reviewed: 2026-10-19
source_type: runbook
---

# Checkout API elevated 5xx

## Alert meaning
`CHECKOUT-5XX` fires when the checkout-api 5xx rate exceeds 3% for 5 minutes. It signals failed requests, not a specific root cause. Customer impact depends on endpoint, region, and duration.

## Triage
1. Confirm affected region, endpoint, request volume, and 5xx trend.
2. Compare checkout-api error rate with dependency latency/errors for payment-adapter, inventory-service, and session-cache.
3. Check traces for the failing span and the first failing dependency.
4. Review recent deployments and configuration changes by service and region.
5. Compare successful and failed request paths; do not assume all 5xx responses share one cause.

## Recovery decision
If failures began directly after a checkout-api deployment, correlate the failing code path with the release and follow `POL-CHANGE-004` for an approved rollback.

If a downstream dependency is failing, follow that dependency's runbook and keep checkout retries bounded. Do not roll back checkout-api solely because its 5xx alert fired when evidence points to a dependency.

If the first failing component is unknown, preserve request IDs and traces, page Commerce Platform on-call, and avoid simultaneous changes to multiple services.

## Verification
Confirm the 5xx rate is below threshold, checkout success rate recovers, dependency health is stable, and customer-impact indicators improve for 15 minutes.

## Prohibited initial actions
Do not disable authentication, bypass payment or inventory checks, or increase retries without identifying the failure path and obtaining incident approval.

## Escalation
Commerce Platform owns checkout-api. Page the owner of the first failing dependency as identified by traces. See `OWNERS-005`.
