# Sentinel stress-test report

_12 incoming PRs (8 reversals + 4 noise controls) reviewed against a graph of 159 nodes built from 9 merged PRs + 8 incident issues._

| PR | slug | expected | result | confidence | tier | cited decision | outcome |
|---:|------|----------|--------|-----------:|------|----------------|---------|
| #33 | noise_refinement | silent | silent | — | — | — | OK (silent) |
| #32 | noise_null_check | silent | silent | — | — | — | OK (silent) |
| #31 | noise_dep_bump | silent | silent | — | — | — | OK (silent) |
| #30 | noise_typo | silent | silent | — | — | — | OK (silent) |
| #29 | inline_webhooks | flag | flag | 90% | approved | PR #21: webhooks: acknowledge provider callbacks | OK (caught) |
| #28 | join_search | flag | flag | 85% | approved | PR #20: search: serve catalog queries from the d | OK (caught) |
| #27 | direct_db | flag | flag | 90% | approved | PR #19 | OK (caught) |
| #26 | drop_idempotency | flag | flag | 90% | approved | PR #18 (require idempotency keys on the capture  | OK (caught) |
| #25 | db_sessions | flag | flag | 90% | approved | PR #17 | OK (caught) |
| #24 | app_ratelimit_orders | flag | flag | 90% | approved | PR #14 | OK (caught) |
| #23 | app_ratelimit | flag | flag | 90% | approved | PR #14 | OK (caught) |
| #22 | sync_email | flag | flag | 90% | approved | PR #16 (async email dispatch via Redis/Celery qu | OK (caught) |

**12 PRs, 8 flags, 8 genuine reversals caught (8 with correct citations); 4/4 noise PRs correctly silent.**
