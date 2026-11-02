---
doc_id: RB-CACHE-005
service: session-cache
environment: production
version: 2
status: active
owner: commerce-platform
last_reviewed: 2026-11-02
source_type: runbook
---

# Redis cache miss surge

## Alert meaning
`CACHE-MISS-SURGE` fires when session-cache miss ratio and backing-store request rate exceed their alert thresholds. A miss surge may follow key expiry, invalidation, traffic changes, or cache service degradation.

## Triage
1. Confirm affected key namespace, region, miss ratio, request rate, and Redis health.
2. Compare miss timing with deployments, invalidations, TTL changes, and traffic changes.
3. Check backing-store latency and saturation before increasing cache refill concurrency.
4. Determine whether misses are isolated to one namespace or broad across the service.
5. Review cache error rate and evictions; a high miss ratio alone does not establish Redis failure.

## Recovery decision
If a synchronized expiry or invalidation is confirmed and Redis is healthy, ask the service owner to apply the approved gradual refill or TTL-jitter mitigation using the procedure below. Watch backing-store capacity during recovery.

If Redis errors or evictions are elevated, page the cache owner before changing application TTL or refill behavior.

## Gradual key refill procedure
Use this procedure only after the Recovery decision conditions are met and the Commerce Platform service owner approves the scope and method. This runbook does not define a production refill command, endpoint, key format, or numeric rate limit; obtain those from the service-owned implementation before acting. Do not use a raw Redis write or an unreviewed script.

1. Identify the affected region and key namespace from approved cache-miss telemetry. Select a small, bounded set of currently missing keys; keep key identifiers in approved internal tools rather than pasting them into incident chat.
2. Confirm that each selected key's value can be reconstructed from an authoritative backing-store record. If the backing record is absent, expired, or not authoritative for that session or cart state, skip the key; never fabricate a value.
3. Record baseline miss ratio, backing-store request rate and latency, Redis errors and evictions, and session lookup latency. Agree with the service owner on the canary size, maximum refill rate, concurrency, TTL and jitter settings, and stop thresholds using current capacity evidence; this runbook supplies no default numbers.
4. Use the service owner's approved application refill job or cache-aside read path. For each canary key, read the current backing record, serialize it through the application's normal cache-writing path, and write only if the key is still absent so a newer value is not overwritten. Apply the approved TTL with jitter; do not extend the lifetime of expired session data.
5. Recheck the metrics after the canary, then expand in bounded batches only while Redis and the backing store remain healthy. Stop the refill and page Commerce Platform if backing-store load or latency, Redis errors or evictions, or session latency worsens; page Runtime Platform for shared Redis health issues. Do not flush or broadly invalidate the cache.
6. After the last batch, follow Verification below. Record the affected namespace, approved method, batch scope, observed metric changes, and any keys skipped; do not record customer data or secret values.

## Verification
Confirm miss ratio and backing-store load return toward baseline, Redis errors/evictions remain healthy, and session request latency recovers for 15 minutes.

## Prohibited initial actions
Do not flush the cache, invalidate all keys, or increase refill concurrency without evidence and approval; these actions can amplify load on the backing store.

## Escalation
Commerce Platform owns session-cache behavior; Runtime Platform owns shared Redis service health. See `OWNERS-005`.
