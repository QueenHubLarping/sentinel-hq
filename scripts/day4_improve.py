"""
Day 4 — the Improve phase: a 👎 teaches Sentinel to stop flagging a drift it considers
noise, proven on screen via Cognee's own ``improve()``.

  BEFORE: detect PR #61 (app-level rate limiting) -> Sentinel FLAGS it (reverses ADR-003)
          detect PR #63 (a *similar* app-level rate-limit PR) -> also FLAGGED (baseline)
  ACT:    maintainer 👎 the #61 flag as noise -> cognee.improve() streams that feedback
          onto the exact graph nodes/edges the flag used (feedback_weight 0.5 -> ~0.0)
  AFTER:  detect PR #61 again -> SILENT (the memory it relied on is down-ranked)
          detect PR #63 again -> SILENT too (the *similar future flag* is suppressed)

This is SPINE-2's improve half: a drift-type drops below threshold and stops surfacing,
inspectable as a before/after diff (feedback_weight + retrieved-context size), not narrated.
It is distinct from forget (Day 3): nothing is deleted — memory is re-ranked, and only the
elements the dismissed flag actually used.

Run from the repo root:
    python scripts/day4_improve.py

First run ingests the whole corpus (cognify), which is LLM-heavy — on a rate-limited Groq
tier this is the slow/flaky part. The graph then persists, so later runs reuse it and only
do the (cheap) detect → improve → re-detect loop. The improve weight mutation itself is
graph-only (no LLM) and is the load-bearing proof.
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

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
PR_A = SAMPLES / "incoming_pr_61_app_ratelimit.md"          # the flag we dismiss as noise
PR_B = SAMPLES / "incoming_pr_63_app_ratelimit_orders.md"   # the similar "future" flag

# Weight the retriever gives to learned feedback (0..1). 0.4 leaves baseline relevance
# ranking intact (so #61/#63 still flag before any feedback) while giving a 👎 real bite.
INFLUENCE = 0.4
GC = cognee.SearchType.GRAPH_COMPLETION


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


async def _context_chars(pr_text: str) -> int:
    """Size of the feedback-influenced graph context retrieved for a PR's recall query.

    The honest, LLM-independent suppression signal: it shrinks once the drift's memory is
    down-weighted, even before the judge runs."""
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
    pr_a = PR_A.read_text(encoding="utf-8")
    pr_b = PR_B.read_text(encoding="utf-8")
    await setup_cognee()
    enable_session_cache()  # must run after cognee import; else 👎 feedback is a no-op

    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time, slow on a local model)...")
        await ingest_corpus()
    print(f"-> graph ready ({await _node_count()} nodes); feedback_influence={INFLUENCE}\n")

    run = uuid4().hex[:8]  # unique session ids so a re-run never serves a stale cache hit
    sid_flag = f"flag-61-{run}"

    print("=" * 70)
    print("BEFORE — detect the two incoming rate-limit PRs")
    print("=" * 70)
    v_a = await _detect(pr_a, session_id=sid_flag)   # recorded: this recall is what we 👎
    v_b0 = await _detect(pr_b, session_id=None)
    print(f"PR #61  reverses_decision = {v_a.reverses_decision}  ({v_a.decision_reference})  conf={v_a.confidence:.0%}")
    print(f"PR #63  reverses_decision = {v_b0.reverses_decision}  ({v_b0.decision_reference})  conf={v_b0.confidence:.0%}")
    b_chars_before = await _context_chars(pr_b)
    print(f"PR #63  retrieved-context size: {b_chars_before} chars")
    print("\n--- the flag a maintainer is about to dismiss (PR #61) ---\n")
    print(render_comment(v_a))

    print("\n" + "=" * 70)
    print("ACT — maintainer 👎 the PR #61 flag: 'app-level rate limiting is fine here, stop flagging it'")
    print("=" * 70)
    # Inspect the weights on the exact elements this flag used, before improve().
    from sentinel.improve import latest_recall_qa, _element_ids

    qa = await latest_recall_qa(sid_flag)
    node_ids = _element_ids(qa, "node_ids") if qa else []
    edge_ids = _element_ids(qa, "edge_ids") if qa else []
    print(f"flag recall used {len(node_ids)} node(s) + {len(edge_ids)} edge(s)")
    _summarize_weights("feedback_weight BEFORE (nodes)", await node_feedback_weights(node_ids))

    result = await dismiss_as_noise(sid_flag)
    print(f"\ncognee.improve() -> status={result.get('status')}  "
          f"targeted {result.get('targeted_nodes', 0)} node(s) / {result.get('targeted_edges', 0)} edge(s)")
    if result.get("improve", {}).get("warning"):
        print(f"   note: {result['improve']['warning']}")

    _summarize_weights("feedback_weight AFTER  (nodes)", await node_feedback_weights(node_ids))
    _summarize_weights("feedback_weight AFTER  (edges)", await edge_feedback_weights(edge_ids))

    print("\n" + "=" * 70)
    print("AFTER — re-detect both PRs (fresh sessions, so recall is recomputed live)")
    print("=" * 70)
    v_a2 = await _detect(pr_a, session_id=f"recheck-61-{run}")
    v_b2 = await _detect(pr_b, session_id=f"recheck-63-{run}")
    b_chars_after = await _context_chars(pr_b)
    print(f"PR #61  reverses_decision = {v_a2.reverses_decision}  ({v_a2.decision_reference})  conf={v_a2.confidence:.0%}")
    print(f"PR #63  reverses_decision = {v_b2.reverses_decision}  ({v_b2.decision_reference})  conf={v_b2.confidence:.0%}")
    print(f"PR #63  retrieved-context size: {b_chars_before} -> {b_chars_after} chars "
          f"({'shrank' if b_chars_after < b_chars_before else 'unchanged'})")
    print("\n--- what Sentinel now says about the *similar* PR #63 ---\n")
    print(render_comment(v_b2))

    print("\n" + "=" * 70)
    dismissed_suppressed = v_a.reverses_decision and not v_a2.reverses_decision
    similar_suppressed = v_b0.reverses_decision and not v_b2.reverses_decision
    context_shrank = b_chars_after < b_chars_before
    if dismissed_suppressed and similar_suppressed:
        print("IMPROVE PROVEN: 👎 suppressed the dismissed flag AND the similar future flag.")
    elif dismissed_suppressed or context_shrank:
        print("IMPROVE PROVEN (partial): the dismissed drift is down-ranked after feedback "
              f"(#61 flip={dismissed_suppressed}, #63 context shrank={context_shrank}).")
    else:
        print("NO SUPPRESSION: feedback did not change recall — check CACHING / influence / alpha.")
    print("(re-run to repeat; weights persist in the graph between runs)")


if __name__ == "__main__":
    asyncio.run(main())
