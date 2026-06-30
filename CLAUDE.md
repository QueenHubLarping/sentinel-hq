# Sentinel — CLAUDE.md

**The Memory OS for software engineering — the Organizational Learning Engine.** Decision-reversal
is the flagship live demo; the product turns engineering activity into reusable organizational
learning. Built on Cognee. Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5 2026). Track:
**Best Use of Open Source**.

> Canonical product docs at repo root: **`PRODUCT_SPEC.md`** (full vision) and **`REQUIREMENTS.md`**
> (scope/MoSCoW/gates). Read those for the "why"; this file is the engineering context for the code.

## Product direction & vocabulary (surface vs. substrate)

We are building **the best application of Cognee**, not a better Cognee (Stripe : Postgres :: Sentinel : Cognee).

**Three foundational scope decisions (LOCKED):**
- **No ADRs, no Slack, no separate decision docs as inputs.** Ingestion is **merged PRs (body + diff)
  + linked issues (thread/comments) + review comments + human input**, pulled from the GitHub API.
  `cognify` synthesizes `EngineeringDecision` nodes anchored to the **establishing PR** (decision id =
  deterministic UUID from the PR number, replacing the old ADR-filename key). Rationale is mined from
  linked issues/discussion — **never invented from the diff**. Deployable on any repo, zero docs.
- **No markdown corpus — everything comes from the GitHub API.** There is **no `corpus/*.md` and no
  `samples/*.md`** (both deleted). `remember` reads PR + issue **dicts** from `sentinel.sources`
  (`fetch_merged_prs` / `fetch_issues`), and for offline/demo runs replays them from a cached JSON
  snapshot **`.sentinel/api_snapshot.json`** (still 100% API-sourced — just recorded, so the stage demo
  never depends on the network). The demo data is *created* in a real repo via the API by
  **`scripts/seed_demo_repo.py`** (no hand-authored content). `sources.gather_memory()` returns
  `(pr_dicts, issue_dicts)` from the live API (writing the snapshot) or the snapshot; `incoming_text(slug)`
  returns the PR-under-review text.
- **No `memory/` directory.** Memory lives **in Cognee** (graph + vector), surfaced ONLY through the
  **Memory Review comment** + **graph viz**. Durability of a `forget` = Cognee's persistent stores +
  a small non-user-facing **`.sentinel/retired.json`** skip-list (re-ingest skips retired decisions).
  Trust tier (approved vs inferred) is recorded in **`.sentinel/approved.json`** (`sentinel.trust`).

**Vocabulary & model:**
- **Rebrand the surface, not the substrate.** Users only ever hear **"Engineering Learning"** /
  "Memory Review" / "Memory Commit". The code keeps load-bearing object names — **`Decision`,
  `EngineeringDecision`** — and deterministic data_ids. The identity anchor moves **ADR-filename →
  establishing-PR-number**; this is the one substrate change the kills require (see §re-anchor below).
- **Knowledge model = two layers.** Layer 1 = **Capabilities** (cross-cutting, not directory-bound:
  Messaging/Auth/Payments) → **Topics**. Layer 2 = knowledge objects (Decision/Assumption/Outcome…)
  that compress into a **Learning**. **Evidence (PR body/diff · Issue thread · review · commit)
  supports memory, never IS memory.** Capabilities/Topics emerge from cognify or are lightly seeded.
- **Done in the API/PR-keyed re-anchor pass (all test-green, 50 tests):** (1) `comment.py` → the
  **Memory Review** card; (2) decision identity + `forget` re-anchored ADR-keyed → **PR-keyed**
  (`_pr_number`, `mark_intentional` → `.sentinel/retired.json`); (3) markdown corpus deleted —
  ingestion is **GitHub API + JSON snapshot** only; (4) minimal **trust tiers** (`trust.py`) +
  Verdict assumption/capability/evidence_chain; (5) `GRAPH_DATABASE_PROVIDER=ladybug` pinned;
  (6) `scripts/seed_demo_repo.py` creates demo data via the API. **Still pending (needs a live
  Cognee/Groq/Ollama box):** re-prove SPINE-2 on the PR-keyed path; then delete the dormant ADR
  helpers in `resolve.py`. The ADR helpers remain ONLY as the §9 sequencing-rule backstop.

**The inference guardrail (keeps narrowed ingestion honest):** inference *connects and compresses
evidence that exists* (PR body + issue thread + diff); it **never invents a rationale written
nowhere.** No supporting evidence → stay silent (or "decision recorded; rationale not in history").

## Judging criteria

1. **Potential Impact** — addresses a meaningful problem with persistent AI memory.
2. **Creativity & Innovation** — pushes what's possible when an agent never forgets.
3. **Technical Excellence** — clean, maintainable engineering.
4. **Best Use of Cognee** — depth of the memory lifecycle (remember / recall / improve / forget) + hybrid graph-vector layer.
5. **User Experience** — intuitive, polished, adoptable.
6. **Presentation Quality** — demo, README, and submission communicate problem → solution → impact.

