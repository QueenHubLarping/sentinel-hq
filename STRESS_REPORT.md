# Sentinel stress-test report

_12 incoming PRs (8 reversals + 4 noise controls) reviewed against a graph of 192 nodes built from 9 merged PRs + 8 incident issues._

| PR | slug | expected | result | confidence | tier | cited decision | outcome |
|---:|------|----------|--------|-----------:|------|----------------|---------|
| #33 | noise_refinement | silent | silent | — | — | — | OK (silent) |
| #32 | noise_null_check | silent | silent | — | — | — | OK (silent) |
| #31 | noise_dep_bump | silent | silent | — | — | — | OK (silent) |
| #30 | noise_typo | silent | silent | — | — | — | OK (silent) |
| #29 | inline_webhooks | flag | flag | 90% | approved | PR #21 | OK (caught) |
| #28 | join_search | flag | flag | 90% | approved | PR #20 | OK (caught) |
| #27 | direct_db | flag | flag | 90% | approved | PR #19 (infra: route all Postgres access through | OK (caught) |
| #26 | drop_idempotency | flag | flag | 90% | approved | PR #18 (require idempotency keys on the capture  | OK (caught) |
| #25 | db_sessions | flag | flag | 90% | approved | PR #17 (stateless signed tokens) | OK (caught) |
| #24 | app_ratelimit_orders | flag | flag | 90% | approved | PR #14 (gateway-level rate limiting) | OK (caught) |
| #23 | app_ratelimit | flag | flag | 90% | approved | PR #14 (ops: add gateway-level rate limiting) | OK (caught) |
| #22 | sync_email | flag | flag | 90% | approved | PR #16 | OK (caught) |

**12 PRs, 8 flags, 8 genuine reversals caught (8 with correct citations); 4/4 noise PRs correctly silent.**

## Live GitHub Action runs (the same matrix, on real PRs)

The identical 12-PR matrix ran as **real GitHub Action runs** on the public demo repo
([QueenHubLarping/sentinel-test-repo](https://github.com/QueenHubLarping/sentinel-test-repo/pulls)) —
each PR opened via the API, each verdict posted (or withheld) by the Action itself:

| PR | slug | expected | live result |
|---:|------|----------|-------------|
| [#22](https://github.com/QueenHubLarping/sentinel-test-repo/pull/22) | sync_email | flag | ✅ flagged — Messaging, 90%, cites the async-email decision → latency incident |
| [#23](https://github.com/QueenHubLarping/sentinel-test-repo/pull/23) | app_ratelimit | flag | ✅ flagged — Rate Limiting, cites the gateway decision → double-counting incident |
| [#24](https://github.com/QueenHubLarping/sentinel-test-repo/pull/24) | app_ratelimit_orders | flag | ✅ flagged — same decision, second reversal vector |
| [#25](https://github.com/QueenHubLarping/sentinel-test-repo/pull/25) | db_sessions | flag | ✅ flagged — Authentication, cites the stateless-token decision → DB-load incident |
| [#26](https://github.com/QueenHubLarping/sentinel-test-repo/pull/26) | drop_idempotency | flag | ✅ flagged — Payments, cites the idempotency decision → double-charge incident |
| [#27](https://github.com/QueenHubLarping/sentinel-test-repo/pull/27) | direct_db | flag | ✅ flagged — Infrastructure, cites the PgBouncer decision → connection-exhaustion incident |
| [#28](https://github.com/QueenHubLarping/sentinel-test-repo/pull/28) | join_search | flag | ✅ flagged — Search, cites the read-model decision → join-storm incident |
| [#29](https://github.com/QueenHubLarping/sentinel-test-repo/pull/29) | inline_webhooks | flag | ✅ flagged — Webhooks, cites the queue-ack decision → duplicate-delivery incident |
| [#30](https://github.com/QueenHubLarping/sentinel-test-repo/pull/30) | noise_typo | silent | ✅ silent |
| [#31](https://github.com/QueenHubLarping/sentinel-test-repo/pull/31) | noise_dep_bump | silent | ✅ silent (a *Celery* version bump next to an active Celery decision — still silent) |
| [#32](https://github.com/QueenHubLarping/sentinel-test-repo/pull/32) | noise_null_check | silent | ✅ silent |
| [#33](https://github.com/QueenHubLarping/sentinel-test-repo/pull/33) | noise_refinement | silent | ✅ silent (a *consistent* refinement of the async-email decision — silent, not a false flag) |

**Live: 12/12 correct — 8/8 reversals caught, 4/4 noise silent, 0 false positives.**
Each flag's comment carries the Memory Review card, the evidence chain
(decision PR → incident issue), a confidence meter, the trust tier, and a link to the
interactive Visual Memory Recap.
