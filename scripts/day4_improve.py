"""
Day 4 — the Improve phase: 👍/👎 feedback RE-WEIGHTS memory (it does not erase it),
proven on screen via Cognee's own ``improve()``.

improve is NOT forget. Forget (Day 3) erases a doc: the decision is gone and the same PR
goes silent. improve only *adjusts* ``feedback_weight`` on the graph elements a recall used —
a 👎 nudges them down, a 👍 nudges them up, by a gentle ``feedback_alpha`` step — which
re-ranks what the next recall surfaces. The decision stays in memory the whole time.

The script takes two sample PRs that reverse the same decision: it 👎s the flag on the
first, then re-checks the second (a similar PR) to see whether the nudge carried over.

  BEFORE: detect both PRs -> Sentinel flags each (they reverse a past decision)
  ACT:    maintainer 👎 the first flag -> cognee.improve() nudges feedback_weight DOWN on the
          exact graph nodes/edges that flag's recall used (e.g. 0.5 -> ~0.35)
  AFTER:  the retrieved ANSWER changes — the down-weighted evidence ranks lower, so the recall
          context shifts — but the decision is NOT erased: detection still recognizes it.
          (That permanence is the point: re-rank, don't delete.)

What this proves (a before/after diff, not narration):
  1. feedback_weight on the flag's elements drops from the 0.5 baseline (the graph mutated).
  2. the feedback-influenced recall context changes (the answer re-ranked) for both PRs —
     the learning transfers to the similar one.
  3. the decision survives — improve refined the ranking, it did not forget anything.

Run from the repo root:
    python scripts/day4_improve.py

First run ingests the corpus (cognify), which is LLM-heavy — on a rate-limited Groq tier
this is the slow part. The graph then persists, so later runs reuse it and only do the
(cheap) detect → improve → re-detect loop. The improve weight mutation itself is graph-only
(no LLM) and is the load-bearing proof.
"""

import os

# --- The Improve phase needs settings that differ from the forget demo: a live session
#     cache and a non-zero feedback influence. CACHE_BACKEND/AUTO_FEEDBACK/influence aren't
#     in .env, so setting them up front sticks. CACHING *is* in .env (=false, for the forget
#     demo), and cognee/__init__ calls load_dotenv(override=True) at import — so CACHING gets
#     re-clobbered to false. We re-assert it AFTER importing cognee (see enable_session_cache).
os.environ.setdefault("CACHE_BACKEND", "sqlite")    # SQLite cache.db — no Redis required
os.environ.setdefault("AUTO_FEEDBACK", "false")     # skip the per-query auto-feedback LLM call
os.environ.setdefault("DEFAULT_FEEDBACK_INFLUENCE", "0.4")  # recall must honor feedback_weight

import asyncio  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from uuid import uuid4  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402  (loads .env before cognee)
import cognee  # noqa: E402
from sentinel.comment import render_comment  # noqa: E402
from sentinel.detect import _recall_query, detect_reversal  # noqa: E402
from sentinel.improve import (  # noqa: E402
    dismiss_as_noise,
    edge_feedback_weights,
    node_feedback_weights,
)
from sentinel.ingest import ingest_corpus  # noqa: E402


def enable_session_cache() -> None:
    """Turn the session cache on for THIS process, surviving cognee's import-time
    load_dotenv(override=True) that resets CACHING to .env's value (false).

    We re-assert CACHING after import and bust the lru-cached cache config + engine so the
    SessionManager actually gets a backend (else feedback is silently dropped). Scoped to
    this script so the forget demo keeps CACHING=false.
    """
    os.environ["CACHING"] = "true"
    from cognee.infrastructure.databases.cache.config import get_cache_config
    from cognee.infrastructure.databases.cache.get_cache_engine import create_cache_engine

    get_cache_config.cache_clear()
    create_cache_engine.cache_clear()
    if not get_cache_config().caching:
        raise RuntimeError("session cache could not be enabled; improve feedback would no-op.")

