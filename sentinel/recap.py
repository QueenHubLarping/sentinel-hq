"""
The Visual Memory Recap — an interactive, self-contained HTML page per flagged PR.

Where the Memory Review comment is the one-screenshot artifact, the recap is the
one-CLICK artifact: the diff annotated with the org belief it undoes, the belief card,
and the evidence subgraph Sentinel actually traversed — rendered as an interactive SVG
with a "play the traversal" animation that walks the SPINE-1 hop on screen
(incoming PR → governing Decision → incident issue; no shared words, no #ref).

Every visual element is retrieved memory (the Verdict fields + the live Cognee graph)
— nothing here is derivable from the diff alone. That is the point: this is a recap of
the PR's MEMORY IMPACT, not a prettier view of the diff.

Design constraints:
  - fully self-contained (inline CSS/JS, zero CDN) so the artifact opens offline —
    the stage demo never depends on the network (PRODUCT_SPEC §13);
  - deterministic layout (positions computed here, not by a JS force sim) so the same
    verdict renders the same page every run — no demo flakiness;
  - pure core (`render_recap_html`) unit-testable with no Cognee/network, mirroring
    comment.py; the live-graph fetch lives in one thin async wrapper.
"""

import html as _html
import json
import math
import os
import re
from pathlib import Path

from sentinel.detect import Verdict
from sentinel.graph_viz import _STRUCT, _classify, _persons, _pretty, find_root

RECAP_FILENAME = "sentinel_recap.html"

# Node palette — mirrors graph_viz._CLASSDEF / the deck legend, plus the retired state.
_ROLE_COLORS = {
    "decision": "#7c3aed",
    "incoming": "#dc2626",
    "pr":       "#2563eb",
    "issue":    "#16a34a",
    "slack":    "#16a34a",
    "tech":     "#0891b2",
    "person":   "#f59e0b",
    "retired":  "#6e7781",
}
_ROLE_EMOJI = {"decision": "🛡️", "incoming": "🔻", "pr": "🔀", "issue": "🐛",
               "slack": "💬", "tech": "⚙️", "person": "👤", "retired": "🪦"}


def _esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


# ---------------------------------------------------------------------------
# Incoming-PR parsing — title / description / diff, from the PR text we already have
# ---------------------------------------------------------------------------

def parse_pr(pr_text: str) -> dict:
    """Split an incoming-PR text into {title, meta, description, diff} (pure).

    The PR text is the same document detect_reversal consumes: a markdown body with an
    optional fenced ```diff block. `diff` is a list of (kind, line) where kind is one of
    file/hunk/del/add/ctx — enough to color a review-style diff panel.
    """
    title = ""
    for ln in pr_text.splitlines():
        if ln.strip():
            title = ln.strip().lstrip("# ").strip()
            break

    meta = []
    for m in re.finditer(r"^\*\*(Author|Branch)[:\*]*\*?\s*(.+)$", pr_text, re.MULTILINE):
        meta.append(f"{m.group(1)}: {m.group(2).strip()}")

    diff_match = re.search(r"```diff\n(.*?)```", pr_text, re.DOTALL)
    diff_lines: list[tuple[str, str]] = []
    if diff_match:
        for ln in diff_match.group(1).splitlines():
            if ln.startswith("--- ") or ln.startswith("+++ "):
                kind = "file"
            elif ln.startswith("@@"):
                kind = "hunk"
            elif ln.startswith("-"):
                kind = "del"
            elif ln.startswith("+"):
                kind = "add"
            else:
                kind = "ctx"
            diff_lines.append((kind, ln))

    # Description = the prose between the title and the diff block.
    body = pr_text[: diff_match.start()] if diff_match else pr_text
    desc_lines = []
    for ln in body.splitlines()[1:]:
        s = ln.strip()
        if s.startswith("**Author") or s.startswith("**Branch") or s in ("## Diff", "```diff"):
            continue
        if s.startswith("## "):
            continue
        desc_lines.append(ln)
    description = "\n".join(desc_lines).strip()

    return {"title": title, "meta": meta, "description": description, "diff": diff_lines}


# ---------------------------------------------------------------------------
# Subgraph curation — the same evidence neighborhood the Mermaid diagram shows
# ---------------------------------------------------------------------------

