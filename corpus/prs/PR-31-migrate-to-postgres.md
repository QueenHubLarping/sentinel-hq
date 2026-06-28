# PR #31 — chore: migrate orders + payments to PostgreSQL

**Author:** @daniel-osei  
**Date:** 2024-05-14  
**Status:** Merged  
**Component:** orders_service, payments_service  

## Summary

Implements the storage decision from ADR-002. Replaces MongoDB collections
(`orders_v1`, `payments_v1`) with PostgreSQL tables. All financial and order-state
data now lives in Postgres with full ACID semantics.

## Changes

- `orders/models.py`: Django ORM models for `Order`, `OrderLine`, `Refund`
- `payments/models.py`: `Payment`, `PaymentEvent` tables with FK constraints to `Order`
- `migrations/`: Alembic migration scripts (0031_orders_to_pg.py)
- `orders/repositories.py`: replace PyMongo queries with SQLAlchemy queries
- `payments/repositories.py`: same
- `docker-compose.yml`: swap `mongo` service for `postgres:16`
- `scripts/migrate_mongo_to_pg.py`: one-time data migration script (run once, delete after)
- `tests/`: updated fixtures; added transaction-rollback tests for payment failure paths

## Why not just add Postgres alongside Mongo?

Dual-write during migration was considered and rejected. It doubles the failure surface
and leaves us with two sources of truth. We did a maintenance-window migration instead:
export Mongo → transform → bulk-insert Postgres. Tested against a staging snapshot first.

## Benchmark (staging, 500k order records)

| Metric | MongoDB | PostgreSQL |
|--------|---------|------------|
| Order + Payment write (2-table atomic) | ~3.1ms (app-level "transaction") | 2.4ms (real transaction) |
| Refund with FK integrity check | N/A (app-enforced) | 2.8ms (DB-enforced) |
| Corrupt write rate (chaos test) | 0.4% silent bad state | 0% (constraint rejected) |

The 0.4% figure from the Mongo chaos test was the decisive number — those were real data
integrity failures that would have required manual reconciliation.

## Implements

ADR-002: Use PostgreSQL for Transactional Order Data

## Cross-References
- implements: ADR-002-postgres-not-nosql.md
- discussed_in: slack-2024-05-database-choice.md
- component: orders_service, payments_service
