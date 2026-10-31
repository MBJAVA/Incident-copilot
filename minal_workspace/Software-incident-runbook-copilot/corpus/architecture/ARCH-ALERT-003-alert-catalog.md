---
doc_id: ARCH-ALERT-003
service: platform
environment: production
version: 2
status: active
owner: sre
last_reviewed: 2026-10-29
source_type: architecture
---

# Alert catalog and signal semantics

## PAY-QUEUE-LAG
Service: checkout-worker. Fires when payments-events consumer lag exceeds 5,000 messages for 10 minutes. Signal: backlog. It does not prove loss, duplicate processing, or broker failure. Runbook: `RB-PAY-014`.

## DB-POOL-SATURATION
Service: checkout-api. Fires when application connection-pool utilization is above 90% for 5 minutes or connection acquisition timeouts exceed threshold. Signal: application pool pressure. It does not prove PostgreSQL server saturation. Runbook: `RB-DB-006`.

## PAY-PROVIDER-TIMEOUT
Service: payment-adapter. Fires when the provider request timeout rate exceeds 10% for 5 minutes, measured per provider and region. Signal: provider request latency/failure. It does not prove the provider is down; compare provider status and local adapter evidence. Runbook: `RB-PROV-009`.

## CHECKOUT-5XX
Service: checkout-api. Fires when checkout-api 5xx rate exceeds 3% for 5 minutes. Signal: failed HTTP requests. It does not identify the failing component. Runbook: `RB-CHK-002`.

## K8S-CRASHLOOP
Service: checkout-worker. Fires when one or more pods repeatedly fail readiness/startup. Signal: pod restart/startup issue. It does not distinguish app defect, configuration, dependency, or resource cause. Runbook: `RB-K8S-003`.

## CACHE-MISS-SURGE
Service: session-cache. Fires when miss ratio and backing-store request rate cross configured thresholds. Signal: cache effectiveness/load. It does not prove Redis is unavailable. Runbook: `RB-CACHE-005`.

## Interpretation rule
Alert names and thresholds in this synthetic catalog are authoritative only for this corpus. In a real system, query the live alert definition and current telemetry; do not assume a copied threshold is current.