def _role(name: str, persons: set) -> str:
    n = name.strip().lower()
    if n.startswith("issue") or "issue #" in n:
        return "issue"
    return _classify(name, persons)


def curate_subgraph(nbid: dict, edges: list[dict], decision_reference: str,
                    max_nodes: int = 9) -> tuple[list[dict], list[dict]]:
    """Pure: the ≤max_nodes neighborhood around the flagged decision, ready to render.

    nbid: {node_id: {"name", "type"}}; edges: [{"src","dst","rel"}].
    Returns ([{id, label, role}], [{src, dst, rel}]) — ([], []) if the root is missing.
    Curation matches graph_viz.build_mermaid: structural edges dropped, person/date
    leaves not expanded, one edge per pair, root-adjacent edges first.
    """
    root = find_root(nbid, decision_reference)
    if root is None:
        return [], []
    persons = _persons(nbid, edges)

    adj: dict[str, list[str]] = {}
    for e in edges:
        if e["rel"] in _STRUCT:
            continue
        adj.setdefault(e["src"], []).append(e["dst"])
        adj.setdefault(e["dst"], []).append(e["src"])

    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    keep, seen, frontier = [root], {root}, [root]
    while frontier and len(keep) < max_nodes:
        nxt = []
        for u in frontier:
            if u != root and _role(nbid[u]["name"], persons) == "person":
                continue
            for v in adj.get(u, []):
                if v in seen or v not in nbid or date_re.match(nbid[v]["name"].strip()):
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

    nodes = [{"id": nid,
              "label": _pretty(nbid[nid]["name"]),
              "role": "decision" if nid == root else _role(nbid[nid]["name"], persons)}
             for nid in keep]

    candidates = [e for e in edges
                  if e["rel"] not in _STRUCT and e["src"] in keep_set
                  and e["dst"] in keep_set and e["src"] != e["dst"]]
    candidates.sort(key=lambda e: (root not in (e["src"], e["dst"]), e["src"] != root))
    out_edges, seen_pair = [], set()
    for e in candidates:
        pair = frozenset((e["src"], e["dst"]))
        if pair in seen_pair:
            continue
        seen_pair.add(pair)
        rel = re.sub(r"[^a-z ]", " ", e["rel"].replace("_", " ").lower()).strip()
        out_edges.append({"src": e["src"], "dst": e["dst"], "rel": rel})
        if len(out_edges) >= 12:
            break
    return nodes, out_edges


def chain_subgraph(verdict: Verdict, incoming_label: str = "This PR") -> tuple[list[dict], list[dict]]:
    """Pure fallback: build the evidence subgraph from the Verdict's own fields.

    cognify does not reliably mint a resolvable node for every decision, so when the
    graph-name lookup fails we render the chain recall actually reconstructed —
    `evidence_chain` ("PR #16 (made it async) -> Issue #8 (the incident)") plus the
    affected capability. Still 100% retrieved memory; just sourced from the verdict
    instead of a node-name match.
    """
    if not verdict.reverses_decision:
        return [], []
    hops = [h.strip() for h in re.split(r"->|→", verdict.evidence_chain or "") if h.strip()]
    if not hops:
        if not verdict.decision_reference:
            return [], []
        hops = [verdict.decision_reference]

    nodes = [{"id": "inc", "label": incoming_label[:34], "role": "incoming"}]
    edges: list[dict] = []
    prev = "inc"
    for k, hop in enumerate(hops):
        nid = f"hop{k}"
        low = hop.lower()
        role = "decision" if k == 0 else ("issue" if "issue" in low else "pr")
        nodes.append({"id": nid, "label": _pretty(hop), "role": role})
        edges.append({"src": prev, "dst": nid,
                      "rel": "reverses" if k == 0 else "justified by"})
        prev = nid
    cap = (verdict.affected_capability or "").strip()
    if cap:
        nodes.append({"id": "cap", "label": _pretty(cap), "role": "tech"})
        edges.append({"src": "hop0", "dst": "cap", "rel": "governs"})
    return nodes, edges


