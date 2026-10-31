---
doc_id: PM-2026-104
service: checkout-api
environment: production
version: 1
status: reviewed
owner: commerce-platform
last_reviewed: 2026-10-20
occurred_at: 2026-10-16T11:40:00Z
severity: SEV-2
source_type: postmortem
---

# Checkout 5xx caused by inventory dependency latency

## Impact
The checkout-api 5xx rate exceeded 3% for 9 minutes in one region. Some customers had to retry checkout; order records remained consistent.

## Timeline and evidence
- `CHECKOUT-5XX` fired at 11:40 UTC.
- Traces showed inventory-service as the first failing span; checkout-api itself had no new deployment.
- inventory-service latency rose after a separate database maintenance event.
- Payment-adapter and session-cache health remained normal.

## Root cause
Inventory-service requests exceeded the checkout-api dependency timeout. The API returned 5xx for affected requests; the alerting service was the symptom, not the root cause.

## Resolution
The inventory owner restored normal query latency under the approved maintenance plan. Commerce Platform verified checkout success rate and error rate recovery. No checkout-api rollback was performed.

## Lessons
Trace the failing request to the first failing dependency before proposing a rollback. Keep retries bounded and follow the owner of the failing component. See `RB-CHK-002` and `ARCH-FLOW-002`.
