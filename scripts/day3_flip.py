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
import json
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
_REPO_ROOT = Path(__file__).resolve().parent.parent
_VIS_CDN = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


async def save_graph_html(title: str, filename: str) -> None:
    """Render the current knowledge graph as an interactive HTML page using vis.js.

    The output is a self-contained HTML file (vis.js loaded from CDN).  Open it
    in any browser to zoom, pan, and hover over nodes.
    """
    from cognee.infrastructure.databases.graph import get_graph_engine

    engine = await get_graph_engine()
    nodes, edges = await engine.get_graph_data()

    # Build vis.js node/edge arrays.
    vis_nodes = []
    for nid, props in nodes:
        label = (props.get("name") or props.get("type") or str(nid)[:8])
        # Truncate long labels for readability; full props appear on hover.
        short_label = label[:35] + ("…" if len(label) > 35 else "")
        vis_nodes.append({
            "id": nid,
            "label": short_label,
            "title": json.dumps(props, default=str),  # tooltip on hover
        })

    vis_edges = []
    seen: set = set()
    for src, tgt, rel, _ in edges:
        key = (src, tgt, rel)
        if key in seen:
            continue
        seen.add(key)
        vis_edges.append({"from": src, "to": tgt, "label": str(rel), "arrows": "to"})

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)
    node_count = len(vis_nodes)
    edge_count = len(vis_edges)

    # Colour scheme: blue nodes when graph is populated, grey when empty.
    node_color = "#2A6EBB" if node_count else "#aaaaaa"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{title}</title>
  <script src="{_VIS_CDN}"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f4f6f9; }}
    header {{
      background: #1a3a5c;
      color: #fff;
      padding: 12px 20px;
      display: flex;
      align-items: baseline;
      gap: 16px;
    }}
    header h2 {{ font-size: 1.05rem; font-weight: 600; }}
    header .meta {{ font-size: 0.85rem; opacity: 0.75; }}
    #graph {{
      width: 100%;
      height: calc(100vh - 46px);
      background: #ffffff;
    }}
    .empty-msg {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      font-size: 1.4rem;
      color: #999;
    }}
  </style>
</head>
<body>
  <header>
    <h2>{title}</h2>
    <span class="meta">{node_count} nodes &nbsp;·&nbsp; {edge_count} edges</span>
  </header>
  <div id="graph">
    {"" if node_count else '<div class="empty-msg">Graph is empty — ADR-001 nodes were retired.</div>'}
  </div>
  <script>
    const rawNodes = {nodes_json};
    const rawEdges = {edges_json};

    if (rawNodes.length > 0) {{
      const nodes = new vis.DataSet(rawNodes);
      const edges = new vis.DataSet(rawEdges);
      const container = document.getElementById("graph");
      const options = {{
        nodes: {{
          shape: "dot",
          size: 18,
          color: {{
            background: "{node_color}",
            border: "#1a3a5c",
            highlight: {{ background: "#f0a500", border: "#c07800" }},
          }},
          font: {{ color: "#fff", size: 12, face: "system-ui" }},
          borderWidth: 2,
        }},
        edges: {{
          arrows: "to",
          font: {{ size: 10, align: "middle", background: "#f4f6f9" }},
          color: {{ color: "#888", highlight: "#f0a500" }},
          smooth: {{ type: "dynamic" }},
          width: 1.5,
        }},
        physics: {{
          solver: "forceAtlas2Based",
          forceAtlas2Based: {{ springLength: 120, gravitationalConstant: -60 }},
          stabilization: {{ iterations: 150, updateInterval: 25 }},
        }},
        interaction: {{ hover: true, tooltipDelay: 150 }},
      }};
      new vis.Network(container, {{ nodes, edges }}, options);
    }}
  </script>
</body>
</html>"""

    out = _REPO_ROOT / filename
    out.write_text(html, encoding="utf-8")
    print(f"   viz saved → {out}  (open in browser)")


async def main() -> None:
    pr_text = PR_PATH.read_text(encoding="utf-8")
    await setup_cognee()

    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time, slow)...")
        await ingest_corpus()
    print(f"-> graph ready ({await _node_count()} nodes)\n")

    print("Saving BEFORE graph visualization...")
    await save_graph_html("BEFORE: Full Decision Graph", "graph_before.html")

    print("=" * 64)
    print("BEFORE — detect the incoming PR")
    print("=" * 64)
    v1 = await detect_reversal(pr_text)
    print(f"reverses_decision = {v1.reverses_decision} ({v1.decision_reference})\n")
    print(render_comment(v1))

    print("\n" + "=" * 64)
    print("ACT — maintainer replies '/sentinel intentional'")
    print("=" * 64)
    retire_result = await mark_intentional(v1.decision_reference)
    print("retiring the superseded decision (forget) ->", retire_result)
    print(f"graph nodes now: {await _node_count()}")

    print("\nSaving AFTER graph visualization...")
    await save_graph_html("AFTER: ADR-001 Decision Retired", "graph_after.html")

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
    if flipped:
        print("\nOpen graph_before.html and graph_after.html to see the structural change.")
    print("(re-run to rebuild the graph and repeat)")


if __name__ == "__main__":
    asyncio.run(main())