def traversal_path(nodes: list[dict], edges: list[dict]) -> list[str]:
    """The SPINE-1 story as an ordered node-id path: incoming → decision → incident issue.

    Pure; used to drive the 'play the traversal' animation. Falls back gracefully:
    whatever prefix of the chain exists is returned (possibly just [decision]).
    """
    by_role: dict[str, list[str]] = {}
    for n in nodes:
        by_role.setdefault(n["role"], []).append(n["id"])
    path = []
    if by_role.get("incoming"):
        path.append(by_role["incoming"][0])
    root = (by_role.get("decision") or [None])[0]
    if root:
        path.append(root)
        adj = {root: []}
        for e in edges:
            if e["src"] == root:
                adj[root].append(e["dst"])
            elif e["dst"] == root:
                adj[root].append(e["src"])
        issues = set(by_role.get("issue", []))
        hop = next((v for v in adj[root] if v in issues), None)
        if hop is None and issues:
            hop = sorted(issues)[0]
        if hop:
            path.append(hop)
    return path


# ---------------------------------------------------------------------------
# Layout — deterministic radial placement (no JS force sim; same page every run)
# ---------------------------------------------------------------------------

_W, _H = 920, 540


def _layout(nodes: list[dict]) -> dict[str, tuple[float, float]]:
    """Root at center-right, incoming PR pinned left, the rest on a ring around the root."""
    pos: dict[str, tuple[float, float]] = {}
    # A retired decision keeps its center pin so the before/after toggle doesn't jump.
    root = next((n["id"] for n in nodes if n["role"] in ("decision", "retired")), None)
    incoming = next((n["id"] for n in nodes if n["role"] == "incoming"), None)
    cx, cy = _W * 0.56, _H * 0.5
    if root:
        pos[root] = (cx, cy)
    if incoming:
        pos[incoming] = (_W * 0.13, cy)
    ring = [n["id"] for n in nodes if n["id"] not in (root, incoming)]
    r = 195.0
    # Spread the ring across the right-facing arc so nothing collides with the pinned
    # incoming node on the left; even angular spacing keeps small graphs legible.
    span_start, span_end = -125.0, 125.0
    for k, nid in enumerate(ring):
        t = 0.5 if len(ring) == 1 else k / (len(ring) - 1)
        a = math.radians(span_start + t * (span_end - span_start))
        pos[nid] = (cx + r * math.cos(a), cy + r * math.sin(a))
    return pos


# ---------------------------------------------------------------------------
# HTML rendering — the pure climax function
# ---------------------------------------------------------------------------

