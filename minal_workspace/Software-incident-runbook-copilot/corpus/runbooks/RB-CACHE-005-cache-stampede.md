---
doc_id: RB-CACHE-005
service: session-cache
environment: production
version: 1
status: active
owner: commerce-platform
last_reviewed: 2026-10-16
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
If a synchronized expiry or invalidation is confirmed and Redis is healthy, ask the service owner to apply the approved gradual refill or TTL-jitter mitigation. Watch backing-store capacity during recovery.

If Redis errors or evictions are elevated, page the cache owner before changing application TTL or refill behavior.

## Verification
Confirm miss ratio and backing-store load return toward baseline, Redis errors/evictions remain healthy, and session request latency recovers for 15 minutes.

## Prohibited initial actions
Do not flush the cache, invalidate all keys, or increase refill concurrency without evidence and approval; these actions can amplify load on the backing store.

## Escalation
Commerce Platform owns session-cache behavior; Runtime Platform owns shared Redis service health. See `OWNERS-005`.
