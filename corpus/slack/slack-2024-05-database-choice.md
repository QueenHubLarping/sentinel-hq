# Slack Export — #backend-decisions — May 2024

**Channel:** #backend-decisions  
**Date:** 2024-05-07  
**Topic:** Database choice for v2 orders + payments redesign

---

**@ravi-menon** [9:14 AM]  
Before Daniel's ADR lands — can we do a quick gut-check on Mongo vs Postgres for orders?
Half the team has been assuming we'd stay on Mongo since that's what we know.

**@daniel-osei** [9:19 AM]  
I pushed hard for Postgres here. Let me explain the core reason: we can't do a real
multi-document transaction in Mongo without the 4.0+ multi-document transaction API, which
adds overhead and still doesn't give us FK integrity. An order without a payment row is
invalid — I want the *database* to enforce that, not us.

**@priya-sharma** [9:22 AM]  
Agree with Daniel. The chaos test last sprint was the eye-opener for me. 0.4% of writes
in the Mongo path ended up in inconsistent state during simulated network partition. That's
not acceptable for payments data. We'd need an application-level saga pattern to fix it,
which is way more complexity than just using Postgres.

**@ravi-menon** [9:25 AM]  
What about schema flexibility? We change the order model pretty often. Migration scripts
feel like overhead.

**@daniel-osei** [9:29 AM]  
Alembic auto-generates them in 30 seconds. The "flexibility" argument for Mongo really
means "we can write inconsistent data without the DB complaining." That's not a feature
for payments — it's a liability. We *want* the schema to be a contract.

**@ananya-krishna** [9:33 AM]  
Also worth noting — PCI-DSS audit in Q3. Auditors want WAL-based change-data-capture.
Postgres + Debezium is a standard pattern. Mongo change streams can work but we'd be
explaining a non-standard setup to the auditors. Not worth it.

**@ravi-menon** [9:36 AM]  
That settles it for me. ACID + FK constraints + audit trail. Postgres it is.
Daniel, write the ADR so this doesn't get re-litigated in 6 months.

**@daniel-osei** [9:38 AM]  
On it. ADR-002, drafting now. Key point I'll make explicit: this decision is specifically
for transactional financial data. Product catalog, events, analytics — we can revisit
document stores for those. Orders and payments: Postgres, full stop.

**@ananya-krishna** [9:41 AM]  
+1. Please also include the chaos test numbers. If someone proposes Mongo for orders
again they should have to disprove those numbers first.