_CSS = """
:root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --fg:#e6edf3; --muted:#8b949e;
        --purple:#a78bfa; --purple-deep:#7c3aed; --red:#f85149; --green:#3fb950;
        --amber:#d29922; --blue:#58a6ff; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--fg);
       font:15px/1.55 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif; padding:28px 20px 60px; }
.wrap { max-width:1180px; margin:0 auto; }
.topbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
.topbar h1 { font-size:21px; font-weight:700; }
.chip { display:inline-block; padding:3px 11px; border-radius:999px; font-size:12px;
        font-weight:600; border:1px solid var(--border); background:var(--panel); }
.chip.purple { background:#3b2a63; border-color:var(--purple-deep); color:var(--purple); }
.chip.red    { background:#4d1a1f; border-color:#8e2c33; color:#ff9b9b; }
.chip.gray   { color:var(--muted); }
.hero { background:linear-gradient(135deg,#221a3a,#161b22 60%); border:1px solid var(--purple-deep);
        border-radius:12px; padding:20px 24px; margin-bottom:20px; }
.hero .big { font-size:18px; font-weight:650; margin-bottom:8px; }
.hero .big b { color:var(--purple); }
.meter { display:flex; align-items:center; gap:10px; margin-top:10px; font-size:13px; color:var(--muted); }
.meter .track { flex:0 0 220px; height:8px; border-radius:6px; background:#21262d; overflow:hidden; }
.meter .fill { height:100%; background:linear-gradient(90deg,var(--purple-deep),var(--purple)); }
.grid { display:grid; grid-template-columns:1.25fr 1fr; gap:18px; margin-bottom:20px; }
@media (max-width:900px){ .grid { grid-template-columns:1fr; } }
.panel { background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
.panel > h2 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted);
              padding:12px 16px; border-bottom:1px solid var(--border); }
.panel .pad { padding:14px 16px; }
.diff { font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; overflow-x:auto; }
.diff .ln { display:block; white-space:pre; padding:0 14px; }
.diff .file { background:#1c2128; color:var(--blue); font-weight:600; padding-top:4px; padding-bottom:4px; }
.diff .hunk { color:var(--purple); background:#1a1f27; }
.diff .del  { background:rgba(248,81,73,.14); color:#ffa198; }
.diff .add  { background:rgba(63,185,80,.13); color:#7ee787; }
.diff .ctx  { color:var(--muted); }
.annot { margin:8px 12px; padding:10px 14px; border-left:3px solid var(--red);
         background:rgba(248,81,73,.08); border-radius:0 8px 8px 0; font-size:13px; }
.annot b { color:#ff9b9b; }
.belief-quote { border-left:3px solid var(--purple-deep); padding:8px 14px; margin:6px 0 12px;
                background:rgba(124,58,237,.08); border-radius:0 8px 8px 0; font-style:italic; }
.kv { font-size:13.5px; margin:9px 0; }
.kv .k { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; display:block; }
.chain { font:12.5px ui-monospace,Menlo,monospace; color:var(--blue); }
.note { color:var(--muted); font-size:12px; font-style:italic; }
.graph-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
              padding:12px 16px; border-bottom:1px solid var(--border); }
.graph-head h2 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); flex:1; }
button { background:var(--purple-deep); color:#fff; border:0; border-radius:8px; padding:7px 14px;
         font-size:13px; font-weight:600; cursor:pointer; }
button:hover { background:#8b5cf6; }
button.ghost { background:transparent; border:1px solid var(--border); color:var(--muted); }
button.ghost.active { border-color:var(--purple-deep); color:var(--purple); }
svg text { font:12px -apple-system,"Segoe UI",sans-serif; fill:var(--fg); }
.edge { stroke:#3d444d; stroke-width:1.6; fill:none; marker-end:url(#arr); transition:all .25s; }
.edge-label { fill:var(--muted); font-size:10.5px; }
.node circle { stroke-width:2; transition:all .25s; cursor:default; }
.node text { font-weight:600; }
.node .sub { font-weight:400; fill:var(--muted); font-size:10px; }
.lit circle { filter:drop-shadow(0 0 10px var(--purple)); stroke:#fff !important; }
.lit-edge { stroke:var(--purple) !important; stroke-width:3 !important; }
.dim { opacity:.25; }
.retired circle { stroke-dasharray:4 3; }
.retired text { text-decoration:line-through; fill:var(--muted); }
.legend { display:flex; gap:14px; flex-wrap:wrap; padding:10px 16px; border-top:1px solid var(--border);
          font-size:12px; color:var(--muted); }
.legend i { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }
.caption { min-height:22px; padding:6px 16px 12px; font-size:13px; color:var(--purple); }
details { margin:18px 0; background:var(--panel); border:1px solid var(--border); border-radius:12px; }
details summary { padding:12px 16px; cursor:pointer; font-weight:600; font-size:14px; }
details .pad { border-top:1px solid var(--border); color:var(--muted); }
footer { margin-top:26px; text-align:center; color:var(--muted); font-size:12.5px; }
footer b { color:var(--purple); }
"""

_JS = """
function playTraversal(stateIdx){
  const data = RECAP.states[stateIdx];
  const steps = data.path;
  document.querySelectorAll('.lit').forEach(e=>e.classList.remove('lit'));
  document.querySelectorAll('.lit-edge').forEach(e=>e.classList.remove('lit-edge'));
  const cap = document.getElementById('cap-'+stateIdx);
  let i = 0;
  function step(){
    if(i >= steps.length){ cap.textContent = RECAP.doneCaption; return; }
    const nid = steps[i];
    const el = document.getElementById('st'+stateIdx+'-'+nid);
    if(el){ el.classList.add('lit'); }
    if(i > 0){
      const eid = document.getElementById('st'+stateIdx+'-e-'+steps[i-1]+'-'+nid) ||
                  document.getElementById('st'+stateIdx+'-e-'+nid+'-'+steps[i-1]);
      if(eid){ eid.classList.add('lit-edge'); }
    }
    cap.textContent = data.captions[i] || '';
    i++; setTimeout(step, 950);
  }
  step();
}
function showState(idx){
  document.querySelectorAll('.gstate').forEach((g,k)=>{ g.style.display = (k===idx)?'':'none'; });
  document.querySelectorAll('.stbtn').forEach((b,k)=>{ b.classList.toggle('active', k===idx); });
}
document.querySelectorAll('.node').forEach(n=>{
  n.addEventListener('mouseenter', ()=>{
    const sid = n.dataset.state, nid = n.dataset.nid;
    document.querySelectorAll('.gstate[data-state="'+sid+'"] .edge').forEach(e=>{
      if(e.dataset.src!==nid && e.dataset.dst!==nid){ e.classList.add('dim'); }
    });
  });
  n.addEventListener('mouseleave', ()=>{
    document.querySelectorAll('.dim').forEach(e=>e.classList.remove('dim'));
  });
});
"""


