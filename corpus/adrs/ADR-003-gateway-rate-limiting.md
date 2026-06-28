# ADR-003: Enforce Rate Limiting at the API Gateway, Not in Application Code

**Status:** Accepted  
**Date:** 2024-03-22  
**Author:** @ravi-menon  
**Component:** api_gateway, all public endpoints  

## Context

After a scraping incident that saturated the `/search` endpoint (12k req/s from 3 IPs,
causing p99 > 8s for legitimate users), the team agreed that rate limiting was non-negotiable.
We debated where to enforce it:

1. **Application middleware** (Django `django-ratelimit` or DRF throttle classes) — easy to
   add per-view, lives next to the business logic.
2. **API gateway layer** (Nginx `limit_req`, Kong rate-limit plugin, or AWS WAF) — enforcement
   before the request touches Python; blocks at the edge.
3. **Redis-backed distributed counter in app code** — hybrid: app logic, shared state.

## Decision

We enforce rate limits **at the gateway layer** (Nginx `limit_req_zone` for self-hosted;
Kong rate-limit plugin for cloud deployments). Application code contains **no throttle
decorators or middleware** for rate limiting — that responsibility belongs to the gateway.

## Consequences

- **Positive:** Abusive requests are dropped before they consume a Python worker, DB
  connection, or any application resource. The 12k-req burst would have been absorbed at
  the gateway; zero Django workers would have been touched.
- **Positive:** Rate limit config lives in one place (gateway config). Changing a limit
  doesn't require a code deploy, test cycle, or PR — ops can hot-reload Nginx config.
- **Positive:** Consistent enforcement across all services regardless of language or
  framework. A new microservice is automatically covered.
- **Negative:** Per-user / per-route granularity is coarser at Nginx level than in app
  middleware. Mitigated: Kong's rate-limit plugin supports per-consumer, per-route rules.
- **Negative:** Local dev environment must run Nginx or Kong to test realistic limiting.
  Mitigated: `docker-compose.yml` includes a dev gateway service.

## Rationale (the WHY)

Rate limiting in application code is *defense in depth*, not a primary defense. If the
limit is enforced in Django middleware, the abusive request has already: opened a socket,
completed TLS, been parsed by Nginx/uWSGI, spawned a Python coroutine, and hit the ORM
connection pool — before being rejected. We spend ~40ms of expensive compute to say "no."

Enforcing at the gateway drops the request at the edge with <1ms overhead and no
application-layer cost. The scraping incident proved this matters: 12k req/s of "rejected
in middleware" would still saturate our worker pool.

Application-layer throttle decorators (`@ratelimit`, DRF `throttle_classes`) are explicitly
**banned** for public endpoints. If you find yourself adding one, re-read this ADR and
implement the limit in the gateway config instead.

## Cross-References
- implements: PR-19-gateway-rate-limit.md
- discussed_in: slack-2024-03-rate-limiting.md
- component: api_gateway
