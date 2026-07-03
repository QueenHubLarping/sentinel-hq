"""
Offline preview of the Visual Memory Recap — no Cognee, no LLM, no network.

Renders `recap_demo.html` for the primary demo catch (incoming PR #57 reversing the
async-email decision, PR #42 ← issue #91) with the BEFORE/AFTER-forget graph toggle,
using the incoming-PR text from `.sentinel/api_snapshot.json`.

Honesty rule (PRODUCT_SPEC §11): this is a *preview of the rendering*, watermarked
"offline preview" on the page — the verdict text below is the known-good baseline, and
the subgraph mirrors the snapshot corpus rather than a live Cognee fetch. The live path
(Action → recap_from_live_graph) generates everything from the real graph + a real
verdict; this script exists so the artifact can be inspected and styled in seconds.

Run:  python scripts/recap_demo.py   →  recap_demo.html (open in a browser)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.detect import Verdict  # noqa: E402
from sentinel.recap import render_recap_html  # noqa: E402
from sentinel.sources import incoming_text  # noqa: E402

# Known-good baseline verdict for the primary catch (day2/day3 output shape).
VERDICT = Verdict(
    analysis=(
        "The PR removes the async Celery dispatch (send_order_confirmation_task.delay) and "
        "adds a synchronous SMTP call inside the checkout request path. The memory context "
        "records that email dispatch was made asynchronous (PR #42) after a Black Friday "
        "incident (issue #91) showed the inline SMTP call added ~800ms to checkout latency. "
        "The PR's effect directly undoes that decision."
    ),
    reverses_decision=True,
    decision_reference="PR #42 (async email)",
    original_reasoning=(
        "Email delivery is async because the synchronous SMTP send added ~800ms to checkout "
        "latency during the Black Friday peak-traffic incident — and that cost conversions."
    ),
    impact_if_merged="Reintroduces the ~800ms blocking SMTP call on the checkout critical path.",
    assumption="the SMTP provider call costs ~800ms on the checkout critical path",
    affected_capability="Messaging",
    evidence_chain="PR #42 (made it async) -> Issue #91 (the latency incident)",
    confidence=0.92,
    provenance_tier="approved",
)

# The curated evidence neighborhood, mirroring the snapshot corpus (what the live
# recap_from_live_graph curates out of the real graph).
NODES = [
    {"id": "inc", "label": "PR #57 — Sync Email", "role": "incoming"},
    {"id": "dec", "label": "Decision: Async Email (PR #42)", "role": "decision"},
    {"id": "pr42", "label": "PR #42 — Celery Queue", "role": "pr"},
    {"id": "i91", "label": "Issue #91 — Black Friday", "role": "issue"},
    {"id": "chk", "label": "Checkout Views", "role": "tech"},
    {"id": "eml", "label": "Email Service", "role": "tech"},
]
EDGES = [
    {"src": "inc", "dst": "dec", "rel": "reverses"},
    {"src": "dec", "dst": "i91", "rel": "justified by"},
    {"src": "dec", "dst": "pr42", "rel": "established by"},
    {"src": "pr42", "dst": "eml", "rel": "changed"},
    {"src": "i91", "dst": "chk", "rel": "incident in"},
    {"src": "inc", "dst": "chk", "rel": "touches"},
]

# After forget: the decision node is retired — future recall no longer flags PR #57.
NODES_AFTER = [dict(n, role="retired") if n["id"] == "dec" else n for n in NODES]
EDGES_AFTER = [e for e in EDGES if e != EDGES[0]] + [
    {"src": "inc", "dst": "dec", "rel": "supersedes (intentional)"},
]


def main() -> int:
    pr_text = incoming_text("sync_email") or "# PR #57: Simplify checkout — send email synchronously"
    html = render_recap_html(
        VERDICT,
        pr_text,
        [("Before forget", NODES, EDGES), ("After /sentinel intentional", NODES_AFTER, EDGES_AFTER)],
        repo="sentinel-test-repo",
        preview_note="offline preview — snapshot data",
    )
    out = Path(__file__).resolve().parent.parent / "recap_demo.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
