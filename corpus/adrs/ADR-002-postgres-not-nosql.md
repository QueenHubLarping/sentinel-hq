# ADR-002: Use PostgreSQL for Transactional Order Data (Not MongoDB)

**Status:** Accepted  
**Date:** 2024-05-09  
**Author:** @daniel-osei  
**Component:** orders_service, payments_service  

## Context

During the v2 data-layer redesign we debated the storage backend for `orders` and `payments`
tables. The team had prior MongoDB experience and proposed using a document store to avoid
rigid schemas and speed up early iteration. Three options were evaluated:

1. **MongoDB** — flexible schema, familiar to the team, no migration tooling needed.
2. **PostgreSQL** — ACID transactions, mature tooling, strict schema enforced at DB level.
3. **CockroachDB** — distributed ACID, but adds operational complexity we don't need at our scale.

## Decision

We adopt **PostgreSQL** for all transactional tables (`orders`, `payments`, `refunds`).

Product catalog, search indexes, and analytics event stores may use document/columnar
stores where appropriate — that is out of scope here. This ADR governs only financial
and order-state data.

## Consequences

- **Positive:** Full ACID guarantees — an order can't be written without a matching payment
  row; a refund can't partially update. Multi-table writes are atomic.
- **Positive:** Foreign-key constraints prevent orphaned records at the database level.
  MongoDB enforces nothing; application bugs become silent data corruption.
- **Positive:** `pg_audit` and WAL-based CDC (Debezium) give us a reliable audit trail
  required for PCI-DSS compliance audits.
- **Negative:** Stricter schema requires migration scripts on every model change. Accepted —
  Alembic auto-generates migrations; review cost is low.
- **Negative:** Horizontal write-scaling is harder than MongoDB sharding. Accepted — we
  are at ~400 orders/minute peak; vertical Postgres handles this comfortably to 10× that.

## Rationale (the WHY)

Payment and order data is the highest-stakes data we own. A missed transaction or
partially-applied refund is a customer-trust and compliance failure, not an eventual-
consistency footnote. MongoDB's document model is excellent for flexible, high-volume,
non-transactional workloads — but it is the wrong tool when atomicity across multiple
entities is a hard requirement.

The "flexible schema" argument for MongoDB is also a liability here: we *want* the DB
to reject malformed writes that application code lets through. The schema is load-bearing.

This is an explicit, non-obvious choice to accept migration overhead in exchange for
correctness guarantees. Revisit only if horizontal write volume exceeds 10k orders/min.
