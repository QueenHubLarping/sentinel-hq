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

----------------------------------------------------------------------------------------
Two surfaces, one verb. The native re-weighting above is the on-screen proof
(scripts/day4_improve.py, CACHING=true). The GitHub Action runs in a different context —
ephemeral runners with no persistent session cache between the detect run and the
'/sentinel noise' run — so the live loop records the 👎 as a durable, git-committed
dismissal instead (the "Durable dismissal store" section at the bottom of this file),
which the next detection reads. Same intent (the team's 👎 reshapes the next recall),
two transports for two runtimes.
"""

import re
from pathlib import Path
from uuid import uuid5

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


# ===========================================================================
# Durable dismissal store — the Action-side transport of the SAME 👎 intent.
# ===========================================================================
# The native re-weighting above needs a live session cache (CACHING=true) and a
# persistent graph, which the ephemeral GitHub runner doesn't have between the detect
# run and the '/sentinel noise' run. So in CI the 👎 is recorded as a drift signature
# committed to the consuming repo (mirroring how forget commits the ADR supersession),
# which the next detection reads. is_dismissed feeds detect.detect_reversal's
# suppressed_by_feedback. Local dev has no GITHUB_WORKSPACE and can also keep the
# signature in the graph via a marker (graph_dismissed_signatures).

from cognee.tasks.ingestion.data_item import DataItem  # noqa: E402
from sentinel.ingest import _SENTINEL_NS  # noqa: E402
from sentinel.resolve import _adr_number, _pr_number  # noqa: E402
from sentinel.retired import sentinel_dir  # noqa: E402

FEEDBACK_NODE_SET = "sentinel_feedback"

# Distinctive, machine-parseable marker so dismissals can be found deterministically
# in the graph (a substring scan over node data), independent of LLM recall.
_MARKER = "SENTINEL-DISMISSED-DRIFT"
_MARKER_RE = re.compile(rf"{_MARKER}:\s*([A-Za-z0-9\-]+)")


def feedback_signature(decision_reference: str) -> str:
    """Normalize a decision reference into a stable drift signature (the feedback key).

    PR-keyed references collapse to their canonical id ('PR #42 (async email)' -> 'PR-42');
    legacy ADR references collapse to 'ADR-001'; anything else is slugified so it is still a
    stable, comparable key. PR is checked first — the new identity — ADR second (back-compat).
    """
    pr = _pr_number(decision_reference)
    if pr is not None:
        return f"PR-{pr}"
    adr = _adr_number(decision_reference)
    if adr:
        return adr
    slug = re.sub(r"[^a-z0-9]+", "-", (decision_reference or "").lower()).strip("-")
    return slug or "unknown"


def _feedback_doc(signature: str, decision_reference: str, pr_number: int | None, note: str) -> str:
    where = f" on PR #{pr_number}" if pr_number else ""
    body = (
        f"[source_type: SentinelFeedback] [{_MARKER}: {signature}]\n\n"
        f"# Team feedback: the '{signature}' reversal flag was dismissed as noise\n\n"
        f"A maintainer reviewed Sentinel's flag that a change reverses **{decision_reference}**"
        f"{where} and marked it as NOISE — an unhelpful false-positive drift pattern, not an "
        f"intentional override of the decision. Per this team feedback, Sentinel should NOT "
        f"raise the '{signature}' reversal again.\n"
    )
    if note:
        body += f"\nMaintainer note: {note}\n"
    return body


async def record_noise(decision_reference: str, pr_number: int | None = None, note: str = "") -> dict:
    """Write a 👎 into the graph: dismiss the *decision_reference* drift as noise (improve).

    Idempotent — repeated dismissals of the same drift reuse a stable data_id, so a
    second ``/sentinel noise`` just refreshes the existing feedback record. Used by the
    local proof; the Action uses record_noise_file (durable on ephemeral runners).
    """
    signature = feedback_signature(decision_reference)
    doc = _feedback_doc(signature, decision_reference, pr_number, note)
    data_id = uuid5(_SENTINEL_NS, f"feedback::{signature}")

    item = DataItem(data=doc, label=f"feedback-{signature}.md", data_id=data_id)
    await cognee.add(item, dataset_name=DATASET_NAME, node_set=[FEEDBACK_NODE_SET])
    await cognee.cognify(datasets=[DATASET_NAME])

    # Also invoke the native verb where supported — it weights feedback into recall.
    # Non-fatal: the deterministic marker scan is what guarantees the suppression.
    try:
        await cognee.improve(DATASET_NAME)
    except Exception:
        pass

    return {"status": "recorded", "signature": signature, "decision": decision_reference}


async def graph_dismissed_signatures() -> set[str]:
    """Drift signatures dismissed *in the graph* — a deterministic marker scan.

    This is what powers the local before/after proof (the graph persists between runs
    on a dev box), and does not depend on the LLM surfacing the feedback node.
    """
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    found: set[str] = set()
    for node in nodes:
        for m in _MARKER_RE.finditer(str(node)):
            found.add(m.group(1))
    return found


def dismissed_file() -> Path:
    """Path to the durable dismissal store — in `.sentinel/`, alongside retired.json."""
    return sentinel_dir() / ".sentinel-dismissed"


def file_dismissed_signatures() -> set[str]:
    """Drift signatures dismissed in the committed file (empty if the file is absent)."""
    path = dismissed_file()
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def record_noise_file(decision_reference: str) -> Path:
    """Append this drift's signature to the durable dismissal file (idempotent)."""
    signature = feedback_signature(decision_reference)
    path = dismissed_file()
    existing = file_dismissed_signatures()
    if signature not in existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "" if path.exists() else "# Drift signatures the team dismissed via '/sentinel noise'.\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}{signature}\n")
    return path


async def dismissed_signatures() -> set[str]:
    """All dismissed drift signatures: the durable file (CI) ∪ the graph (local)."""
    return file_dismissed_signatures() | await graph_dismissed_signatures()


async def is_dismissed(decision_reference: str) -> bool:
    """True if the team has marked this decision's drift as noise (👎)."""
    return feedback_signature(decision_reference) in await dismissed_signatures()
