---
doc_id: PM-2026-101
service: checkout-worker
environment: production
version: 1
status: reviewed
owner: payments-platform
last_reviewed: 2026-10-20
occurred_at: 2026-10-18T14:22:00Z
severity: SEV-2
source_type: postmortem
---

# Consumer lag after checkout-worker release

## Impact
Checkout confirmations were delayed for a subset of customers for 18 minutes. The event audit found no lost payment or order events.

## Timeline
- 14:22 UTC: `PAY-QUEUE-LAG` fired for checkout-worker.
- 14:27 UTC: Consumer errors and restarts rose after release `8f31`.
- 14:34 UTC: Service owner approved rollback under the incident commander.
- 14:40 UTC: Lag began draining and confirmation latency recovered.

## Root cause
Release `8f31` changed a consumer configuration value. Pods repeatedly restarted, reducing the active consumer count. Kafka brokers remained healthy.

## Resolution
The service owner rolled back to the previous healthy revision. The team verified lag, event age, and checkout confirmation latency before resolving the incident.

## Lessons
For `PAY-QUEUE-LAG`, correlate consumer restarts and release timing before treating backlog as a broker-capacity problem. Do not alter offsets or replay events as an initial step. See `RB-PAY-014`.

## Follow-up
Add startup validation for the consumer configuration and a dashboard panel for active consumers by partition.
