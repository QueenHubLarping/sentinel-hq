# PR #19 — ops: add gateway-level rate limiting (Nginx limit_req)

**Author:** @ravi-menon  
**Date:** 2024-03-28  
**Status:** Merged  
**Component:** api_gateway, infra  

## Summary

Implements the rate-limiting strategy from ADR-003. Adds `limit_req_zone` rules to the
Nginx gateway config. Removes the `django-ratelimit` decorators that were temporarily
added to `/search` and `/products` as an emergency patch after the scraping incident.

## Changes

- `infra/nginx/api.conf`: `limit_req_zone` on `$binary_remote_addr`; `/search` capped at
  30 req/s per IP with burst=10; `/api/` global at 100 req/s per IP with burst=50
- `infra/nginx/errors.conf`: custom 429 JSON response body with `Retry-After` header
- `docker-compose.yml`: dev gateway service (`nginx:alpine`) with hot-reload on config change
- `requirements.txt`: remove `django-ratelimit==4.1.0`
- `search/views.py`, `products/views.py`: **remove** `@ratelimit` decorators (gateway owns this now)
- `docs/runbooks/rate-limit-tuning.md`: how to adjust limits without a code deploy

## Key point

The `@ratelimit` decorators on `search/views.py` and `products/views.py` are intentionally
deleted in this PR — they were a stopgap, not the architecture. Rate limiting in application
code is explicitly out-of-scope per ADR-003. Do not re-add them.

## Load test (locust, 500 virtual users, 10s ramp)

| Scenario | Without gateway limit | With gateway limit |
|----------|-----------------------|--------------------|
| Peak req/s reaching Django workers | 11,800 | 312 |
| Worker pool saturation | Yes (100%) | No (28%) |
| p99 latency for legit users | 8,100ms | 420ms |

## Implements

ADR-003: Enforce Rate Limiting at the API Gateway, Not in Application Code