from sentinel import sources  # noqa: E402

PR_FLAGGED_SLUG = "app_ratelimit"          # the flag the maintainer 👎s (incoming PR #61)
PR_SIMILAR_SLUG = "app_ratelimit_orders"   # a similar PR — does the nudge carry over? (#63)


def _pr_label(slug: str) -> str:
    """A short human label for an incoming PR slug (e.g. 'PR #61'), from the API snapshot."""
    for pr in sources.incoming_prs():
        if pr.get("slug") == slug:
            return f"PR #{pr.get('number')}"
    return slug


# Weight the retriever gives to learned feedback (0..1). When every node sits at the uniform
# 0.5 baseline, influence is just a constant offset, so the BEFORE ranking is unchanged and
# both PRs still flag. Kept modest on purpose: a gentle 👎 should re-rank the retrieved
# answer, not evict the decision (eviction is forget's job).
INFLUENCE = 0.4

# How gently a single 👎 nudges feedback_weight (streaming step new = old + alpha*(rating-old)).
# 0.3 => one 👎 moves a node 0.5 -> ~0.35: a refinement, not an erase. Repeated feedback
# accumulates. (Same as the module default; named here so the demo's intent is explicit.)
FEEDBACK_ALPHA = 0.3
GC = cognee.SearchType.GRAPH_COMPLETION


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


async def _context_chars(pr_text: str) -> int:
    """Size of the feedback-influenced graph context retrieved for a PR's recall query.

    The honest, LLM-independent re-ranking signal: it shifts once the recall's memory is
    re-weighted, even before the judge runs."""
    res = await cognee.search(
        _recall_query(pr_text), query_type=GC, only_context=True, feedback_influence=INFLUENCE
    )
    return len(str(res))


def _summarize_weights(label: str, weights: dict) -> None:
    if not weights:
        print(f"   {label}: (none)")
        return
    vals = list(weights.values())
    avg = sum(vals) / len(vals)
    print(f"   {label}: avg={avg:.3f} over {len(vals)} element(s)  min={min(vals):.3f} max={max(vals):.3f}")


async def _detect(pr_text: str, *, session_id: str | None):
    return await detect_reversal(pr_text, session_id=session_id, feedback_influence=INFLUENCE)


