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

# 4. Run the Day 1 spike
python scripts/day1_spike.py
```

## Project layout

```
sentinel/
  connection.py     — Groq/Ollama bootstrap; applies config + checks local embeddings
  ingest.py         — remember phase: cognee.add() + cognee.cognify() over the corpus
corpus/
  adrs/             — Architecture Decision Records (markdown)
  slack/            — static "Slack" conversation exports (markdown)
  prs/              — PR metadata (markdown)
scripts/
  day1_spike.py     — Day 1 gates: remember+recall (SPINE-1) and forget-flips-recall (SPINE-2)
```

## Architecture decisions

- **Self-hosted Cognee with Groq reasoning and local embeddings.** The LLM
  (`llama-3.3-70b-versatile`) runs through Groq; embeddings (`nomic-embed-text`) run
  on local Ollama. Graph (Kuzu), vector (LanceDB), and relational (SQLite) stores are
  local files. Config is env-driven (`.env`), applied in `sentinel/connection.py`.
- **Single-user/local posture** — `ENABLE_BACKEND_ACCESS_CONTROL=false` (set before
  `import cognee`) disables multi-tenant auth so scripts run without a user/session.
- **remember = add() + cognify()** — each ADR/PR/Slack doc is added separately and
  tagged with its source type so cognify extracts cross-document edges. (Typed edges
  are an extraction outcome to *verify*, not assume — see SPINE-1.)
- **recall = search(query_type=GRAPH_COMPLETION)** — `only_context=True` returns the raw
  retrieved graph context (no LLM answer), which is the honest before/after measure.
- **forget = cognee.forget(dataset=...)** — note the kwarg is `dataset`, not
  `dataset_name`. Dataset-level forget proves SPINE-2 on Day 1; Day 4 swaps to
  node-level retire (active → retired) for the PR-flip demo.

## Verified Cognee 1.2.2 API notes (don't guess these)

- Both V1 (`add`/`cognify`/`search`) and V2 (`remember`/`recall`/`forget`/`improve`/`memify`) exist.
- `forget(*, data_id=, dataset=, dataset_id=, everything=, memory_only=, user=)` — keyword-only.
- `SearchType` members include `GRAPH_COMPLETION`, `TRIPLET_COMPLETION`, `CYPHER`,
  `RAG_COMPLETION`, `TEMPORAL` — **there is no `INSIGHTS`**.
- Ollama embeddings require `transformers` (HuggingFace tokenizer) — in requirements.

## The one contradiction type (corpus)

`email_service` → async via Redis/Celery (ADR-001, PR #42).
Detection target: a PR that makes email sending synchronous again.
Multi-hop evidence chain: `PRRecord --[reverses]--> EngineeringDecision --[justified_by]--> ArchitecturalReason`.
Source types crossed: PR diff (incoming) + ADR (corpus) + Slack (corpus) = ≥2 hops, ≥2 source types.
SPINE-1 proof: vector-only search on the PR diff alone cannot reach the Slack rationale.

## AI tool disclosure (hackathon rule)

Built with assistance from Claude (Claude Code). Must be disclosed in the final submission.
