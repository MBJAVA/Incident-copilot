---
doc_id: RB-PROV-009
service: payment-adapter
environment: production
version: 2
status: active
owner: payments-platform
last_reviewed: 2026-10-29
source_type: runbook
---

# Payment provider timeout increase

## Alert meaning
`PAY-PROVIDER-TIMEOUT` fires when the timeout rate for payment-adapter requests to one provider in one region exceeds 10% for 5 minutes. Provider timeouts can be transient, regional, or caused by a local network or release issue; the alert alone does not identify the cause.

## Triage
1. Confirm the provider, region, request type, error rate, and latency percentiles from the incident snapshot.
2. Compare the provider status signal with payment-adapter latency and errors.
3. Check whether failures affect all providers or only one provider/region.
4. Review retry count, circuit-breaker state, queue depth, and recent adapter deployments.
5. Check for duplicate authorization risk before retrying any payment request.

## Recovery decision
If the provider status signal is degraded and local adapter health is normal, keep the configured circuit breaker and bounded retries in place, route new traffic only through an already-approved fallback if the incident commander authorizes it, and contact the provider liaison.

If local errors began after an adapter release, follow `POL-CHANGE-004` and request an approved rollback. Do not raise timeout or retry limits to mask an unresolved dependency failure.

## Verification
Confirm provider latency and timeout rate are recovering, circuit-breaker state is stable, retry volume is bounded, and payment reconciliation shows no duplicate authorizations. Monitor for 15 minutes.

## Prohibited initial actions
Do not disable the circuit breaker, issue unbounded retries, or manually replay payment requests. These can amplify load or create duplicate financial operations.

## Escalation
Page Payments Platform on-call and notify the incident commander for sustained provider errors or customer-impacting payment failures. Use `OWNERS-005` for the provider liaison path.
