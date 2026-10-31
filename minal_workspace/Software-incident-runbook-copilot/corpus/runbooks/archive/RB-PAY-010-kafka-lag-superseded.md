---
doc_id: RB-PAY-010
service: checkout-worker
environment: production
version: 1
status: superseded
owner: payments-platform
last_reviewed: 2024-03-01
superseded_by: RB-PAY-014
source_type: runbook
---

# Archived Kafka lag procedure - superseded

This historical procedure is retained only for retrieval-freshness evaluation. It is not approved for current production use.

The former procedure suggested increasing consumer replicas immediately when lag exceeded 2,000 messages. That advice was replaced because lag alone does not establish that more consumers are safe or useful; partition count, consumer errors, broker health, and recent changes must first be checked.

Do not follow this archived procedure. Use active `RB-PAY-014` and current incident policy instead.
