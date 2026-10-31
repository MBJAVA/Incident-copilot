---
doc_id: ARCH-SVC-001
service: platform
environment: production
version: 1
status: active
owner: architecture-council
last_reviewed: 2026-10-22
source_type: architecture
---

# HarborPay production service map

## Scope
HarborPay is a fictional commerce and payments platform used only for this learning corpus. All services, telemetry, and incident details are synthetic.

## Services and ownership
| Component | Responsibility | Primary owner | Dependencies |
|---|---|---|---|
| checkout-api | Accepts checkout requests and coordinates order creation | Commerce Platform | order-db, payment-adapter, inventory-service, session-cache |
| payment-adapter | Calls external payment providers and normalizes responses | Payments Platform | provider endpoints, payments-events |
| checkout-worker | Consumes order/payment events and updates checkout state | Payments Platform | payments-events, order-db |
| inventory-service | Reserves and releases inventory | Commerce Platform | inventory-db, payments-events |
| session-cache | Stores short-lived session and cart state | Commerce Platform; Runtime Platform owns shared Redis | Redis cluster |
| order-db | Stores order and checkout state | Database on-call | PostgreSQL cluster |
| payments-events | Kafka topic set for payment and checkout events | Payments Platform; Runtime Platform owns brokers | Kafka cluster |

## Request path
A client request reaches checkout-api. The API validates the request, reads session state, creates an order record, asks payment-adapter to authorize payment, and coordinates inventory reservation. Domain events are published to payments-events. checkout-worker consumes those events to advance asynchronous state and notify downstream systems.

## Reliability boundaries
- checkout-api 5xx may originate in the API or a downstream dependency. Use request traces to identify the first failing span.
- Kafka consumer lag indicates delayed processing, not automatically event loss.
- Application pool saturation and database server saturation are different signals and have different owners.
- Redis miss ratio is not equivalent to Redis service failure; inspect errors, evictions, and backing-store load.

## Ownership authority
`OWNERS-005` is the escalation map. This document describes architecture ownership only; for incident paging, use the current owner map and incident commander direction.
