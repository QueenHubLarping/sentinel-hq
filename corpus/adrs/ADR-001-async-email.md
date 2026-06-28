# ADR-001: Use Asynchronous Email Dispatch via Queue

**Status:** Accepted  
**Date:** 2024-08-14  
**Author:** @priya-sharma  
**Component:** email_service  

## Context

The `/checkout` endpoint was measured at 1,340ms p95 latency. Profiling showed that 800ms
of that came from blocking SMTP calls to SendGrid inside the request-response cycle.
The team explored three options:

1. Keep synchronous SMTP — simple code, but blocks the HTTP worker.
2. Fire-and-forget thread — easy to implement, no retry on failure.
3. Push to a task queue (Redis + Celery) — async dispatch with retry, observable.

## Decision

We adopt **option 3: Redis/Celery async dispatch**.

Email sending is pushed onto a Celery queue. The checkout endpoint returns 200 immediately
after writing the order to the database. A background worker handles SMTP with exponential
backoff (3 retries, max 1 min delay).

## Consequences

- **Positive:** Checkout p95 latency drops from 1,340ms to ~540ms (38% improvement). 
  Users get instant confirmation. Workers can be scaled independently.
- **Positive:** Failed emails are retried automatically; failures are observable via Celery Flower.
- **Negative:** Email delivery is no longer guaranteed within the same transaction.
  If the queue crashes between order write and email dispatch, no email is sent.
  Mitigated by a daily reconciliation job that resends missing confirmation emails.
- **Negative:** Adds operational overhead: Redis + Celery must be deployed and monitored.

## Rationale (the WHY)

The 800ms SMTP block was the single biggest latency driver in checkout. Async dispatch
removes it from the critical path entirely. We chose the queue approach over fire-and-forget
threads because observability and retry logic are non-negotiable for transactional email.
The operational cost of Redis/Celery is justified by the latency gain and the reliability
guarantee the queue provides.

This is a deliberate, non-obvious choice. Synchronous email is the "simpler" path —
but simplicity here trades user-perceived speed and reliability for convenience.
That trade is wrong for a checkout flow.

## Cross-References
- implements: PR-42-implement-async-email.md
- discussed_in: slack-2024-08-email-decision.md
- component: email_service