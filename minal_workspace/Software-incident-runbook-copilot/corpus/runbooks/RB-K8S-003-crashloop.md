---
doc_id: RB-K8S-003
service: checkout-worker
environment: production
version: 3
status: active
owner: runtime-platform
last_reviewed: 2026-10-29
source_type: runbook
---

# Kubernetes CrashLoopBackOff

## Alert meaning
`K8S-CRASHLOOP` fires when one or more checkout-worker pods repeatedly fail to become ready. CrashLoopBackOff is a symptom; it does not by itself identify whether the cause is application startup, configuration, dependency access, or resource pressure.

## Triage
1. Confirm cluster, namespace, deployment, affected replica count, and first failure time.
2. Inspect the pod termination reason and recent application startup logs using the approved observability interface.
3. Check readiness/liveness probe failures, resource-limit events, and scheduling events.
4. Compare the deployment revision and configuration/secret reference changes with the last healthy revision.
5. Verify dependency health only if startup evidence indicates a dependency connection failure.

## Recovery decision
If the failure began after a deployment and evidence points to an invalid application configuration, ask the service owner to use the approved rollback process in `POL-CHANGE-004`.

If a required secret or configuration reference is missing, do not print or copy secret values into chat. Escalate to the secret owner and Runtime Platform; repair must use the approved secret-management workflow.

If pods are unscheduled due to resource pressure or cluster health, page Runtime Platform. Do not increase resource limits without capacity evidence and approval.

## Verification
Confirm new pods become ready, restart count remains stable, health checks pass, and service-level error/latency metrics recover for 15 minutes.

## Prevention
Before rolling out a deployment manifest that changes configuration or secret references, validate that each referenced key exists in the target environment's approved configuration bundle. The service owner and Runtime Platform should review changed references through the approved configuration or secret-management workflow without exposing secret values.

Add a deployment validation check that fails when a required reference is missing. After rollout, monitor startup logs, pod readiness, and restart counts; if configuration validation fails, stop the rollout and follow the approved rollback process.

## Prohibited initial actions
Do not expose secret values, delete persistent resources, or repeatedly restart pods without addressing the observed startup failure.

## Escalation
Runtime Platform owns cluster and scheduling failures. The application team owns application startup defects. See `OWNERS-005`.
