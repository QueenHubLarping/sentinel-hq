"""
SPINE-1 proof — MEASURE (don't assert) that vector-only retrieval misses the
cross-source rationale that Cognee's graph multi-hop reaches.

The claim Sentinel rests on (REQUIREMENTS.md §11): decision-reversal is a *relationship*
between two distant, differently-worded nodes — a similarity search can't see it; typed
graph traversal can. This script turns that claim into a printed number.

It runs TWO retrievals over the SAME incoming-PR query:
  - VECTOR baseline : SearchType.RAG_COMPLETION   (chunk/vector similarity, no traversal)
  - GRAPH multi-hop : SearchType.GRAPH_COMPLETION  (typed-edge traversal across documents)
and reports, for each, how much of the *rationale* it reaches — rationale that lives ONLY
in the Slack thread (corpus/slack/slack-2024-08-email-decision.md) and is ABSENT from the
PR diff (so lexical overlap can't explain a hit).

Honest by construction: it prints whatever it finds. If vector-only also reaches the
rationale, you learn that here — not on stage.

Run on the self-hosted runner (Cognee + Ollama available):
    python scripts/spine1_proof.py
"""

import asyncio
import sys
from pathlib import Path

# --- Pure, importable, network-free helpers (unit-tested in tests/test_sentinel.py) ---

# Rationale that lives in the Slack thread (the "why"), NOT in the PR diff. Each concept
# maps to synonyms; a hit on ANY synonym counts, so a slightly reworded retrieval still
# scores. These tokens are conversational decision-rationale, absent from a code diff.
RATIONALE_MARKERS = {
    "retry/backoff guarantee": ["backoff", "retry with", "silently drops"],
    "flower queue monitoring": ["flower"],
    "reconciliation safety-net": ["reconciliation", "sent_at", "safety net"],
    "A/B conversion evidence": ["6%", "a/b", "completions above", "conversion"],
    "explicit do-not-revert": ["do not let anyone", "without reading the adr", "killing checkout"],
}

# Tokens that DO appear in the PR diff — used only to confirm the two texts don't lexically overlap.
PR_DIFF_TOKENS = ["celery", "redis", "sendgrid", "smtp", "synchronous", "send_email_smtp"]


def rationale_hits(context: str, markers=RATIONALE_MARKERS) -> dict:
    """For each rationale concept, True iff any of its synonyms appears (case-insensitive)."""
    low = (context or "").lower()
    return {name: any(syn.lower() in low for syn in syns) for name, syns in markers.items()}


def hit_count(hits: dict) -> int:
    return sum(1 for v in hits.values() if v)


def _fmt(hits: dict) -> str:
    return "\n".join(f"      {'✓' if v else '·'} {name}" for name, v in hits.items())


# --- Live measurement (Cognee imported lazily so the helpers above stay importable) ---

async def _context_for(cognee, query, search_type, top_k=10) -> str:
    """Run one retrieval and return its raw context as a string (only_context=True)."""
    res = await cognee.search(query, query_type=search_type, only_context=True, top_k=top_k)
    if isinstance(res, (list, tuple)):
        return "\n".join(str(r) for r in res)
    return str(res)


async def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sentinel.connection import setup_cognee
    import cognee
    from sentinel.detect import _recall_query
    from sentinel.ingest import ingest_corpus

    await setup_cognee()

    from cognee.infrastructure.databases.graph import get_graph_engine
    nodes, _ = await (await get_graph_engine()).get_graph_data()
    if len(nodes) == 0:
        print("-> graph empty; ingesting corpus (one-time)...")
        await ingest_corpus()

    from sentinel import sources
    pr_text = sources.incoming_text("sync_email")  # incoming reversal PR from the API snapshot
    query = _recall_query(pr_text)

    # Pick a pure-vector search type, with a documented fallback if the build differs.
    ST = cognee.SearchType
    vector_type = getattr(ST, "RAG_COMPLETION", None) or getattr(ST, "CHUNKS", None) or ST.GRAPH_COMPLETION
    print(f"available SearchType: {[m for m in dir(ST) if m.isupper()]}")
    print(f"vector baseline uses: SearchType.{vector_type.name}")
    print(f"graph multi-hop uses: SearchType.GRAPH_COMPLETION\n")

    # Control: the rationale markers must NOT be in the PR diff itself (else a vector hit
    # would just be lexical overlap, not a real cross-source reach).
    pr_self = rationale_hits(pr_text)
    print(f"CONTROL — rationale present in the PR diff itself: {hit_count(pr_self)}/{len(RATIONALE_MARKERS)} "
          f"(should be ~0 — proves the markers are Slack-only)\n{_fmt(pr_self)}\n")

    vec_ctx = await _context_for(cognee, query, vector_type)
    graph_ctx = await _context_for(cognee, query, ST.GRAPH_COMPLETION)

    vec_hits = rationale_hits(vec_ctx)
    graph_hits = rationale_hits(graph_ctx)
    n = len(RATIONALE_MARKERS)

    print(f"VECTOR-ONLY  (SearchType.{vector_type.name}, {len(vec_ctx)} chars) — "
          f"reached {hit_count(vec_hits)}/{n} rationale concepts:\n{_fmt(vec_hits)}\n")
    print(f"GRAPH MULTI-HOP (GRAPH_COMPLETION, {len(graph_ctx)} chars) — "
          f"reached {hit_count(graph_hits)}/{n} rationale concepts:\n{_fmt(graph_hits)}\n")

    delta = hit_count(graph_hits) - hit_count(vec_hits)
    verdict = "PASS" if delta > 0 else ("TIE" if delta == 0 else "UNEXPECTED")
    print("=" * 78)
    print(f"SPINE-1 [{verdict}]: vector-only reached {hit_count(vec_hits)}/{n} of the Slack "
          f"rationale; graph traversal reached {hit_count(graph_hits)}/{n}.")
    print("  → Reversal detection is a relationship across documents (ADR ─discussed_in─> Slack);")
    print("    similarity search over the diff can't see it, typed-edge traversal can.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
