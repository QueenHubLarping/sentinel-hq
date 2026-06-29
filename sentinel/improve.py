"""
Improve phase — the 👍/👎 feedback loop, built on Cognee's own ``improve()``.

forget retires a decision the team *overturned* — it erases the doc. improve is
different and gentler: 👍/👎 only *re-weight* the memory a recall used, nudging how it
ranks next time. Nothing is deleted; the decision stays in the graph. We do this
honestly through Cognee's memory lifecycle, not a side table:

  1. recall runs inside a Cognee *session* (``search(session_id=...)``), so Cognee
     records exactly which graph nodes/edges produced the flag
     (``used_graph_element_ids`` on the session Q&A entry).
  2. the maintainer's verdict is stored as session feedback
     (``cognee.session.add_feedback``, score 1..5).
  3. ``cognee.improve(dataset=..., session_ids=[...])`` streams that score onto the
     graph: ``feedback_weight`` is nudged toward the rating by ``feedback_alpha`` —
     ``new = old + alpha*(rating - old)``. With a deliberately gentle alpha, a single 👎
     nudges a node from 0.5 *toward* 0 (e.g. ~0.35) and a 👍 *toward* 1 (~0.65);
     repeated feedback accumulates. improve *adjusts* the weight; it never deletes.
  4. the next recall runs with ``feedback_influence > 0``, so a down-weighted element
     gets a slightly larger effective distance and ranks lower — re-shaping the
     retrieved answer. The decision is NOT erased and may still surface; improve
     refines the ranking, forget removes the doc.

Why this is the genuine Cognee verb, not a bolt-on: the weights live on the graph
nodes themselves and are consumed by Cognee's own triplet ranker
(``CogneeGraph.calculate_top_triplet_importances``). Remove Cognee and there is no
feedback-aware recall to re-rank.

Runtime requirements (the Day-4 script sets these *before* importing cognee):
  - ``CACHING=true``       — the session cache must be live, else feedback is a no-op.
                            Default backend is SQLite (a ``cache.db``; no Redis needed).
  - ``DEFAULT_FEEDBACK_INFLUENCE`` > 0 (or pass feedback_influence per call) — else the
                            retriever ignores ``feedback_weight`` entirely.

These differ from the forget demo (which runs ``CACHING=false`` so deletions show in
recall immediately), so the Improve phase is exercised by its own script.
"""

import cognee

from sentinel.ingest import DATASET_NAME

# Feedback scores map to a normalized rating in [0, 1] (Cognee uses (score-1)/4):
#   score 1 -> rating 0.0  (the target a 👎 nudges toward)
#   score 5 -> rating 1.0  (the target a 👍 nudges toward)
THUMBS_DOWN = 1
THUMBS_UP = 5

# Step size for the streaming weight update inside improve(): new = old + alpha*(rating-old).
# Kept gentle (0.3) ON PURPOSE: a single 👎 nudges a node 0.5 -> ~0.35 (and a 👍 -> ~0.65),
# a refinement — not 0.0/1.0, which would read like an erase/forget. Repeated feedback
# accumulates toward the rating. Cognee requires alpha in (0, 1]; raise it for a more
# decisive move, lower it for an even subtler nudge.
DEFAULT_FEEDBACK_ALPHA = 0.3


def _element_ids(entry, key: str) -> list[str]:
    """Pull node_ids / edge_ids off a session Q&A entry, tolerating missing data."""
    used = getattr(entry, "used_graph_element_ids", None) or {}
    values = used.get(key) if isinstance(used, dict) else None
    return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []


async def latest_recall_qa(session_id: str):
    """Return the most recent session Q&A entry (the recall we'll give feedback on)."""
    entries = await cognee.session.get_session(session_id)
    return entries[-1] if entries else None


async def node_feedback_weights(node_ids: list[str]) -> dict[str, float]:
    """Current ``feedback_weight`` for the given graph nodes (the before/after probe)."""
    if not node_ids:
        return {}
    from cognee.infrastructure.databases.graph import get_graph_engine

    engine = await get_graph_engine()
    return await engine.get_node_feedback_weights(node_ids)


