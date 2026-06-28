"""
Day 3 — the full loop / demo money-shot: same PR, opposite behavior, because memory
was forgotten.

  BEFORE: detect the PR -> Sentinel FLAGS it (reverses ADR-001)
  ACT:    team replies '/sentinel intentional' -> the decision is retired (forget)
  AFTER:  detect the SAME PR -> Sentinel is SILENT (the decision it protected is gone)

Proves SPINE-2 in the real product flow: deletion changes the next decision, live.

Run from the repo root:
    python scripts/day3_flip.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402
import cognee  # noqa: E402
from sentinel.comment import render_comment  # noqa: E402
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel.resolve import mark_intentional  # noqa: E402

PR_PATH = Path(__file__).resolve().parent.parent / "samples" / "incoming_pr_57_sync_email.md"


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


async def main() -> None:
    pr_text = PR_PATH.read_text(encoding="utf-8")
    await setup_cognee()

    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time, slow)...")
        await ingest_corpus()
    print(f"-> graph ready ({await _node_count()} nodes)\n")

    print("=" * 64)
    print("BEFORE — detect the incoming PR")
    print("=" * 64)
    v1 = await detect_reversal(pr_text)
    print(f"reverses_decision = {v1.reverses_decision} ({v1.decision_reference})\n")
    print(render_comment(v1))

    print("\n" + "=" * 64)
    print("ACT — maintainer replies '/sentinel intentional'")
    print("=" * 64)
    print("retiring the superseded decision (forget) ->", await mark_intentional(v1.decision_reference))
    print(f"graph nodes now: {await _node_count()}")

    print("\n" + "=" * 64)
    print("AFTER — detect the SAME PR again")
    print("=" * 64)
    v2 = await detect_reversal(pr_text)
    print(f"reverses_decision = {v2.reverses_decision} ({v2.decision_reference})\n")
    print(render_comment(v2))

    print("\n" + "=" * 64)
    flipped = v1.reverses_decision and not v2.reverses_decision
    print(f"{'FLIP PROVEN' if flipped else 'NO FLIP'}: same PR, "
          f"{'flagged -> silent after forget' if flipped else 'unexpected'}.")
    print("(re-run to rebuild the graph and repeat; Day 4 = node-level retire)")


if __name__ == "__main__":
    asyncio.run(main())
