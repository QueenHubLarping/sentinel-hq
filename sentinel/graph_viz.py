"""
Render the evidence subgraph behind a flag as a native Mermaid diagram for the PR comment.

GitHub renders ```mermaid fenced blocks inline in PR comments, so Sentinel can SHOW the
typed, multi-hop decision graph it actually traversed — right where the reviewer looks.
This is the visible proof that recall is graph traversal (typed cross-document edges),
not vector similarity.

The diagram is curated (≤ ~10 nodes) around the flagged decision so it reads at a glance:
person/date nodes are pruned, structural plumbing edges (contains/made_from/…) are dropped,
and nodes are colored by source type (ADR / PR / Slack / component) — matching the deck viz.
"""

import re

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STRUCT = {"contains", "made_from", "is_part_of", "is_a"}

# Source-type styling — mirrors sentinel-demo-graphs/render_curated.py and the deck legend.
_CLASSDEF = {
    "decision": "fill:#7c3aed,stroke:#4c1d95,color:#ffffff",
    "incoming": "fill:#dc2626,stroke:#7f1d1d,color:#ffffff",
    "pr":       "fill:#2563eb,stroke:#1e3a8a,color:#ffffff",
    "slack":    "fill:#16a34a,stroke:#14532d,color:#ffffff",
    "tech":     "fill:#0891b2,stroke:#155e75,color:#ffffff",
    "person":   "fill:#f59e0b,stroke:#78350f,color:#ffffff",
}
_EMOJI = {"decision": "🛡️", "incoming": "🔻", "pr": "🔀", "slack": "💬", "tech": "⚙️", "person": "👤"}


def _persons(nbid: dict, edges: list[dict]) -> set:
    persons = set()
    name = lambda i: nbid.get(i, {}).get("name", "").strip().lower()
    for e in edges:
        if e["rel"] in {"authored_by", "authors"}:
            persons.add(name(e["dst"]))
        if e["rel"] in {"authored", "created", "agrees_with", "agreed_with",
                        "advocated_for", "recommended", "supported", "works_on"}:
            persons.add(name(e["src"]))
    persons.discard("")
    return persons


def _classify(name: str, persons: set) -> str:
    n = name.strip().lower()
    if n in persons:
        return "person"
    if _DATE_RE.match(n):
        return "date"
    if n.startswith("adr-") and len(n) <= 8:
        return "decision"
    if "slack" in n:
        return "slack"
    if n.startswith("pr") or "pr #" in n or "pr-" in n:
        return "pr"
    return "tech"


def _pretty(name: str) -> str:
    """Human-friendly node label: title-case words, fix PR/ADR casing, keep it short."""
    s = name.strip().replace('"', "'").replace("\n", " ")
    words = []
    for w in s.split():
        lw = w.lower()
        if lw in ("pr", "adr") or re.match(r"^(pr|adr)-?\d", lw):
            words.append(w.upper())
        else:
            words.append(w[:1].upper() + w[1:])
    return " ".join(words)[:34]


def _root_label(decision_reference: str, fallback: str) -> str:
    """Two-line label for the reversed decision: id + short title from the reference."""
    m = re.search(r"ADR[- ](\d+)", decision_reference, re.IGNORECASE)
    adr = f"ADR-{int(m.group(1)):03d}" if m else _pretty(fallback)
    title = ""
    paren = re.search(r"\(([^)]+)\)", decision_reference)
    if paren:
        title = paren.group(1).strip()
    elif m:
        title = decision_reference[m.end():].strip(" -—:()")
    title = title.replace('"', "'")
    if len(title) > 36:
        title = title[:35].rstrip() + "…"
    return f"{adr}<br/>{title}" if title else adr


