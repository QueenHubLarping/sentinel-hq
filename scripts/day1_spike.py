"""
Day 1 spike — gates:
  [1] Data lands in Cognee Cloud (ingest corpus, verify recall returns it)
  [2] forget() visibly removes data from recall (before/after behavior change)

Run: python scripts/day1_spike.py
"""

import asyncio
import cognee
from dotenv import load_dotenv

load_dotenv()


async def gate_1_ingest_and_verify() -> bool:
    print("=" * 60)
    print("GATE 1: Ingest corpus → verify recall")
    print("=" * 60)

    from sentinel.ingest import ingest_corpus
    await ingest_corpus()

    print("\n→ Query: 'why was async email chosen for checkout?'")
    results = await cognee.recall("why was async email chosen for the checkout flow?")

    print("\n── Results ──")
    if results:
        for r in results:
            print(f"  {r}")
    else:
        print("  (no results — check Cloud connection)")

    print("\n→ Query: 'what engineering decision affects email_service?'")
    results2 = await cognee.recall("what engineering decision affects email_service?")
    for r in results2:
        print(f"  {r}")

    gate_ok = bool(results or results2)
    print(f"\n{'✓ GATE 1 PASSED' if gate_ok else '✗ GATE 1 FAILED — fix Cloud config'}")
    return gate_ok


async def gate_2_forget_removes_node() -> None:
    print("\n" + "=" * 60)
    print("GATE 2: forget() → verify node no longer recalled")
    print("=" * 60)

    print("\n→ Before forget:")
    before = await cognee.recall("async email decision rationale")
    print(f"  {len(before)} result(s)")
    if before:
        print(f"  Sample: {str(before[0])[:200]}")

    from sentinel.ingest import DATASET_NAME
    print(f"\n→ Calling cognee.forget(dataset_name='{DATASET_NAME}') ...")
    await cognee.forget(dataset_name=DATASET_NAME)

    print("\n→ After forget:")
    after = await cognee.recall("async email decision rationale")
    print(f"  {len(after)} result(s)")

    if len(before) > 0 and len(after) == 0:
        print("\n✓ GATE 2 PASSED: forget() removes data from recall.")
        print("  (Day 4: node-level retire — same PR silent after intentional mark)")
    elif len(before) > 0 and len(after) < len(before):
        print("\n~ GATE 2 PARTIAL: fewer results after forget.")
    else:
        print("\n✗ GATE 2 — no change. Investigate forget() API.")


async def inspect_graph() -> None:
    print("\n" + "=" * 60)
    print("GRAPH INSPECTION: what did cognify() actually build?")
    print("=" * 60)

    # ── 1. Schema inventory (node types + relationship distribution) ───────
    # get_schema_inventory() is a public cognee API that calls get_graph_data()
    # internally and summarizes: per-type node counts, sample names, and
    # the full relationship distribution between types. This tells us whether
    # cognify extracted typed edges or just generic entity links.
    print("\n── Node types and relationships ──")
    try:
        inventory = await cognee.get_schema_inventory(dataset="sentinel_decisions")
        if not inventory:
            inventory = await cognee.get_schema_inventory()  # fallback: all datasets

        if inventory:
            for record in inventory:
                node_type = record.get("type", "?")
                count = record.get("count", 0)
                samples = record.get("samples", [])
                print(f"\n  [{node_type}] — {count} node(s)")
                for name in samples:
                    print(f"    • {name}")
                for rel in record.get("relationships", []):
                    print(f"    → {rel['relation']} → {rel['to_type']} (×{rel['count']})")
        else:
            print("  (empty — graph may still be processing)")
    except Exception as e:
        print(f"  get_schema_inventory failed: {e}")

    # ── 2. Raw graph data: all nodes + edges with relationship names ────────
    # get_graph_engine().get_graph_data() returns the raw graph:
    #   nodes: List[(node_id, {type, name, ...})]
    #   edges: List[(source_id, target_id, relationship_name, {props})]
    # This is the ground truth for whether cross-document typed edges exist.
    print("\n── Raw edges (relationship_name between nodes) ──")
    try:
        from cognee.infrastructure.databases.graph import get_graph_engine
        graph_engine = await get_graph_engine()
        nodes, edges = await graph_engine.get_graph_data()

        # Build id→name map for readable output
        id_to_name = {
            node_id: props.get("name", props.get("type", node_id[:8]))
            for node_id, props in nodes
        }

        print(f"  Total nodes: {len(nodes)} | Total edges: {len(edges)}")
        print()

        # Group edges by relationship_name so we can see what labels cognify used
        from collections import defaultdict
        by_relation = defaultdict(list)
        for src, tgt, rel_name, _ in edges:
            by_relation[rel_name].append((id_to_name.get(src, src[:8]), id_to_name.get(tgt, tgt[:8])))

        for rel_name, pairs in sorted(by_relation.items()):
            print(f"  [{rel_name}] ({len(pairs)} edge(s))")
            for src_name, tgt_name in pairs[:3]:  # show up to 3 examples per type
                print(f"    {src_name}  →  {tgt_name}")
            if len(pairs) > 3:
                print(f"    ... and {len(pairs) - 3} more")

        # ── 3. Graph metrics ────────────────────────────────────────────────
        print("\n── Graph metrics ──")
        metrics = await graph_engine.get_graph_metrics()
        for k, v in metrics.items():
            print(f"  {k}: {v}")

    except Exception as e:
        print(f"  Raw graph access failed (expected in Cloud mode): {e}")
        print("  → Use cognee.search(..., query_type=SearchType.INSIGHTS) for Cloud inspection")

        # Cloud fallback: INSIGHTS search surfaces entity relationships
        print("\n── INSIGHTS search (Cloud-compatible edge view) ──")
        try:
            from cognee.api.v1.search import SearchType
            insight_results = await cognee.search(
                "all entities and relationships in the decision corpus",
                query_type=SearchType.INSIGHTS,
            )
            for r in insight_results[:10]:
                print(f"  {r}")
        except Exception as e2:
            print(f"  INSIGHTS search also failed: {e2}")


async def main():
    from sentinel.connection import setup_cognee
    await setup_cognee()

    print("\nSentinel — Day 1 Spike (Cognee Cloud)")
    print()

    gate1_ok = await gate_1_ingest_and_verify()
    if not gate1_ok:
        print("\nFix GATE 1 before proceeding.")
        return

    # Inspect BEFORE forget so we see the populated graph
    await inspect_graph()

    await gate_2_forget_removes_node()

    print("\n→ Generating graph visualization...")
    try:
        await cognee.visualize_graph()
        print("  Screenshot the viz for the demo deck.")
    except Exception as e:
        print(f"  visualize_graph: {e}")

    print("\nDay 1 done. Next: Day 2 — multi-hop recall (SPINE-1).")


if __name__ == "__main__":
    asyncio.run(main())