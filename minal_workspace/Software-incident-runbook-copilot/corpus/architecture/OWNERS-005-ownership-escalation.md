---
doc_id: OWNERS-005
service: platform
environment: production
version: 1
status: active
owner: sre
last_reviewed: 2026-10-22
source_type: ownership
---

# Service ownership and escalation

## Primary owners
- Commerce Platform: checkout-api, inventory-service, application session-cache behavior.
- Payments Platform: payment-adapter, checkout-worker, payment provider liaison, payments-events consumer group.
- Database on-call: PostgreSQL cluster health, server connections, query locks, database capacity.
- Runtime Platform: Kubernetes cluster, scheduling, node health, shared Redis service health, Kafka broker health.
- SRE: alert definitions, incident process, incident commander rotation, production change policy.

## Escalation rules
1. Follow the first failing component in a trace or the owner identified by the relevant telemetry, not merely the service that emitted a symptom alert.
2. If ownership is ambiguous, page the incident commander/SRE and include alert ID, service, environment, time window, evidence, and runbook IDs consulted.
3. For suspected data loss, duplicate payment, credential exposure, or security impact, escalate immediately to the incident commander and the relevant specialist owner.
4. This synthetic file has no real contact names or paging handles. In production, resolve contacts from the live on-call system; never fabricate a person or destination.
