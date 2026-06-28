# Sentinel — CLAUDE.md

Decision-reversal guardian for code review, built on Cognee.
Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5 2026). Track: Best Use of Open Source.

# Judging criteria:

- 01
Potential Impact
How effectively does the project address a meaningful problem or unlock a valuable use case with persistent AI memory?
- 02
Creativity & Innovation
How unique is the idea? Does it push the boundaries of what's possible when an agent never forgets?
- 03
Technical Excellence
How well is the project implemented? Does it demonstrate strong engineering practices and clean, maintainable code?

- 04
Best Use of Cognee
How deeply and effectively does the project lean on Cognee's memory lifecycle APIs and its hybrid graph-vector memory layer?

- 05
User Experience
Is the project intuitive to use? Does it provide a polished experience that users would actually want to adopt?

- 06
Presentation Quality
How clearly is the project presented? Do the demo, README, and submission communicate the problem, solution, and impact?

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.template .env
# Fill in:
#   COGNEE_CLOUD_URL=https://your-tenant.aws.cognee.ai
#   COGNEE_CLOUD_API_KEY=your_key_here
# (Sign up at https://app.cognee.ai — use code COGNEE-35 for the free Developer plan)

# 4. Run Day 1 spike
python scripts/day1_spike.py
```

## Project layout

```
sentinel/
  connection.py     — Cognee Cloud setup (setup_cognee called once at startup)
  ingest.py         — pushes curated decision corpus to Cognee Cloud via remember()
corpus/
  adrs/             — Architecture Decision Records (markdown)
  slack/            — static "Slack" conversation exports (markdown)
  prs/              — PR metadata (markdown)
scripts/
  day1_spike.py     — Day 1 gates: ingest + verify recall + forget
```

## Architecture decisions

- **Cognee Cloud exclusively** — no self-hosted fallback. LLM, embeddings, and graph
  storage are all handled by Cognee Cloud. Zero local infrastructure to manage.
- **cognee.remember() for corpus ingestion** — structured markdown with explicit
  relationship labels (justified_by, discussed_in, implemented_in) so Cognee extracts
  typed edges. Simpler and more reliable than managing local DataPoints.
- **cognee.recall() for retrieval** — the V2 memory API; cleaner than search() for
  agent-style queries.
- **cognee.forget() for the SPINE-2 demo** — dataset-level forget proves behavior
  change on screen. Day 4 adds node-level retire (active → retired) for the PR flip demo.

## The one contradiction type (corpus)

email_service → async via Redis/Celery (ADR-001, PR #42).
Detection target: a PR that makes email sending synchronous again.
Multi-hop evidence chain: PRRecord --[reverses]--> EngineeringDecision --[justified_by]--> ArchitecturalReason
Source types crossed: PR diff (incoming) + ADR (corpus) + Slack (corpus) = ≥2 hops, ≥2 source types.
This is the SPINE-1 proof: vector-only search on the PR diff alone cannot reach the Slack rationale.