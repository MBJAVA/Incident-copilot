---
doc_id: PM-2026-103
service: payment-adapter
environment: production
version: 1
status: reviewed
owner: payments-platform
last_reviewed: 2026-10-21
occurred_at: 2026-10-15T16:02:00Z
severity: SEV-2
source_type: postmortem
---

# Regional payment provider timeout increase

## Impact
Authorizations through provider Northstar in one region were delayed for 23 minutes. Requests using the configured idempotency key were reconciled; no duplicate authorization was found.

## Evidence
Provider status showed elevated latency in the affected region. payment-adapter health checks, deployment history, and other providers remained normal. The circuit breaker opened as configured and retries remained bounded.

## Root cause
The external provider had a regional latency incident. There was no evidence of a local payment-adapter release or network configuration change.

## Resolution
Payments Platform kept the circuit breaker and bounded retry policy in place, coordinated with the provider liaison, and resumed normal routing after provider latency recovered. Any fallback routing was authorized by the incident commander.

## Lessons
A timeout does not prove a provider is fully unavailable or that an authorization failed. Compare provider status with local adapter signals and avoid unbounded retries or manual replay. See `RB-PROV-009`.
