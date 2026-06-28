# PR #42 — feat: async email dispatch via Redis/Celery queue

**Author:** @priya-sharma  
**Date:** 2024-08-16  
**Status:** Merged  
**Component:** email_service  

## Summary

Implements the async email dispatch architecture decided in ADR-001.

Moves email sending out of the HTTP request-response cycle. The checkout endpoint
now returns 200 immediately after writing the order to the database. A Celery worker
handles SMTP dispatch with exponential backoff (3 retries, max 60s delay).

## Changes

- `email_service/tasks.py`: new Celery task `send_order_confirmation(order_id)`
- `checkout/views.py`: remove direct `send_email()` call; replace with `send_order_confirmation.delay(order.id)`
- `email_service/worker.py`: Celery app config with Redis broker
- `reconciliation/jobs.py`: daily job to resend missing confirmation emails
- `docker-compose.yml`: add `celery-worker` and `celery-beat` services

## Benchmarks

| Metric | Before | After |
|--------|--------|-------|
| Checkout p95 latency | 1,340ms | 541ms |
| Email delivery rate | 99.1% (sync) | 99.7% (async + retry) |

## Implements

ADR-001: Use Asynchronous Email Dispatch via Queue

## Cross-References
- implements: ADR-001-async-email.md
- discussed_in: slack-2024-08-email-decision.md
- component: email_service