def _svg_state(idx: int, label: str, nodes: list[dict], edges: list[dict]) -> str:
    """One graph state (e.g. 'Before forget') as a static SVG group — positions are
    computed here so the artifact is deterministic and needs no layout JS."""
    pos = _layout(nodes)
    parts = [f'<g class="gstate" data-state="{idx}" style="{"" if idx == 0 else "display:none"}">']
    for e in edges:
        if e["src"] not in pos or e["dst"] not in pos:
            continue
        (x1, y1), (x2, y2) = pos[e["src"]], pos[e["dst"]]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 14
        eid = f'st{idx}-e-{e["src"]}-{e["dst"]}'
        parts.append(
            f'<path id="{_esc(eid)}" class="edge" data-src="{_esc(e["src"])}" '
            f'data-dst="{_esc(e["dst"])}" d="M{x1:.0f},{y1:.0f} Q{mx:.0f},{my:.0f} {x2:.0f},{y2:.0f}"/>'
            f'<text class="edge-label" x="{mx:.0f}" y="{my - 4:.0f}" text-anchor="middle">{_esc(e["rel"])}</text>'
        )
    for n in nodes:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        role = n["role"]
        color = _ROLE_COLORS.get(role, _ROLE_COLORS["tech"])
        r = 30 if role in ("decision", "incoming") else 22
        label_words = _esc(n["label"])
        cls = "node retired" if role == "retired" else "node"
        parts.append(
            f'<g id="st{idx}-{_esc(n["id"])}" class="{cls}" data-state="{idx}" data-nid="{_esc(n["id"])}">'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{color}" stroke="{color}" fill-opacity="0.22"/>'
            f'<text x="{x:.0f}" y="{y - r - 8:.0f}" text-anchor="middle">{_ROLE_EMOJI.get(role, "")} {label_words}</text>'
            f'<text class="sub" x="{x:.0f}" y="{y + r + 14:.0f}" text-anchor="middle">{_esc(role)}</text>'
            f"</g>"
        )
    parts.append("</g>")
    return "\n".join(parts)


def _diff_panel(parsed: dict, verdict: Verdict) -> str:
    """The annotated diff: review-style coloring plus ONE memory annotation pinned to the
    first hunk — 'these removed lines undo <decision>' — sourced from the Verdict, never
    invented here (rendering only)."""
    out = ['<div class="diff">']
    annotated = False
    for kind, ln in parsed["diff"]:
        out.append(f'<span class="ln {kind}">{_esc(ln) or " "}</span>')
        if kind == "hunk" and not annotated and verdict.reverses_decision:
            ref = _esc(verdict.decision_reference or "a past decision")
            why_raw = verdict.original_reasoning or ""
            if len(why_raw) > 160:
                why_raw = why_raw[:159].rsplit(" ", 1)[0] + "…"
            why = _esc(why_raw)
            out.append(
                f'<div class="annot">⛔ <b>Memory conflict:</b> the removed lines undo '
                f'<b>{ref}</b>{" — <i>" + why + "</i>" if why else ""}</div>'
            )
            annotated = True
    if not parsed["diff"]:
        out.append('<span class="ln ctx">(no diff found in the PR text)</span>')
    out.append("</div>")
    return "\n".join(out)


