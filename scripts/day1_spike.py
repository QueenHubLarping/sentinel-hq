"""
Day 1 spike — local self-hosted Cognee + Ollama (no Cloud, no API key).

Gates (the load-bearing mechanics the whole project depends on):
  [1] remember + recall: ingest the corpus, confirm a graph-derived answer comes
      back (SPINE-1 — the multi-hop "why").
  [2] forget flips recall: delete the dataset, confirm the retrieved graph
      context drops to zero (SPINE-2 — deletion changes the next answer).

Run from the repo root:
    python scripts/day1_spike.py
"""

import asyncio
import sys
from pathlib import Path

# Make `import sentinel...` work when run as `python scripts/day1_spike.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402  (loads .env before cognee)
import cognee  # noqa: E402
from sentinel.ingest import DATASET_NAME, ingest_corpus  # noqa: E402

GC = cognee.SearchType.GRAPH_COMPLETION


async def _answer(query: str) -> str:
    res = await cognee.search(query, query_type=GC)
    return " ".join(str(r) for r in res) if res else ""


async def _context(query: str) -> list:
    """Raw retrieved graph/vector context (no LLM answer) — the honest before/after measure."""
    return await cognee.search(query, query_type=GC, only_context=True)


async def gate_1_ingest_and_recall() -> bool:
    print("=" * 64)
    print("GATE 1: remember + recall (SPINE-1: the multi-hop 'why')")
    print("=" * 64)

    await ingest_corpus()

    q = "Why was asynchronous email chosen for the checkout flow?"
    print(f"\n-> recall: {q!r}")
    answer = await _answer(q)
    print(f"   answer: {answer or '(empty)'}")

    ctx = await _context(q)
    print(f"   retrieved context items: {len(ctx)}")

    ok = bool(answer) and len(ctx) > 0
    print(f"\n{'PASS' if ok else 'FAIL'}: GATE 1")
    return ok


async def inspect_graph() -> None:
    print("\n" + "=" * 64)
    print("GRAPH INSPECTION: what did cognify() actually build?")
    print("=" * 64)
    try:
        from collections import defaultdict

        from cognee.infrastructure.databases.graph import get_graph_engine

        engine = await get_graph_engine()
        nodes, edges = await engine.get_graph_data()
        id_to_name = {nid: (p.get("name") or p.get("type") or nid[:8]) for nid, p in nodes}
        print(f"  nodes: {len(nodes)} | edges: {len(edges)}")

        by_rel = defaultdict(list)
        for src, tgt, rel, _ in edges:
            by_rel[rel].append((id_to_name.get(src, src[:8]), id_to_name.get(tgt, tgt[:8])))
        print("\n  edges by relationship:")
        for rel, pairs in sorted(by_rel.items()):
            print(f"   [{rel}] x{len(pairs)}")
            for a, b in pairs[:3]:
                print(f"      {a}  ->  {b}")
    except Exception as exc:  # noqa: BLE001
        print(f"  raw graph access failed: {exc}")


async def gate_2_forget_flips_recall() -> bool:
    print("\n" + "=" * 64)
    print("GATE 2: forget flips recall (SPINE-2)")
    print("=" * 64)

    q = "async email decision rationale"
    before = await _context(q)
    print(f"  before forget -> context items: {len(before)}")

    print(f"  cognee.forget(dataset={DATASET_NAME!r}) ...")
    await cognee.forget(dataset=DATASET_NAME)

    after = await _context(q)
    print(f"  after  forget -> context items: {len(after)}")

    ok = len(before) > 0 and len(after) == 0
    status = "PASS" if ok else ("PARTIAL" if len(after) < len(before) else "FAIL")
    print(f"\n{status}: GATE 2 (deletion changes the next recall)")
    print("  (Day 4: node-level retire instead of whole-dataset, for the PR-flip demo)")
    return ok


async def main() -> None:
    await setup_cognee()
    print("\nSentinel — Day 1 Spike (local Cognee + Ollama)\n")

    # Clean slate so the spike is reproducible.
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)

    if not await gate_1_ingest_and_recall():
        print("\nGATE 1 failed — stop and fix before Day 2.")
        return

    await inspect_graph()
    await gate_2_forget_flips_recall()

    print("\n-> graph visualization (screenshot for the deck)")
    try:
        await cognee.visualize_graph()
    except Exception as exc:  # noqa: BLE001
        print(f"   visualize_graph: {exc}")

    print("\nDay 1 done. Next: Day 2 — multi-hop reversal detection on an incoming PR.")


if __name__ == "__main__":
    asyncio.run(main())
