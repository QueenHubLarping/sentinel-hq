"""
improve demo — a 👎 makes a drift stop surfacing (the improve loop, on screen).

  BEFORE:  detect the sample PR  -> Sentinel FLAGS the ADR-001 reversal.
  ACT:     team replies '/sentinel noise' -> record_noise() writes a 👎 into the graph.
  AFTER:   detect the SAME PR  -> Sentinel is QUIET (flag suppressed by feedback).

This proves success-criterion #4 (REQUIREMENTS §6): a dismissed drift type stops
surfacing after feedback — read live from the graph, not a cached verdict. Unlike
forget (which retires the *decision*), improve suppresses the *flag*: the reversal is
still detected, Sentinel just respects the team's 👎 and stays quiet.

Run from the repo root (after `ollama serve`):
    python scripts/improve_demo.py [path/to/pr.md]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402  (loads .env before cognee)
import cognee  # noqa: E402
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.improve import dismissed_signatures, record_noise  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402

DEFAULT_PR = Path(__file__).resolve().parent.parent / "samples" / "incoming_pr_57_sync_email.md"


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _show(label: str, v) -> None:
    flag = "🚩 FLAGGED" if v.should_flag else ("🔕 MUTED" if v.suppressed_by_feedback else "✅ silent")
    print(f"\n=== {label} ===")
    print(f"  reverses_decision    : {v.reverses_decision}")
    print(f"  suppressed_by_feedback: {v.suppressed_by_feedback}")
    print(f"  decision_reference   : {v.decision_reference}")
    print(f"  -> Sentinel verdict  : {flag}")


async def main() -> None:
    pr_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PR
    pr_text = pr_path.read_text(encoding="utf-8")

    await setup_cognee()
    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time)...")
        await ingest_corpus()
    else:
        print(f"-> reusing existing graph ({await _node_count()} nodes).")

    # BEFORE — the flag fires.
    before = await detect_reversal(pr_text)
    _show("BEFORE feedback", before)
    if not before.should_flag:
        print("\n(!) Expected a flag before feedback — is the corpus ingested? Aborting.")
        return

    # ACT — the team says '/sentinel noise'.
    print(f"\n-> team replies '/sentinel noise' on the {before.decision_reference} flag")
    result = await record_noise(before.decision_reference)
    print(f"   record_noise -> {result}")
    print(f"   dismissed signatures now in graph: {sorted(await dismissed_signatures())}")

    # AFTER — same PR, now muted.
    after = await detect_reversal(pr_text)
    _show("AFTER feedback (same PR)", after)

    flipped = before.should_flag and not after.should_flag and after.suppressed_by_feedback
    print("\n" + ("=" * 60))
    print("RESULT:", "✅ improve works — flagged -> muted after 👎." if flipped
          else "❌ unexpected — the flag did not get suppressed.")


if __name__ == "__main__":
    asyncio.run(main())