def render_recap_html(verdict: Verdict, pr_text: str,
                      states: list[tuple[str, list[dict], list[dict]]],
                      *, repo: str = "", preview_note: str = "") -> str:
    """Pure: the full Visual Memory Recap page as a self-contained HTML string.

    states: [(label, nodes, edges)] graph states to render (one = current memory;
    two = the before/after-forget toggle for the stage demo). May be empty — the page
    still carries the annotated diff + belief card.
    preview_note: shown as a watermark chip for offline previews (honesty rule: a
    synthetic-layout preview must say so).
    """
    parsed = parse_pr(pr_text)
    conf = max(0.0, min(1.0, verdict.confidence))
    pct = f"{conf:.0%}"
    tier = (getattr(verdict, "provenance_tier", "") or "inferred").strip().lower()
    tier_label = "human-approved belief" if tier == "approved" else "machine-inferred belief"
    cap = (verdict.affected_capability or "").strip()

    # Per-state traversal payload for the play button (captions from the edge rels).
    state_payload = []
    for _, nodes, edges in states:
        path = traversal_path(nodes, edges)
        names = {n["id"]: n["label"] for n in nodes}
        captions = []
        for i, nid in enumerate(path):
            if i == 0:
                captions.append(f"1 · The incoming change: {names.get(nid, 'this PR')}")
            elif i == 1:
                captions.append(f"2 · Semantic recall matches the governing decision: {names.get(nid, '')}")
            else:
                captions.append(f"3 · A typed graph edge reaches the rationale: {names.get(nid, '')} — no shared words, no #ref")
        state_payload.append({"path": path, "captions": captions})

    graph_html = ""
    if states:
        buttons = "".join(
            f'<button class="ghost stbtn{" active" if i == 0 else ""}" '
            f'onclick="showState({i})">{_esc(lbl)}</button>'
            for i, (lbl, _, _) in enumerate(states)
        ) if len(states) > 1 else ""
        svgs = "\n".join(_svg_state(i, lbl, nodes, edges) for i, (lbl, nodes, edges) in enumerate(states))
        captions = "\n".join(
            f'<div class="caption" id="cap-{i}"></div>' for i in range(len(states))
        )
        legend = "".join(
            f'<span><i style="background:{c}"></i>{r}</span>'
            for r, c in _ROLE_COLORS.items() if r not in ("slack",)
        )
        graph_html = f"""
<div class="panel" style="margin-bottom:20px">
  <div class="graph-head">
    <h2>The evidence graph Sentinel traversed</h2>
    {buttons}
    <button onclick="playTraversal(0)">▶ Play the traversal</button>
  </div>
  <svg viewBox="0 0 {_W} {_H}" width="100%">
    <defs><marker id="arr" viewBox="0 0 10 10" refX="26" refY="5" markerWidth="7"
      markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#3d444d"/></marker></defs>
    {svgs}
  </svg>
  {captions}
  <div class="legend">{legend}</div>
</div>
<p class="note" style="margin:-8px 4px 20px">The reconstruction path — <b>incoming PR → governing
decision → incident issue</b> — shares no keywords and no <code>#ref</code> across the hop:
vector similarity alone and the GitHub API alone both miss it. Typed graph traversal + semantic
recall (Cognee) is what connects them.</p>
"""

    assumption = (getattr(verdict, "assumption", "") or "").strip()
    chain = (getattr(verdict, "evidence_chain", "") or "").strip()
    meta_line = " · ".join(_esc(m) for m in parsed["meta"])
    desc = _esc(parsed["description"][:600])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel · Visual Memory Recap</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>🛡️ Sentinel · Visual Memory Recap</h1>
    {f'<span class="chip purple">{_esc(cap)}</span>' if cap else ''}
    <span class="chip red">supersedes a learning</span>
    <span class="chip">{_esc(tier_label)}</span>
    {f'<span class="chip gray">{_esc(repo)}</span>' if repo else ''}
    {f'<span class="chip gray">{_esc(preview_note)}</span>' if preview_note else ''}
  </div>

  <div class="hero">
    <div class="big">This PR doesn't just change code — it changes <b>what your organization
    believes{f' about {_esc(cap)}' if cap else ''}</b>.</div>
    <div>{_esc(parsed['title'])}</div>
    {f'<div class="note">{meta_line}</div>' if meta_line else ''}
    <div class="meter"><span>Confidence in the current belief</span>
      <span class="track"><span class="fill" style="width:{conf * 100:.0f}%"></span></span>
      <b style="color:var(--fg)">{pct}</b></div>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>What this PR changes — annotated against memory</h2>
      {_diff_panel(parsed, verdict)}
      {f'<div class="pad note">{desc}</div>' if desc else ''}
    </div>
    <div class="panel">
      <h2>What your organization currently believes</h2>
      <div class="pad">
        <div class="belief-quote">{_esc(verdict.original_reasoning or '(original rationale not captured)')}</div>
        {f'<div class="kv"><span class="k">This holds only while</span>{_esc(assumption)}</div>' if assumption else ''}
        <div class="kv"><span class="k">Reconstructed via</span>
          <span class="chain">{_esc(chain or verdict.decision_reference)}</span></div>
        <div class="kv"><span class="k">Memory impact</span>
          ⚠️ This PR would <b>supersede</b> {_esc(verdict.decision_reference or 'that learning')}.</div>
        <div class="kv"><span class="k">If merged</span>{_esc(verdict.impact_if_merged or '—')}</div>
        <p class="note">no shared keywords, no #ref from this PR — recovered by graph + semantic reasoning</p>
      </div>
    </div>
  </div>

  {graph_html}

  {f'''<details><summary>🔎 How Sentinel reconstructed this</summary>
  <div class="pad">{_esc(verdict.analysis)}</div></details>''' if verdict.analysis else ''}

  <footer>🛡️ <b>Sentinel</b> — every element on this page is <b>retrieved memory</b>
  (Cognee graph + vector recall), not a re-reading of the diff · remember / recall / improve / forget</footer>
