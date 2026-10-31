---
doc_id: POL-CHANGE-004
service: platform
environment: production
version: 1
status: active
owner: sre
last_reviewed: 2026-10-22
source_type: policy
---

# Production change and rollback policy

## Authority
The incident commander coordinates high-severity response. The service owner approves service-specific changes. Database, Runtime Platform, Security, or provider owners must approve changes within their control boundary.

## Rollback criteria
A rollback may be proposed when evidence links a recent release/configuration change to the symptom, the target revision is known and healthy, and the service owner confirms rollback is safer than the current state. The incident commander coordinates timing and communications.

## Assistant boundaries
The incident copilot may summarize evidence, cite applicable policy/runbooks, identify missing checks, and draft a rollback checklist. It must not execute a rollback, change a feature flag, scale a service, change a database limit, modify Kafka offsets, replay a payment, or alter production configuration.

Any action proposal must state the evidence, expected effect, risk, owner/approver, and verification plan. If an action is not covered by an approved runbook or policy, the assistant must not invent steps; escalate to the responsible on-call owner.

## Sensitive information
Never share secrets, credentials, payment details, or customer-identifying data in generated summaries. Use approved internal observability and secret-management systems.
