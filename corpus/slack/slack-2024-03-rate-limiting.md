# Slack Export — #incidents — March 2024

**Channel:** #incidents  
**Date:** 2024-03-21  
**Topic:** Scraping incident post-mortem + rate limiting decision

---

**@ravi-menon** [2:03 PM]  
Incident post-mortem thread. We just got hit by ~12k req/s from 3 IPs targeting /search.
Workers saturated for 22 minutes. p99 hit 8.1 seconds. Conversion dropped ~31% during
the window.

**@priya-sharma** [2:06 PM]  
I added `@ratelimit` decorators to search and products views as an emergency patch.
It's live but it's a bandage — requests still hit Django workers before getting rejected.
We need a real solution.

**@ravi-menon** [2:09 PM]  
Right. The problem with middleware rate limiting is that the abusive request has already:
opened a socket, done TLS, been parsed by uWSGI, allocated a thread, hit the middleware
chain — *then* we say no. At 12k req/s that's still 12k connections per second burning
resources.

**@daniel-osei** [2:13 PM]  
Nginx `limit_req_zone`. Drop it at the edge before it reaches Python at all. I've seen
this handle 100k req/s on a $20 VPS. Gateway enforcement is the right answer.

**@ananya-krishna** [2:17 PM]  
Agreed. Also makes ops simpler — change a limit = edit nginx config + reload. No code
deploy, no test cycle, no PR. Oncall can adjust limits at 3am without waking up a dev.

**@priya-sharma** [2:19 PM]  
What about per-user granularity? Nginx limit_req is per-IP. Authenticated users could
have different limits.

**@ravi-menon** [2:22 PM]  
Kong rate-limit plugin handles per-consumer. We can route authenticated traffic through
Kong consumer groups. Anonymous traffic gets the IP-based limit.

**@daniel-osei** [2:25 PM]  
The key principle I want captured in the ADR: rate limiting in application code is
defense-in-depth, not primary defense. Primary defense is at the edge. The `@ratelimit`
decorators we added today should be removed once the gateway config is in.

**@ravi-menon** [2:27 PM]  
Agreed. I'll write ADR-003 and PR the Nginx config. The decorators in the app code come
out in that same PR. We don't want two rate-limiting systems — that's how you get
inconsistent behavior and false confidence.

**@ananya-krishna** [2:30 PM]  
Worth calling out explicitly in the ADR that adding `@ratelimit` or DRF `throttle_classes`
to public endpoints is banned. If someone's tempted to add one, they should be implementing
a gateway rule instead.

**@ravi-menon** [2:32 PM]  
Will do. Making it explicit. The incident cost us real conversion revenue — I want future
devs to understand *why* this isn't a decoration choice.

## Cross-References
- related_to: ADR-003-gateway-rate-limiting.md
- related_to: PR-19-gateway-rate-limit.md
- component: api_gateway
