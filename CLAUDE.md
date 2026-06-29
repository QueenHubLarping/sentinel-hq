# Sentinel — CLAUDE.md

Decision-reversal guardian for code review, built on Cognee.
Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5 2026). Track: **Best Use of Open Source**.

## Judging criteria

1. **Potential Impact** — addresses a meaningful problem with persistent AI memory.
2. **Creativity & Innovation** — pushes what's possible when an agent never forgets.
3. **Technical Excellence** — clean, maintainable engineering.
4. **Best Use of Cognee** — depth of the memory lifecycle (remember / recall / improve / forget) + hybrid graph-vector layer.
5. **User Experience** — intuitive, polished, adoptable.
6. **Presentation Quality** — demo, README, and submission communicate problem → solution → impact.

## Hackathon day status

| Day | Goal | Status |
|-----|------|--------|
| 1 | Cognee spike — remember + recall + forget gates pass | ✅ Done |
| 2 | Multi-hop reversal detection (90 % confidence on ADR-001 flip) | ✅ Done |
| 3 | End-to-end skeleton + SPINE-2 demo (before → forget → after) | ✅ Done |
| 4 | Improve phase (👍/👎 feedback loop), feature freeze | ✅ Improve done |
| 5 | Harden demo, graph viz polish, lock prompts + fallbacks | ❌ |
| 6 | Presentation, deck, rehearse | ❌ |

**SPINE-1** (multi-hop recall, ≥2 source types, no lexical overlap) ✅  
**SPINE-2** (forget mutates graph; same PR flips behavior) ✅

## Setup (self-hosted Cognee + Groq LLM + local Ollama embeddings)

```bash
# 1. Ollama (local embedding runtime)
ollama serve
ollama pull nomic-embed-text    # embeddings

# 2. Python env (use 3.10–3.12; cognee needs >=3.10)
python3.10 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. Config (set GROQ_API_KEY in the ignored .env file)
cp .env.template .env

# 4. Scripts — run in order for the full demo
python scripts/day1_spike.py    # verify remember + recall + forget
python scripts/day2_detect.py   # single-PR reversal detection
python scripts/day3_flip.py     # before → intentional → after + graph HTML
python scripts/day4_improve.py  # improve phase: 👎 → cognee.improve() → similar flag suppressed

# 5. Tests (no Cognee / network required)
pytest tests/
```

## Project layout

```
sentinel/
  connection.py       — Groq/Ollama bootstrap; applies config + checks local embeddings
  ingest.py           — remember phase: cognee.add() + cognee.cognify() over the corpus
  detect.py           — recall + judge phase: graph search → Groq Verdict (Pydantic model)
                        (recall takes optional session_id/feedback_influence for the improve loop)
  resolve.py          — forget phase: mark_intentional() → supersede ADR + cognee.forget()
  improve.py          — improve phase: session feedback (👍/👎) → cognee.improve() re-weights
                        the exact graph nodes/edges a flag used (feedback_weight 0.5↔0/1)
  comment.py          — render GitHub PR comments (reversal card or clean-bill)
  github_pr.py        — GitHub REST helpers, event payload parsing, commit/push

corpus/
  adrs/               — Architecture Decision Records (markdown, 3 decisions)
  slack/              — static "Slack" conversation exports (markdown, 3 threads)
  prs/                — PR metadata for decisions already merged (markdown, 3 PRs)

samples/
  incoming_pr_57_sync_email.md          — PR that reverses ADR-001 (async email) — Day 2 & 3
  incoming_pr_61_app_ratelimit.md       — PR that reverses ADR-003 (app-level rate limiting) — Day 4 flag
  incoming_pr_63_app_ratelimit_orders.md — a *similar* ADR-003 reversal — Day 4 "future flag" suppressed by improve

scripts/
  day1_spike.py           — Day 1 gates: remember+recall (SPINE-1) + forget-flips-recall (SPINE-2)
  day2_detect.py          — reversal detection on the sample PR; prints GitHub comment
  day3_flip.py            — full demo loop; emits graph_before.html + graph_after.html
  day4_improve.py         — improve phase: 👎 a flag → cognee.improve() → same + similar PR go silent
  action_entrypoint.py    — GitHub Action entry point (pull_request + issue_comment events)
  wipe.py                 — local dev: wipe Cognee stores for a clean re-ingest

tests/
  test_sentinel.py        — pure-function unit tests (no Cognee, no network)

action.yml              — GitHub Action metadata (inputs: mode, github-token, groq-api-key)
.github/workflows/
  sentinel.yml            — example workflow (runs on PR open/sync, self-hosted runner)
graph_before.html       — Day 3 output: vis.js knowledge graph before forget
graph_after.html        — Day 3 output: vis.js knowledge graph after forget
```

