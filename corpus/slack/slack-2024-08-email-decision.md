# Slack Export — #backend-decisions — August 2024

**Channel:** #backend-decisions  
**Date:** 2024-08-13  
**Topic:** Email dispatch approach for checkout latency fix

---

**@ravi-menon** [10:02 AM]  
Quick question before Priya writes the ADR — why are we going with Celery/Redis instead of
just a background thread? Threads are simpler to deploy.

**@priya-sharma** [10:07 AM]  
Three reasons: (1) Celery gives us retry with backoff — a thread that fails just silently
drops the email. (2) Flower monitoring means we can actually see what's in the queue.
(3) We're already running Redis for sessions; adding a Celery worker is low marginal cost.

**@ravi-menon** [10:11 AM]  
Fair point on the retry. What about the transaction boundary issue? Order written, queue
push fails, customer gets no email?

**@priya-sharma** [10:15 AM]  
We'll add a daily reconciliation job. Scans orders with no sent_at timestamp older than
10 minutes, resends. It's a safety net, not the primary flow. But yes — this decision
deliberately gives up same-transaction email guarantees. That's the trade.

**@daniel-osei** [10:20 AM]  
Agree with Priya. The 800ms block is absolutely killing checkout conversion. We saw a 6%
drop in completions above 1.2s in last quarter's A/B. Async is the right call.

**@ravi-menon** [10:22 AM]  
OK I'm convinced. Do NOT let anyone "simplify" this back to synchronous later without
reading the ADR first. The latency numbers are the whole reason.

**@priya-sharma** [10:24 AM]  
+1. Writing ADR-001 now. The rationale lives there.

## Cross-References
- related_to: ADR-001-async-email.md
- related_to: PR-42-implement-async-email.md
- component: email_service