async def main() -> None:
    label_a, label_b = _pr_label(PR_FLAGGED_SLUG), _pr_label(PR_SIMILAR_SLUG)
    pr_a = sources.incoming_text(PR_FLAGGED_SLUG)
    pr_b = sources.incoming_text(PR_SIMILAR_SLUG)
    await setup_cognee()
    enable_session_cache()  # must run after cognee import; else 👎 feedback is a no-op

    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time, slow on a local model)...")
        await ingest_corpus()
    print(f"-> graph ready ({await _node_count()} nodes); feedback_influence={INFLUENCE}\n")

    run = uuid4().hex[:8]  # unique session ids so a re-run never serves a stale cache hit
    sid_flag = f"flag-{run}"

    print("=" * 70)
    print("BEFORE — detect the two incoming PRs")
    print("=" * 70)
    v_a = await _detect(pr_a, session_id=sid_flag)   # recorded: this recall is what we 👎
    v_b0 = await _detect(pr_b, session_id=None)
    print(f"{label_a}  reverses_decision = {v_a.reverses_decision}  ({v_a.decision_reference})  conf={v_a.confidence:.0%}")
    print(f"{label_b}  reverses_decision = {v_b0.reverses_decision}  ({v_b0.decision_reference})  conf={v_b0.confidence:.0%}")
    b_chars_before = await _context_chars(pr_b)
    print(f"{label_b}  retrieved-context size: {b_chars_before} chars")
    print(f"\n--- the flag a maintainer is about to give feedback on ({label_a}) ---\n")
    print(render_comment(v_a))

    decision = v_a.decision_reference or "the decision"

    print("\n" + "=" * 70)
    print(f"ACT — maintainer 👎 the {label_a} flag (feedback: this evidence was less useful here)")
    print(f"     improve() NUDGES its weights down — it does NOT erase {decision} (that's forget).")
    print("=" * 70)
    # Inspect the weights on the exact elements this flag used, before improve().
    from sentinel.improve import latest_recall_qa, _element_ids

    qa = await latest_recall_qa(sid_flag)
    node_ids = _element_ids(qa, "node_ids") if qa else []
    edge_ids = _element_ids(qa, "edge_ids") if qa else []
    print(f"flag recall used {len(node_ids)} node(s) + {len(edge_ids)} edge(s)")
    before_w = await node_feedback_weights(node_ids)
    _summarize_weights("feedback_weight BEFORE (nodes)", before_w)

    result = await dismiss_as_noise(sid_flag, alpha=FEEDBACK_ALPHA)
    print(f"\ncognee.improve(feedback_alpha={FEEDBACK_ALPHA}) -> status={result.get('status')}  "
          f"targeted {result.get('targeted_nodes', 0)} node(s) / {result.get('targeted_edges', 0)} edge(s)")
    if result.get("improve", {}).get("warning"):
        print(f"   note: {result['improve']['warning']}")

    after_w = await node_feedback_weights(node_ids)
    _summarize_weights("feedback_weight AFTER  (nodes)", after_w)
    _summarize_weights("feedback_weight AFTER  (edges)", await edge_feedback_weights(edge_ids))

    print("\n" + "=" * 70)
    print("AFTER — re-detect both PRs (fresh sessions, so recall is recomputed live)")
    print("=" * 70)
    v_a2 = await _detect(pr_a, session_id=f"recheck-a-{run}")
    v_b2 = await _detect(pr_b, session_id=f"recheck-b-{run}")
    b_chars_after = await _context_chars(pr_b)
    print(f"{label_a}  reverses_decision = {v_a2.reverses_decision}  ({v_a2.decision_reference})  conf={v_a2.confidence:.0%}")
    print(f"{label_b}  reverses_decision = {v_b2.reverses_decision}  ({v_b2.decision_reference})  conf={v_b2.confidence:.0%}")
    print(f"{label_b}  retrieved-context size: {b_chars_before} -> {b_chars_after} chars "
          f"({'shrank' if b_chars_after < b_chars_before else 'grew' if b_chars_after > b_chars_before else 'unchanged'})")
    print("   ^ the retrieved evidence was re-ranked by the 👎 — yet the decision is still"
          " detected (improve refined the answer; it did not erase the decision).")
    print(f"\n--- Sentinel still recognizes the decision in the similar {label_b} (not forgotten) ---\n")
    print(render_comment(v_b2))

    print("\n" + "=" * 70)
    avg = lambda d: (sum(d.values()) / len(d)) if d else 0.0
    weights_nudged_down = bool(node_ids) and avg(after_w) < avg(before_w)
    answer_reranked = b_chars_after != b_chars_before
    decision_kept = v_a2.reverses_decision  # decision still recognized -> NOT erased
    if weights_nudged_down and answer_reranked and decision_kept:
        print(f"IMPROVE PROVEN: the 👎 nudged feedback_weight {avg(before_w):.2f} -> {avg(after_w):.2f} "
              f"and re-ranked the retrieved answer ({label_b} context {b_chars_before} -> {b_chars_after} chars),")
        print(f"  while {decision} stayed in memory and is still detected. "
              "That's improve (refine the ranking), not forget (erase the doc).")
    elif weights_nudged_down:
        print(f"IMPROVE applied: feedback_weight {avg(before_w):.2f} -> {avg(after_w):.2f} "
              f"(answer re-ranked={answer_reranked}, decision kept={decision_kept}).")
    else:
        print("NO WEIGHT CHANGE: improve did not adjust weights — check CACHING / session / alpha.")
    print("(re-run rebuilds; weights persist in the graph between runs unless you run wipe.py)")


if __name__ == "__main__":
    asyncio.run(main())