## Status

**The spine is built and proven** — the work now is the experience layer (Memory OS reskin),
without regressing the spine. Capture a known-good baseline run before any reskin.

| Spine (done — protect) | Status |
|-----|------|
| Cognee spike — remember + recall + forget gates pass | ✅ |
| Multi-hop reversal detection (90 % confidence on ADR-001 flip) | ✅ |
| End-to-end skeleton + SPINE-2 (before → forget → after) | ✅ |
| Improve phase (👍/👎 feedback loop) — proven by `day4_improve.py` | ✅ |

| Re-anchor + experience layer (new plan — see `REQUIREMENTS.md` §10) | Status |
|-----|------|
| D1 — API/snapshot ingestion (markdown corpus killed); reskin `comment.py` → Memory Review card | ✅ (code) |
| D2 — re-anchor decision identity + `forget` ADR-keyed → **PR-keyed** + `.sentinel/retired.json` | ✅ (code) · ⏳ re-prove SPINE-2 live, then delete ADR helpers |
| D3 — `improve` (`/sentinel noise`) wired into the Action; trust-tier confidence on the card | ✅ wired · ⏳ confidence *threshold* gate |
| D4 — north-star dry run on a repo we didn't author (seed via `seed_demo_repo.py`) + FEATURE FREEZE | ❌ |
| D5 — harden/de-risk demo (clean 3×) · D6 — deck + rehearse | ❌ |

**SPINE-1** (multi-hop recall — hop unreachable by vector AND by `#ref`, only graph+semantic) ✅ *(re-verify on PR/issue corpus)*  
**SPINE-2** (forget mutates graph; same PR flips behavior) ✅ *(re-prove on PR-keyed path)*

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
  connection.py       — Groq/Ollama bootstrap; applies config (incl. GRAPH_DATABASE_PROVIDER=ladybug)
  sources.py          — GitHub API ingestion source: fetch_merged_prs/fetch_issues, pr_to_doc/
                        issue_to_doc (pure), the JSON snapshot (load/save_snapshot, snapshot_path),
                        gather_memory()→(prs,issues) from live API or snapshot, incoming_text(slug)
  ingest.py           — remember phase: gather_memory() → cognee.add() + cognee.cognify() (NO files;
                        merged PRs + issues only; skips decisions in .sentinel/retired.json)
  detect.py           — recall + judge phase: graph search → Groq Verdict (Pydantic; PR-keyed
                        decision_reference; assumption/affected_capability/evidence_chain; sets
                        provenance_tier from sentinel.trust). recall takes session_id/feedback_influence.
  resolve.py          — forget phase: mark_intentional() → _pr_number() → retire the PR-keyed decision
                        via cognee.forget() + record in .sentinel/retired.json. (ADR helpers kept dormant
                        for back-compat; remove after SPINE-2 re-proven on PR path.)
  trust.py            — trust tiers (M9): approved (.sentinel/approved.json ∪ SENTINEL_APPROVED_PRS)
                        drives the confident flag; everything else is inferred (soft proposal)
  retired.py          — .sentinel/retired.json ledger (durable forget backstop): record_retired,
                        retired_pr_numbers/retired_data_ids, sentinel_dir()
  improve.py          — improve phase: session feedback (👍/👎) → cognee.improve() re-weights;
                        PR-keyed feedback_signature; durable dismissal in .sentinel/.sentinel-dismissed
  comment.py          — the Memory Review card (approved=confident CAUTION / inferred=soft NOTE)
  github_pr.py        — GitHub REST helpers, event payload parsing, commit/push

.sentinel/              — durable, committable backstops (NOT a memory store)
  api_snapshot.json   — cached API responses (prs/issues/incoming) — offline replay of remember
  retired.json        — retired PR-keyed decisions (skipped on re-ingest)
  approved.json       — human-approved PR numbers (trust tier → confident flag)

scripts/
  seed_demo_repo.py       — CREATE the demo PRs/issues in a real repo via the GitHub API, then
                            regenerate api_snapshot.json + approved.json (SENTINEL_SEED_REPO + token)
  day1_spike.py           — Day 1 gates: remember+recall (SPINE-1) + forget-flips-recall (SPINE-2)
  day2_detect.py          — reversal detection on an incoming PR (slug from the snapshot); prints comment
  day3_flip.py            — full demo loop; emits graph_before.html + graph_after.html
  day4_improve.py         — improve phase: 👎 a flag → cognee.improve() → same + similar PR go silent
  action_entrypoint.py    — GitHub Action entry point (pull_request + issue_comment events)
  wipe.py                 — local dev: wipe Cognee stores for a clean re-ingest