</div>
<script>
const RECAP = {{"states": {json.dumps(state_payload)},
  "doneCaption": "The lesson, reconstructed — only graph + semantic memory could make this hop."}};
{_JS}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Live wrapper + file output (the only non-pure code in this module)
# ---------------------------------------------------------------------------

def write_recap(html_text: str, path: Path | None = None) -> Path:
    """Write the recap where the Action's upload-artifact step will find it."""
    if path is None:
        base = os.environ.get("GITHUB_WORKSPACE") or "."
        path = Path(base) / RECAP_FILENAME
    path.write_text(html_text, encoding="utf-8")
    return path


async def recap_from_live_graph(verdict: Verdict, pr_text: str, *, repo: str = "") -> str:
    """Fetch the live Cognee graph, curate the flagged decision's neighborhood, and render
    the recap. Best-effort like evidence_mermaid: any failure returns "" and the Action
    simply skips the artifact (advisory, never blocks)."""
    try:
        from cognee.infrastructure.databases.graph import get_graph_engine

        raw_nodes, raw_edges = await (await get_graph_engine()).get_graph_data()
    except Exception:
        return ""
    nbid = {str(i): {"name": str(p.get("name") or ""), "type": str(p.get("type") or "")}
            for i, p in raw_nodes}
    eds = [{"src": str(e[0]), "dst": str(e[1]), "rel": str(e[2])}
           for e in raw_edges if isinstance(e, (list, tuple)) and len(e) >= 3]
    try:
        first_line = next((ln.strip("# ").strip() for ln in pr_text.splitlines() if ln.strip()),
                          "This PR")
        nodes, edges = curate_subgraph(nbid, eds, verdict.decision_reference)
        if nodes:
            # Pin the incoming PR into the picture — it's the change under review, not
            # stored memory, so it never comes back from the graph fetch.
            root = nodes[0]["id"]
            nodes.insert(0, {"id": "__incoming__", "label": first_line[:34], "role": "incoming"})
            edges.insert(0, {"src": "__incoming__", "dst": root, "rel": "reverses"})
        else:
            # Entity names didn't resolve (cognify roll) — render the chain the verdict
            # itself reconstructed. Same retrieved memory, sturdier source.
            nodes, edges = chain_subgraph(verdict, incoming_label=first_line)
        states = [("Current memory", nodes, edges)] if nodes else []
        return render_recap_html(verdict, pr_text, states, repo=repo)
    except Exception:
        return ""