## Architecture decisions

- **Self-hosted Cognee with Groq reasoning and local embeddings.** The LLM
  (`llama-3.3-70b-versatile`) runs through Groq; embeddings (`nomic-embed-text`) run
  on local Ollama. Graph (Ladybug — cognee 1.2.2's default embedded store), vector
  (LanceDB), relational (SQLite), and the session cache (SQLite `cache.db`) are all local
  files. Config is env-driven (`.env`), applied in `sentinel/connection.py`.
- **Single-user/local posture** — `ENABLE_BACKEND_ACCESS_CONTROL=false` (set before
  `import cognee`) disables multi-tenant auth so scripts run without a user/session.
- **remember = add() + cognify()** — each ADR/PR/Slack doc is added separately with a
  type-stamped metadata header so cognify extracts cross-document typed edges
  (supersedes, justifies, implements, discussed_in).
- **recall = search(query_type=GRAPH_COMPLETION)** — `only_context=True` returns the raw
  retrieved graph context (no LLM answer), which is the honest before/after measure.
- **judge = Groq LLM grounded in retrieved context only** — the Verdict Pydantic model
  (analysis, reverses_decision, decision_reference, original_reasoning, impact_if_merged,
  confidence) is generated from PR text + graph context; LLM never uses training knowledge.
  Chain-of-thought in `analysis` comes before the boolean to improve small-model accuracy.
- **forget = cognee.forget(data_id=..., dataset=...)** — stable data_ids are derived
  deterministically from filenames (fixed-namespace UUID) so selective forget works across
  CI runner restarts without querying internal Cognee dataset APIs.
- **Superseded ADR skip at ingest** — `mark_intentional()` rewrites the ADR file on disk
  (`**Status:** Superseded`) and then forgets from graph. Next ingest skips superseded
  files, making forget durable without managing graph persistence.
- **improve = session feedback → cognee.improve()** (`sentinel/improve.py`). Distinct from
  forget: forget *retires* an overturned decision; improve *re-ranks* memory the team
  considers noise, deleting nothing. Loop: (1) detection recall runs inside a Cognee
  *session* (`search(session_id=...)`) so Cognee records the exact `used_graph_element_ids`
  that produced the flag; (2) a maintainer 👎 is stored via `cognee.session.add_feedback`
  (score 1=suppress … 5=reinforce); (3) `cognee.improve(dataset=…, session_ids=[…],
  feedback_alpha=1.0)` streams that score onto those nodes/edges' `feedback_weight`
  (0.5 baseline → ~0.0 on a 👎); (4) the next recall, run with `feedback_influence>0`,
  gives down-weighted triplets a larger effective distance so they fall out of top-k and
  stop reaching the judge. Honest because the weights live on the graph and are consumed by
  Cognee's own triplet ranker — the suppression is a real graph mutation, not a side table.
- **GitHub Action — advisory only** — Sentinel never fails the build. Dry-run mode
  writes to $GITHUB_STEP_SUMMARY; post mode comments on the PR. The `/sentinel
  intentional` reply triggers the issue_comment event path (checkout branch → supersede
  ADR → commit/push → resolution comment).

## Verified Cognee 1.2.2 API notes (don't guess these)

- Both V1 (`add`/`cognify`/`search`) and V2 (`remember`/`recall`/`forget`/`improve`/`memify`) exist.
- `forget(*, data_id=, dataset=, dataset_id=, everything=, memory_only=, user=)` — keyword-only.
- `SearchType` members include `GRAPH_COMPLETION`, `TRIPLET_COMPLETION`, `CYPHER`,
  `RAG_COMPLETION`, `TEMPORAL` — **there is no `INSIGHTS`**.
- Ollama embeddings require `transformers` (HuggingFace tokenizer) — in requirements
  (`pip install -r requirements.txt`; a bare cognee install does NOT pull it).
- **improve() feedback loop** (verified from source, needed for `sentinel/improve.py`):
  - `improve(dataset=, *, session_ids=, feedback_alpha=0.1, ...)` — keyword `feedback_alpha`
    is the streaming-update step (must be in `(0, 1]`); we use `1.0` for a decisive 0.5→0 move.
  - `cognee.session.add_feedback(session_id=, qa_id=, feedback_text=, feedback_score=)` —
    score is `1..5`, normalized to `(score-1)/4` (1→0.0 suppress, 5→1.0 reinforce).
    Get the `qa_id` from `cognee.session.get_session(session_id)` (latest entry).
  - **Requires the session cache**: with `CACHING=false` the SessionManager no-ops, so
    feedback is silently dropped. Default `CACHE_BACKEND=sqlite` (a `cache.db`; no Redis).
    The Day-4 script sets `CACHING=true` BEFORE importing cognee (it differs from the forget
    demo, which keeps `CACHING=false` so deletions show in recall immediately).
  - **Recall only honors feedback if `feedback_influence>0`** — config default
    `DEFAULT_FEEDBACK_INFLUENCE=0.0`, so set it (env or per-`search`/`detect_reversal` call).
  - Graph store is **Ladybug** (cognee 1.2.2 default `GRAPH_DATABASE_PROVIDER`), whose
    adapter implements `get/set_node_feedback_weights` + edge equivalents; the Kuzu adapter
    does not. (Earlier notes said "Kuzu" — the running default here is Ladybug.)

## Corpus decisions (3 contradiction types)

| ADR | Decision | Reversal pattern |
|-----|----------|-----------------|
| ADR-001 | `email_service` → async via Redis/Celery | PR that makes checkout email sending synchronous again |
| ADR-002 | `orders/payments` → PostgreSQL (not MongoDB) | PR that switches transactional tables back to MongoDB |
| ADR-003 | Rate limiting at Nginx gateway (not app code) | PR that adds `@ratelimit` decorators to Django views |

**Primary demo target:** ADR-001 (the one contradiction used in all Day 2/3 scripts).  
Multi-hop evidence chain: `PRRecord --[reverses]--> EngineeringDecision --[justified_by]--> ArchitecturalReason`.  
Source types crossed: PR diff (incoming) + ADR (corpus) + Slack (corpus) = ≥2 hops, ≥2 source types.  
SPINE-1 proof: vector-only search on the PR diff alone cannot reach the Slack rationale.

## What is NOT implemented yet (Day 4+)

- **Improve phase in the GitHub Action** — the loop exists (`sentinel/improve.py`, proven by
  `scripts/day4_improve.py`), but it is not yet wired into `action_entrypoint.py` as a
  `/sentinel noise` (👎) reply alongside the existing `/sentinel intentional` (forget) path.
- **Confidence threshold** — Verdict emits confidence but no threshold filter gates the comment.
- **Incremental ingestion** — re-ingests entire corpus each run; no diff-based add.
- **Auto-draft superseding ADR** — marked as "should" in REQUIREMENTS.md.
- **Live Slack API** — explicitly cut (W1); uses static markdown exports only.
- **MCP "ask-the-graph" face** — stretch goal (W2), not implemented.

## AI tool disclosure (hackathon rule)

Built with assistance from Claude (Claude Code). Must be disclosed in the final submission.
