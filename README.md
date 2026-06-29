# 🛡️ Sentinel

**A GitHub Action that catches when a PR silently reverses a past engineering decision — and tells you *why* that decision was made.** Built on [Cognee](https://www.cognee.ai/)'s knowledge-graph memory, using Groq reasoning and local Ollama embeddings.

> Other bots review your code against the internet's conventions. **Sentinel reviews it against yours.**

## The problem

Codebases remember *what* changed, never *why*. Months later someone opens a PR to "simplify" something — and unknowingly undoes a deliberate decision the team made for a reason nobody remembers. Sentinel is the institutional memory that catches it.

## How it works

1. **remember** — ingest ADRs, PRs, commits, and Slack threads into a Cognee knowledge graph.
2. **recall** — on each PR, multi-hop traverse the graph to find any decision the change contradicts, *and its rationale*.
3. **comment** — if it reverses a past decision, Sentinel comments with the reasoning trail and asks "intentional?"
4. **forget** — when the team confirms an intentional override, the old decision is retired (so the bot stops crying wolf).
5. **improve** — a maintainer's 👍/👎 on a flag is stored as session feedback and fed to `cognee.improve()`, which gently nudges the `feedback_weight` on the exact graph nodes that flag used (a 👎 down, a 👍 up); the next feedback-influenced recall ranks that evidence accordingly, re-shaping the retrieved answer. Unlike forget, nothing is deleted — the decision stays in memory; improve just refines the ranking.

## Groq reasoning + local memory

The reasoning LLM (`llama-3.3-70b-versatile`) runs on **Groq**. Embeddings
(`nomic-embed-text`) run on local **Ollama**, while graph/vector/relational stores
remain local files. Document and PR text sent for reasoning is transmitted to Groq.

```bash
ollama serve && ollama pull nomic-embed-text
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
# Set GROQ_API_KEY in .env
python scripts/day1_spike.py
```

See [`CLAUDE.md`](CLAUDE.md) for architecture and [`REQUIREMENTS.md`](REQUIREMENTS.md) for goals and the build plan.

## Quick start

```bash
# 1. Start Ollama embeddings
ollama serve
ollama pull nomic-embed-text

# 2. Python env
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Set your Groq key
cp .env.template .env
# edit .env and set GROQ_API_KEY=your-key

# 4. Run the detection demo (graph auto-ingested on first run)
python scripts/day2_detect.py

# 5. Run the full flip demo (flag → intentional → silent)
python scripts/day3_flip.py

# 6. Run the improve demo (👎 a flag → cognee.improve() → similar PR no longer flagged)
python scripts/day4_improve.py
```

## Status

- **Day 1** ✅ — Self-hosted Cognee verified end-to-end (remember → recall → forget).
- **Day 2** ✅ — Reversal detection working: 90% confidence catch on ADR-001 reversal.
- **Day 3** ✅ — Full flip proven: same PR flagged before forget, silent after.
- **Day 4** ✅ — Improve phase: a 👎 routed through `cognee.improve()` gently re-weights the
  flag's memory (feedback_weight nudged down), re-ranking the retrieved evidence — without
  erasing the decision (that's forget).

## Tests

Pure-function tests (no Cognee, no network) run anywhere:

```bash
pip install pytest
pytest tests/
```

---

_Built with assistance from Claude (Claude Code) — disclosed per hackathon rules._