tests/
  test_sentinel.py        — pure-function unit tests (no Cognee, no network); 50 tests

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
- **remember = gather_memory() → add() + cognify()** — `sentinel.sources.gather_memory()` returns
  merged-PR + issue **dicts** from the live GitHub API (caching them to `.sentinel/api_snapshot.json`)
  or replays that snapshot offline. `pr_to_doc`/`issue_to_doc` render each into a type-stamped doc;
  `add()` stages it (stable data_id from the label), `cognify()` extracts cross-document typed edges
  (supersedes, justifies, implements, discussed_in). Only MERGED PRs become memory; the rationale
  comes from the linked **incident issue**, not the PR diff (the basis of the SPINE-1 graph-only hop).
  **There is no markdown corpus** — `incoming_text(slug)` returns the PR-under-review for detection.
- **recall = search(query_type=GRAPH_COMPLETION)** — `only_context=True` returns the raw
  retrieved graph context (no LLM answer), which is the honest before/after measure.
- **judge = Groq LLM grounded in retrieved context only** — the Verdict Pydantic model
  (analysis, reverses_decision, **PR-keyed** decision_reference, original_reasoning, impact_if_merged,
  **assumption, affected_capability, evidence_chain**, confidence) is generated from PR text + graph
  context; LLM never uses training knowledge. CoT `analysis` is first to improve small-model accuracy.
  `provenance_tier` is set AFTER the verdict by `sentinel.trust` (never by the LLM) — approved drives
  the confident flag, inferred a soft proposal (minimal M9 trust gating, §8.1).
- **forget = cognee.forget(data_id=..., dataset=...)** — stable data_ids are derived
  deterministically from the **establishing PR number** (fixed-namespace UUID) so selective forget
  works across CI runner restarts without querying internal Cognee dataset APIs. *(Was keyed on ADR
  filenames; re-anchored to PR number — see Day 2. Re-prove SPINE-2 before deleting the ADR path.)*
