---
doc_id: RB-PAY-014
service: checkout-worker
environment: production
version: 3
status: active
owner: payments-platform
last_reviewed: 2026-10-20
source_type: runbook
---

# Kafka consumer lag

## Alert meaning
`PAY-QUEUE-LAG` fires when the `checkout-worker` consumer group's lag on `payments-events` exceeds 5,000 messages for 10 minutes. Lag means events are waiting to be processed; it does not by itself prove that events were lost.

## Triage
1. Confirm the service, consumer group, topic, and affected partitions from the alert.
2. Compare lag over time. A rising lag is different from a backlog that is already draining.
3. Check consumer error rate, restart count, recent deployment/configuration changes, and Kafka broker health.
4. Compare partition count and active consumer count. Do not infer a capacity problem from total lag alone.
5. Check the event-age metric and checkout confirmation latency to understand customer impact.

## Recovery decision
If consumer errors and restarts began immediately after a `checkout-worker` deployment, follow `POL-CHANGE-004` and request the service owner to roll back the last known-good deployment. Verify the rollback is approved and the target version is known before changing production.

If lag is rising but no deployment correlation or consumer error is established, do not scale consumers or alter partition assignments yet. Escalate to Payments Platform on-call with the affected partitions, lag trend, consumer errors, and broker health.

## Verification
Confirm lag is decreasing across affected partitions, event age is within the service objective, consumer restarts have stopped, and checkout confirmation latency has recovered. Continue monitoring for 15 minutes after recovery.

## Prohibited initial actions
Do not purge, skip, or replay messages as a first response. Do not increase partitions or change consumer offsets without an approved incident plan; these actions can alter ordering or duplicate processing.

## Escalation
Page Payments Platform on-call if lag continues to rise after an approved rollback, broker health is degraded, or event loss/duplication is suspected. Follow `OWNERS-005` for escalation contacts.
