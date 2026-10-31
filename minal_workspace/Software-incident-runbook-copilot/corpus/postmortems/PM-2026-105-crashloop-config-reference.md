---
doc_id: PM-2026-105
service: checkout-worker
environment: production
version: 2
status: reviewed
owner: runtime-platform
last_reviewed: 2026-10-29
occurred_at: 2026-10-11T07:15:00Z
severity: SEV-3
source_type: postmortem
---

# checkout-worker CrashLoop after configuration reference change

## Impact
Two checkout-worker replicas failed startup for 7 minutes. Remaining replicas processed the event backlog; no event loss was observed.

## Evidence
`K8S-CRASHLOOP` fired after deployment `c204`. Pod events and startup logs identified a missing configuration reference. Cluster scheduling, node health, and resource pressure were normal. No secret values were collected in the incident notes.

## Root cause
A deployment manifest referenced a configuration key that was not present in the production configuration bundle. The issue was a reference mismatch, not a Kubernetes capacity problem.

## Resolution
Runtime Platform and the service owner verified the intended key through the approved configuration workflow, corrected the reference, and waited for readiness and restart metrics to stabilize.

## Lessons
To prevent the same reference mismatch, validate manifest configuration references against the target environment's approved configuration bundle before deployment, and add a rollout check that fails when a required reference is missing. The service owner and Runtime Platform should review changes to those references through the approved workflow. After rollout, watch pod readiness and restart counts. Use termination reasons, startup logs, deployment revision, and config-reference history to distinguish app configuration from cluster resource issues. Never copy secret values into incident chat. See `RB-K8S-003`.