- **Retired-decision skip at ingest** — `mark_intentional()` calls `cognee.forget()` on the
  PR-keyed decision node and records its id in **`.sentinel/retired.json`** (non-user-facing). Next
  ingest skips retired ids, making forget durable on top of Cognee's own store persistence — no ADR
  file rewrite, no `memory/` directory. *(Both former file backstops are killed; verify the demo
  runner does not wipe Cognee's stores between the before/after recall.)*
- **improve = session feedback → cognee.improve()** (`sentinel/improve.py`). Distinct from
  forget: forget *retires* an overturned decision node (excluded from active recall); improve only *re-weights*
  memory so it ranks differently — deleting nothing, the decision stays. Loop: (1) detection
  recall runs inside a Cognee *session* (`search(session_id=...)`) so Cognee records the exact
  `used_graph_element_ids` that produced the flag; (2) a maintainer 👎 is stored via
  `cognee.session.add_feedback` (score 1=down … 5=up); (3) `cognee.improve(dataset=…,
  session_ids=[…], feedback_alpha=0.3)` nudges those nodes/edges' `feedback_weight` toward the
  rating (`new = old + alpha*(rating-old)`; a gentle 0.5→~0.35 on a 👎, NOT 0.0 — that would
  read as an erase); (4) the next recall, run with `feedback_influence>0`, gives down-weighted
  triplets a larger effective distance so they rank lower and the retrieved answer shifts —
  but the decision is not evicted/forgotten. Honest because the weights live on the graph and
  are consumed by Cognee's own triplet ranker — a real graph mutation, not a side table.
- **GitHub Action — advisory only** — Sentinel never fails the build. Dry-run mode
  writes to $GITHUB_STEP_SUMMARY; post mode comments on the PR. The `/sentinel
  intentional` reply triggers the issue_comment event path (retire the PR-keyed decision via
  cognee.forget → record in `.sentinel/retired.json` → resolution comment). *(Was: checkout branch
  → supersede ADR → commit/push. The ADR-file path is being removed.)*

## Verified Cognee 1.2.2 API notes (don't guess these)

- Both V1 (`add`/`cognify`/`search`) and V2 (`remember`/`recall`/`forget`/`improve`/`memify`) exist.
- `forget(*, data_id=, dataset=, dataset_id=, everything=, memory_only=, user=)` — keyword-only.
- `SearchType` members include `GRAPH_COMPLETION`, `TRIPLET_COMPLETION`, `CYPHER`,
  `RAG_COMPLETION`, `TEMPORAL` — **there is no `INSIGHTS`**.
- Ollama embeddings require `transformers` (HuggingFace tokenizer) — in requirements
  (`pip install -r requirements.txt`; a bare cognee install does NOT pull it).
- **improve() feedback loop** (verified from source, needed for `sentinel/improve.py`):
  - `improve(dataset=, *, session_ids=, feedback_alpha=0.1, ...)` — keyword `feedback_alpha`
    is the streaming-update step `new = old + alpha*(rating-old)` (must be in `(0, 1]`); we use
    a gentle `0.3` so a 👎 nudges 0.5→~0.35 (a refinement, not an erase — alpha=1.0 would slam
    it to 0.0 and read like forget).
  - `cognee.session.add_feedback(session_id=, qa_id=, feedback_text=, feedback_score=)` —
    score is `1..5`, normalized to `(score-1)/4` (1→0.0 down-weight, 5→1.0 up-weight).
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

## Decision corpus (3 decisions — created in a real repo via the API, replayed from the snapshot)

Each decision is anchored to its **establishing PR**; its rationale lives in a linked **incident
issue** (NOT the PR diff). The data is created in a real GitHub repo by `scripts/seed_demo_repo.py`
and cached to `.sentinel/api_snapshot.json` (PR numbers below are the snapshot's demo numbers; a live
seed assigns real ones and rewrites approved.json).

| Decision (anchor PR) | Decision | Rationale issue | Reversal PR (incoming) |
|-----|----------|-----|-----------------|
| Async email (PR #42) | `email_service` → async via Redis/Celery | issue #91 — Black Friday checkout-latency | #57 — makes checkout email synchronous again |
| Postgres (PR #31) | `orders/payments` → PostgreSQL (not MongoDB) | issue #58 — transactional-integrity | (none — memory-only graph richness) |
| Gateway rate-limit (PR #19) | Rate limiting at Nginx gateway (not app code) | issue #27 — duplicated-limits | #61 `@ratelimit` on views; #63 a *similar* reversal (improve-suppressed) |

**Primary demo target:** the async-email reversal (incoming PR #57 vs anchor PR #42).  
Multi-hop evidence chain: `incoming PR --[reverses]--> EngineeringDecision(PR #42) --[justified_by]--> Incident(issue #91)`.  
**SPINE-1 proof (the bar, VERIFIED on the snapshot):** incoming PR #57 shares **no distinctive words**
with, and has **no `#ref` to**, issue #91 — so vector-only AND GitHub-API-only both miss it; only
graph+semantic recall connects them. *(Distinctive-word overlap measured ≈ empty.)*

## What is NOT implemented yet (post API/PR-keyed re-anchor)

- **Re-prove SPINE-2 on the PR-keyed path (live)** — needs a box with Cognee + Groq + Ollama. The
  forget path is re-anchored to PR-keyed + `.sentinel/retired.json` (code + unit tests green), but the
  before→forget→after graph mutation hasn't been re-run live. **Do this, then delete the dormant ADR
  helpers** (`supersede_adr_file`, `_mark_intentional_adr`, `_adr_number`) in `resolve.py` (§9).
- **Run the seed script against a real repo** — `scripts/seed_demo_repo.py` is written + dry-run-verified
  but not yet executed live (needs `SENTINEL_SEED_REPO` + `GITHUB_TOKEN`). That regenerates the snapshot
  + approved.json with real PR numbers (the north-star: a repo we didn't author).
- **Confidence *threshold* gate** — the card now shows confidence + trust tier, but no numeric threshold
  gates whether a low-confidence inferred flag surfaces at all (S1 noise budget).
- **Capability/Topic layer** — `affected_capability` is filled by the LLM per-verdict; no persistent
  Capability nodes yet (emerges from cognify or lightly seeded).
- **First-class Assumption nodes** — the assumption is surfaced in the card (Verdict.assumption, and the
  issue carries an `assumption:` cross-ref) but not yet modeled as its own node with invalidation edges.
- **Inference guardrail enforcement** — detection should stay silent when no evidence supports a
  rationale; confirm enforced live, not just intended.
- **Incremental ingestion** — re-ingests the whole snapshot each run; no diff-based add.
- **Live issue fetch ↔ snapshot incoming** — `fetch_issues` ingests live issues, but mapping the live
  open reversal PRs back into the snapshot's `incoming` slugs is done by the seed script, not on every run.

**Killed / explicitly cut (roadmap slides, see REQUIREMENTS.md §5 WON'T):** ADRs/Slack/docs as
inputs (killed — PR+issue only); **the markdown corpus + sample files** (killed — all data from the
GitHub API, replayed offline from `.sentinel/api_snapshot.json`); the `memory/` directory artifact
(killed — memory lives in Cognee); code ingestion (deferred); Phase-0 candidate-memory approval queue (the `/sentinel intentional` reply
IS the approval primitive); general "is this any learning?" classifier (live path stays the precise
reversal catch); new-engineer "open file → Engineering Memory" face; MCP "ask-the-graph" face;
multi-repo / multiple contradiction types.

## AI tool disclosure (hackathon rule)

Built with assistance from Claude (Claude Code). Must be disclosed in the final submission.