async def edge_feedback_weights(edge_ids: list[str]) -> dict[str, float]:
    """Current ``feedback_weight`` for the given graph edges."""
    if not edge_ids:
        return {}
    from cognee.infrastructure.databases.graph import get_graph_engine

    engine = await get_graph_engine()
    return await engine.get_edge_feedback_weights(edge_ids)


async def record_feedback(session_id: str, qa_id: str, *, score: int, note: str = "") -> bool:
    """Attach a 1..5 feedback score (and optional note) to a session Q&A entry."""
    return await cognee.session.add_feedback(
        session_id=session_id,
        qa_id=qa_id,
        feedback_text=note or None,
        feedback_score=score,
    )


async def apply_improvement(
    session_id: str,
    *,
    alpha: float = DEFAULT_FEEDBACK_ALPHA,
    dataset: str = DATASET_NAME,
) -> dict:
    """Run ``cognee.improve`` to stream this session's feedback onto the graph.

    improve() applies feedback weights FIRST and persists them before its later
    enrichment stages (Q&A persistence, triplet re-embedding) run. Those tail stages
    make extra LLM/embedding calls that can be flaky on a small local model, so we
    isolate them: if a tail stage raises, the weight update Sentinel actually needs is
    already committed, and we surface a warning instead of failing the loop.
    """
    try:
        result = await cognee.improve(
            dataset=dataset,
            session_ids=[session_id],
            feedback_alpha=alpha,
        )
        return {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001 — tail-stage failure must not lose the applied weights
        return {"ok": True, "warning": f"improve() tail-stage error (weights already applied): {exc}"}


async def _act_on_flag(session_id: str, *, score: int, note: str, alpha: float, dataset: str) -> dict:
    """Shared body for dismiss/reinforce: score the latest recall, then improve()."""
    entry = await latest_recall_qa(session_id)
    if entry is None or not getattr(entry, "qa_id", None):
        return {
            "status": "no_recall",
            "note": (
                f"No recorded recall found in session {session_id!r}. Run detection with "
                "session_id set (and CACHING enabled) before giving feedback."
            ),
        }

    node_ids = _element_ids(entry, "node_ids")
    edge_ids = _element_ids(entry, "edge_ids")
    if not node_ids and not edge_ids:
        return {
            "status": "no_graph_elements",
            "qa_id": entry.qa_id,
            "note": "Recall recorded no used_graph_element_ids; nothing to re-weight.",
        }

    if not await record_feedback(session_id, entry.qa_id, score=score, note=note):
        return {"status": "feedback_failed", "qa_id": entry.qa_id}

    improve_result = await apply_improvement(session_id, alpha=alpha, dataset=dataset)
    return {
        "status": "improved",
        "qa_id": entry.qa_id,
        "score": score,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "targeted_nodes": len(node_ids),
        "targeted_edges": len(edge_ids),
        "improve": improve_result,
    }


async def dismiss_as_noise(
    session_id: str,
    *,
    note: str = "Maintainer feedback: de-emphasise this evidence (less useful here).",
    alpha: float = DEFAULT_FEEDBACK_ALPHA,
    dataset: str = DATASET_NAME,
) -> dict:
    """👎 the most recent flag in this session: record a low score, then ``improve()``.

    Nudges ``feedback_weight`` down (toward 0, by ``alpha``) on the graph elements that
    produced the flag, so the next feedback-influenced recall ranks them lower — refining
    the answer. It does NOT delete them: the decision stays in memory (that's forget's job).
    """
    return await _act_on_flag(
        session_id, score=THUMBS_DOWN, note=note, alpha=alpha, dataset=dataset
    )


async def reinforce(
    session_id: str,
    *,
    note: str = "Confirmed by maintainer as a real, valuable catch.",
    alpha: float = DEFAULT_FEEDBACK_ALPHA,
    dataset: str = DATASET_NAME,
) -> dict:
    """👍 the most recent flag: record a high score, then ``improve()`` to reinforce it.

    The mirror of dismiss_as_noise — drives ``feedback_weight`` toward 1 so the catch
    ranks even higher next time. Kept for completeness and queryability (M6).
    """
    return await _act_on_flag(
        session_id, score=THUMBS_UP, note=note, alpha=alpha, dataset=dataset
    )