def build_mermaid(nbid: dict, edges: list[dict], decision_reference: str,
                  incoming_label: str = "This PR", max_nodes: int = 9) -> str:
    """Pure: build the Mermaid block for the subgraph around the flagged decision.

    nbid:  {node_id: {"name": str, "type": str}}; edges: [{"src","dst","rel"}].
    Returns "" if the decision node isn't in the graph (caller omits the section).
    """
    persons = _persons(nbid, edges)

    # Resolve the decision node by normalized name (e.g. 'adr-001').
    m = re.search(r"ADR[- ](\d+)", decision_reference, re.IGNORECASE)
    focus = f"adr-{int(m.group(1)):03d}" if m else decision_reference.strip().lower()
    root = next((i for i, d in nbid.items() if d["name"].strip().lower() == focus), None)
    if root is None:
        return ""

    # Adjacency over semantic edges only; person/date nodes are leaves (don't expand).
    adj: dict[str, list[str]] = {}
    for e in edges:
        if e["rel"] in _STRUCT:
            continue
        adj.setdefault(e["src"], []).append(e["dst"])
        adj.setdefault(e["dst"], []).append(e["src"])

    def is_leaf(i: str) -> bool:
        return _classify(nbid[i]["name"], persons) in ("person", "date")

    # BFS, capped, dropping date nodes entirely (noise in a diagram).
    keep: list[str] = [root]
    seen = {root}
    frontier = [root]
    while frontier and len(keep) < max_nodes:
        nxt = []
        for u in frontier:
            if u != root and is_leaf(u):
                continue
            for v in adj.get(u, []):
                if v in seen or v not in nbid:
                    continue
                if _classify(nbid[v]["name"], persons) == "date":
                    continue
                seen.add(v)
                keep.append(v)
                nxt.append(v)
                if len(keep) >= max_nodes:
                    break
            if len(keep) >= max_nodes:
                break
        frontier = nxt
    keep_set = set(keep)

    # Stable short ids for Mermaid.
    mid = {nid: f"n{idx}" for idx, nid in enumerate(keep)}
    roles = {nid: ("decision" if nid == root else _classify(nbid[nid]["name"], persons)) for nid in keep}

    def node_def(nid: str) -> str:
        role = roles[nid]
        emoji = _EMOJI.get(role, "")
        if nid == root:
            label = f"{emoji} {_root_label(decision_reference, nbid[nid]['name'])}"
            return f'  {mid[nid]}(["{label}"]):::{role}'        # stadium
        label = f"{emoji} {_pretty(nbid[nid]['name'])}"
        return f'  {mid[nid]}("{label}"):::{role}'              # rounded

    lines = ["```mermaid", "flowchart LR"]
    # Incoming PR (the change under review) — visually distinct, not stored memory.
    inc_label = incoming_label.replace('"', "'")[:34]
    lines.append(f'  INC{{{{"🔻 {inc_label}"}}}}:::incoming')
    lines += [node_def(nid) for nid in keep]
    lines.append(f"  INC -->|\"reverses\"| {mid[root]}")

    # Curated semantic edges: one per unordered pair (drop reciprocals like
    # implements/implements), root-incident first, prefer root as the source for cleaner
    # labels, capped so the diagram stays legible.
    candidates = [e for e in edges
                  if e["rel"] not in _STRUCT and e["src"] in keep_set
                  and e["dst"] in keep_set and e["src"] != e["dst"]]
    candidates.sort(key=lambda e: (root not in (e["src"], e["dst"]), e["src"] != root))
    seen_pair: set = set()
    for e in candidates:
        s, d, rel = e["src"], e["dst"], e["rel"]
        pair = frozenset((s, d))
        if pair in seen_pair:
            continue
        seen_pair.add(pair)
        rel_label = re.sub(r"[^a-z ]", " ", rel.replace("_", " ").lower()).strip()
        lines.append(f'  {mid[s]} -->|"{rel_label}"| {mid[d]}')
        if len(seen_pair) >= 12:
            break

    for role, style in _CLASSDEF.items():
        lines.append(f"  classDef {role} {style}")
    lines.append("```")
    return "\n".join(lines)


async def evidence_mermaid(decision_reference: str, incoming_label: str = "This PR",
                           max_nodes: int = 9) -> str:
    """Fetch the live graph and render the flagged decision's subgraph as Mermaid.

    Best-effort: returns "" on any failure (the comment simply omits the diagram).
    """
    try:
        from cognee.infrastructure.databases.graph import get_graph_engine
        nodes, edges = await (await get_graph_engine()).get_graph_data()
    except Exception:
        return ""
    nbid = {str(i): {"name": str(p.get("name") or ""), "type": str(p.get("type") or "")}
            for i, p in nodes}
    eds = [{"src": str(e[0]), "dst": str(e[1]), "rel": str(e[2])}
           for e in edges if isinstance(e, (list, tuple)) and len(e) >= 3]
    try:
        return build_mermaid(nbid, eds, decision_reference, incoming_label, max_nodes)
    except Exception:
        return ""
