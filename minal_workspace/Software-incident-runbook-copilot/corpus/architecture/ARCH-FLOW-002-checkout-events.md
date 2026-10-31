---
doc_id: ARCH-FLOW-002
service: checkout-api
environment: production
version: 2
status: active
owner: commerce-platform
last_reviewed: 2026-10-21
source_type: architecture
---

# Checkout and payment event flow

## Synchronous path
1. checkout-api validates the request and reads session-cache.
2. checkout-api writes a pending order to order-db.
3. payment-adapter calls the selected provider with an idempotency key.
4. checkout-api records the authorization result and requests inventory reservation.
5. The API returns the appropriate checkout response.

## Asynchronous path
Payment and order state changes publish events to `payments-events`. checkout-worker consumes events and updates order state. Consumers are expected to be idempotent. Event order is guaranteed only within a Kafka partition, not across all partitions.

## Failure interpretation
- Provider timeout does not prove authorization failed. Repeating a request without the same idempotency key can create a duplicate authorization.
- Consumer lag means events are queued. Verify event age and consumer health before concluding customers are affected.
- A checkout-api 5xx should be traced to the first failing component; the API may be reporting a dependency failure.
- A pending order may be temporarily correct while asynchronous work is in progress. Check the state transition and age before intervention.

## Safe diagnostic evidence
Use the incident's request IDs, trace IDs, event IDs, timestamps, and service-level telemetry. Do not paste payment credentials, customer names, card data, or raw authorization payloads into an assistant prompt.
