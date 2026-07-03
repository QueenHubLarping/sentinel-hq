"""Pure-function tests — no Cognee, no network, no LLM calls.

Run with:  pip install pytest && pytest tests/
"""

import types

import pytest

from sentinel.comment import render_comment, render_feedback_recorded
from sentinel.detect import Verdict, _normalize_confidence, _recall_query
from sentinel.improve import (
    DEFAULT_FEEDBACK_ALPHA,
    THUMBS_DOWN,
    THUMBS_UP,
    _element_ids,
    dismissed_file,
    feedback_signature,
    file_dismissed_signatures,
    record_noise_file,
)
from sentinel.ingest import corpus_file_data_id
from sentinel.resolve import _adr_number


# ---------------------------------------------------------------------------
# render_comment
# ---------------------------------------------------------------------------

def test_render_comment_no_reversal():
    v = Verdict(
        analysis="No contradiction found in the graph context.",
        reverses_decision=False,
    )
    comment = render_comment(v)
    # The calm "nothing contradicted" Memory Review note.
    assert "Memory Review" in comment
    assert "no active learning" in comment.lower()
    assert "[!CAUTION]" not in comment


def test_render_comment_approved_reversal_is_confident_card():
    v = Verdict(
        analysis="Removes async Celery dispatch, adds inline SMTP.",
        reverses_decision=True,
        decision_reference="PR #42 (async email)",
        original_reasoning="800ms SMTP block was the single biggest latency driver.",
        impact_if_merged="Reintroduces 800ms blocking SMTP call in checkout.",
        confidence=0.9,
        provenance_tier="approved",
    )
    comment = render_comment(v)
    # Approved tier → the loud, confident supersession card.
    assert "[!CAUTION]" in comment
    assert "Memory Review" in comment
    assert "PR #42" in comment
    assert "800ms" in comment
    assert "90%" in comment
    assert "/sentinel intentional" in comment


def test_render_comment_inferred_reversal_is_soft_proposal():
    v = Verdict(
        analysis="Removes async dispatch.",
        reverses_decision=True,
        decision_reference="PR #42 (async email)",
        original_reasoning="latency",
        impact_if_merged="reintroduces latency",
        confidence=0.63,
        provenance_tier="inferred",
    )
    comment = render_comment(v)
    # Inferred tier → soft proposal, never the loud CAUTION styling.
    assert "[!CAUTION]" not in comment
    assert "[!NOTE]" in comment
    assert "Possible" in comment or "possible" in comment
    assert "PR #42" in comment


def test_render_comment_reversal_confidence_formats_as_percent():
    v = Verdict(
        analysis="x",
        reverses_decision=True,
        decision_reference="PR #42",
        original_reasoning="r",
        impact_if_merged="i",
        confidence=0.75,
        provenance_tier="approved",
    )
    assert "75%" in render_comment(v)


# ---------------------------------------------------------------------------
# _normalize_confidence
# ---------------------------------------------------------------------------

def test_normalize_confidence_passthrough():
    assert _normalize_confidence(0.9) == pytest.approx(0.9)
    assert _normalize_confidence(0.0) == 0.0
    assert _normalize_confidence(1.0) == 1.0


def test_normalize_confidence_hundreds_scale():
    # Models that emit 85 instead of 0.85 are divided by 100.
    assert _normalize_confidence(85.0) == pytest.approx(0.85)
    assert _normalize_confidence(100.0) == pytest.approx(1.0)
    assert _normalize_confidence(95.0) == pytest.approx(0.95)


def test_normalize_confidence_clamp_low():
    assert _normalize_confidence(-0.5) == 0.0


def test_normalize_confidence_clamp_high():
    # 200 / 100 = 2.0, clamped to 1.0
    assert _normalize_confidence(200.0) == 1.0


# ---------------------------------------------------------------------------
# corpus_file_data_id  (stable UUID derivation)
# ---------------------------------------------------------------------------

def test_corpus_file_data_id_is_stable():
    uid1 = corpus_file_data_id("ADR-001-async-email.md")
    uid2 = corpus_file_data_id("ADR-001-async-email.md")
    assert uid1 == uid2


def test_corpus_file_data_id_distinct_files():
    uid1 = corpus_file_data_id("ADR-001-async-email.md")
    uid2 = corpus_file_data_id("ADR-002-postgres-not-nosql.md")
    uid3 = corpus_file_data_id("ADR-003-gateway-rate-limiting.md")
    assert uid1 != uid2
    assert uid1 != uid3
    assert uid2 != uid3


# ---------------------------------------------------------------------------
# _adr_number  (decision_reference parsing in resolve.py)
# ---------------------------------------------------------------------------

def test_adr_number_hyphen_standard():
    assert _adr_number("ADR-001 (async email dispatch via Redis/Celery queue)") == "ADR-001"


def test_adr_number_hyphen_no_parens():
    assert _adr_number("ADR-042") == "ADR-042"


def test_adr_number_zero_pads_single_digit():
    assert _adr_number("ADR-3 something") == "ADR-003"


def test_adr_number_space_separator():
    assert _adr_number("ADR 002 rate-limiting") == "ADR-002"


def test_adr_number_lowercase():
    assert _adr_number("adr-001 (something)") == "ADR-001"


def test_adr_number_no_match_returns_none():
    assert _adr_number("some unrelated string") is None
    assert _adr_number("") is None
    assert _adr_number("ADDR-001") is None   # double-D should not match


# ---------------------------------------------------------------------------
# Improve phase — feedback score constants + alpha (map to Cognee's rating space)
# ---------------------------------------------------------------------------

def test_thumbs_scores_are_extremes_of_cognee_range():
    # Cognee normalizes score via (score-1)/4: THUMBS_DOWN -> 0.0, THUMBS_UP -> 1.0.
    assert THUMBS_DOWN == 1
    assert THUMBS_UP == 5
    assert (THUMBS_DOWN - 1) / 4 == 0.0
    assert (THUMBS_UP - 1) / 4 == 1.0


def test_default_feedback_alpha_in_valid_range():
    # Cognee requires the streaming-update alpha in (0, 1].
    assert 0.0 < DEFAULT_FEEDBACK_ALPHA <= 1.0


# ---------------------------------------------------------------------------
# _element_ids  (pulls node_ids / edge_ids off a session Q&A entry, fault-tolerant)
# ---------------------------------------------------------------------------

def _qa(used):
    return types.SimpleNamespace(used_graph_element_ids=used)


def test_element_ids_extracts_lists():
    qa = _qa({"node_ids": ["n1", "n2"], "edge_ids": ["e1"]})
    assert _element_ids(qa, "node_ids") == ["n1", "n2"]
    assert _element_ids(qa, "edge_ids") == ["e1"]


def test_element_ids_missing_key_returns_empty():
    assert _element_ids(_qa({"node_ids": ["n1"]}), "edge_ids") == []


def test_element_ids_handles_none_and_bad_shapes():
    assert _element_ids(_qa(None), "node_ids") == []
    assert _element_ids(_qa({}), "node_ids") == []
    assert _element_ids(_qa({"node_ids": "n1"}), "node_ids") == []  # not a list
    assert _element_ids(types.SimpleNamespace(), "node_ids") == []  # attr absent


def test_element_ids_drops_non_string_entries():
    qa = _qa({"node_ids": ["n1", 7, None, "n2"]})
    assert _element_ids(qa, "node_ids") == ["n1", "n2"]


# ---------------------------------------------------------------------------
# _recall_query  (the shared recall question — Improve replays it verbatim)
# ---------------------------------------------------------------------------

def test_recall_query_embeds_change_text():
    q = _recall_query("make checkout email synchronous")
    assert "make checkout email synchronous" in q
    assert "reasoning" in q.lower()


def test_recall_query_truncates_long_pr_text():
    long_text = "x" * 5000
    q = _recall_query(long_text)
    # PR text is capped at 800 chars in the query body.
    assert q.count("x") == 800


# ---------------------------------------------------------------------------
# improve — feedback_signature (the drift key) + suppression rendering
# ---------------------------------------------------------------------------

def test_feedback_signature_adr_collapses_to_canonical_id():
    assert feedback_signature("ADR-001 (async email)") == "ADR-001"
    assert feedback_signature("adr-3 something") == "ADR-003"


def test_feedback_signature_non_adr_slugifies():
    assert feedback_signature("Inline retry helper") == "inline-retry-helper"
    assert feedback_signature("") == "unknown"


def test_feedback_signature_stable():
    assert feedback_signature("ADR-001 (x)") == feedback_signature("ADR-001 something else")


def test_should_flag_true_when_reversal_not_suppressed():
    v = Verdict(analysis="x", reverses_decision=True, decision_reference="ADR-001")
    assert v.should_flag is True


def test_should_flag_false_when_suppressed_by_feedback():
    v = Verdict(
        analysis="x", reverses_decision=True, decision_reference="ADR-001",
        suppressed_by_feedback=True,
    )
    assert v.should_flag is False


def test_should_flag_false_when_no_reversal():
    v = Verdict(analysis="x", reverses_decision=False)
    assert v.should_flag is False


# ---------------------------------------------------------------------------
# render_comment — suppressed (muted-by-feedback) branch
# ---------------------------------------------------------------------------

def test_render_comment_suppressed_is_quiet_note():
    v = Verdict(
        analysis="reverses async email", reverses_decision=True,
        decision_reference="ADR-001 (async email)", suppressed_by_feedback=True,
    )
    comment = render_comment(v)
    assert "muted" in comment.lower()
    assert "ADR-001" in comment
    # A muted flag must NOT render the loud CAUTION card.
    assert "[!CAUTION]" not in comment


def test_render_feedback_recorded_confirms_drift():
    comment = render_feedback_recorded("ADR-001", 57)
    assert "👎" in comment
    assert "ADR-001" in comment
    assert "#57" in comment


# ---------------------------------------------------------------------------
# improve — durable dismissal file (the CI-safe store)
# ---------------------------------------------------------------------------

def test_dismissal_file_roundtrip_and_idempotent(tmp_path, monkeypatch):
    # dismissed_file() now lives under .sentinel/ (sentinel_dir, driven by SENTINEL_RETIRED_DIR).
    monkeypatch.setenv("SENTINEL_RETIRED_DIR", str(tmp_path))
    assert file_dismissed_signatures() == set()

    record_noise_file("PR #42 (async email)")
    record_noise_file("PR #42 something else")  # same signature — idempotent
    record_noise_file("PR #19 (rate limiting)")

    assert file_dismissed_signatures() == {"PR-42", "PR-19"}
    # One entry per signature despite the repeated dismissal.
    body = dismissed_file().read_text(encoding="utf-8")
    assert body.count("PR-42") == 1


# ---------------------------------------------------------------------------
# SPINE-1 proof — pure marker-matching helper (no Cognee/network)
# ---------------------------------------------------------------------------
import pathlib  # noqa: E402
import sys as _sys  # noqa: E402

_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from spine1_proof import RATIONALE_MARKERS, hit_count, rationale_hits  # noqa: E402


def test_rationale_hits_detects_slack_only_rationale():
    # A retrieval that surfaced the Slack thread reaches the conversational rationale.
    ctx = "We use Flower for monitoring and retry with backoff; a daily reconciliation job resends."
    hits = rationale_hits(ctx)
    assert hits["flower queue monitoring"] is True
    assert hits["retry/backoff guarantee"] is True
    assert hits["reconciliation safety-net"] is True
    assert hit_count(hits) >= 3


def test_rationale_hits_absent_in_pr_diff_text():
    # The PR diff (Celery/Redis/SMTP) carries none of the Slack-only rationale → control ~0.
    pr_like = "Send the confirmation email directly via SendGrid SMTP, no Celery/Redis queue."
    assert hit_count(rationale_hits(pr_like)) == 0


def test_rationale_hits_empty_and_case_insensitive():
    assert hit_count(rationale_hits("")) == 0
    assert rationale_hits("FLOWER dashboard")["flower queue monitoring"] is True
    assert set(rationale_hits("x").keys()) == set(RATIONALE_MARKERS.keys())


# ---------------------------------------------------------------------------
# sources — rendering a real merged PR into an ingestible doc (pure, no network)
# ---------------------------------------------------------------------------
from sentinel.sources import pr_to_doc  # noqa: E402


def test_pr_to_doc_renders_tagged_markdown():
    label, content = pr_to_doc({
        "number": 42,
        "title": "Implement async email via Celery",
        "body": "Move SMTP off the checkout path to cut p95 latency.",
        "author": "@priya-sharma",
        "merged_at": "2024-08-16T10:00:00Z",
        "files": ["checkout/views.py", "checkout/tasks.py"],
    })
    assert label == "PR-42.md"
    assert "[source_type: PR]" in content
    assert "[pr_number: 42]" in content
    assert "[author: priya-sharma]" in content      # leading @ stripped
    assert "[merged: 2024-08-16]" in content         # date only
    assert "[files: checkout/views.py, checkout/tasks.py]" in content
    assert "# PR #42: Implement async email via Celery" in content
    assert "cut p95 latency" in content


def test_pr_to_doc_handles_empty_body():
    label, content = pr_to_doc({"number": 7, "title": "x", "body": "", "author": "", "merged_at": "", "files": []})
    assert label == "PR-7.md"
    assert "(no description provided)" in content
    # data_id derives from the label, so forget/dedup work on live PRs too.
    assert corpus_file_data_id("PR-7.md") == corpus_file_data_id(label)


# ---------------------------------------------------------------------------
# graph_viz — Mermaid evidence subgraph for the PR comment (pure, no network)
# ---------------------------------------------------------------------------
from sentinel.graph_viz import build_mermaid  # noqa: E402

_NBID = {
    "a": {"name": "adr-001", "type": "Entity"},
    "p": {"name": "pr #42", "type": "Entity"},
    "s": {"name": "slack discussion", "type": "Entity"},
    "e": {"name": "email service", "type": "Entity"},
    "person": {"name": "priya sharma", "type": "Entity"},
    "d": {"name": "2024-08-14", "type": "Entity"},
}
_EDGES = [
    {"src": "a", "dst": "s", "rel": "discussed_in"},
    {"src": "a", "dst": "p", "rel": "implements"},
    {"src": "p", "dst": "a", "rel": "implements"},      # reciprocal — should be deduped
    {"src": "a", "dst": "e", "rel": "pertains_to"},
    {"src": "a", "dst": "person", "rel": "authored_by"},
    {"src": "a", "dst": "d", "rel": "accepted_on"},     # date — should be pruned
    {"src": "x", "dst": "x", "rel": "contains"},        # struct/orphan — ignored
]


def test_build_mermaid_renders_typed_subgraph():
    out = build_mermaid(_NBID, _EDGES, "ADR-001 (async email)", "This PR — sync email")
    assert out.startswith("```mermaid") and out.rstrip().endswith("```")
    assert "flowchart LR" in out
    assert "🔻 This PR — sync email" in out           # incoming node
    assert 'INC -->|"reverses"|' in out               # incoming reverses the decision
    assert "ADR-001" in out                            # decision label
    assert "classDef decision" in out and "classDef slack" in out
    assert '|"discussed in"|' in out                   # typed edge label, underscore->space
    # date node pruned; reciprocal implements collapsed to a single pair edge
    assert "2024-08-14" not in out
    assert out.count('|"implements"|') == 1


def test_build_mermaid_empty_when_decision_absent():
    assert build_mermaid(_NBID, _EDGES, "ADR-999 (missing)") == ""


# ===========================================================================
# PR-keyed decision identity, trust tiers, retired ledger, API snapshot
# (the API-only / no-markdown re-anchor — PRODUCT_SPEC §3 / §8.1)
# ===========================================================================
import json as _json  # noqa: E402

from sentinel.resolve import _pr_number, decision_ref_from_text  # noqa: E402
from sentinel.retired import (  # noqa: E402
    record_retired,
    retired_data_ids,
    retired_pr_numbers,
)
from sentinel.sources import incoming_text, issue_to_doc  # noqa: E402
from sentinel.trust import provenance_tier  # noqa: E402


# --- _pr_number: PR-keyed reference parsing (the new decision identity) ---

def test_pr_number_hash_form():
    assert _pr_number("PR #42 (async email)") == 42


def test_pr_number_hyphen_and_space_forms():
    assert _pr_number("PR-19") == 19
    assert _pr_number("PR 31 postgres") == 31
    assert _pr_number("pr#7 something") == 7


def test_pr_number_no_match_returns_none():
    assert _pr_number("ADR-001 only") is None
    assert _pr_number("") is None


def test_decision_ref_from_text_extracts_pr():
    body = "> ## 🧠 Memory Review\nThis would supersede **PR #42 (async email)**. /sentinel intentional"
    assert decision_ref_from_text(body) == "PR #42"
    assert decision_ref_from_text("no pr here") == ""


# --- feedback_signature is now PR-keyed first, ADR for back-compat ---

def test_feedback_signature_pr_keyed():
    assert feedback_signature("PR #42 (async email)") == "PR-42"
    assert feedback_signature("PR-19") == "PR-19"
    # legacy ADR refs still collapse correctly
    assert feedback_signature("ADR-001 (x)") == "ADR-001"


# --- retired.json ledger (the durable forget backstop, replaces ADR supersede) ---

def test_retired_ledger_roundtrip_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_RETIRED_DIR", str(tmp_path))
    assert retired_pr_numbers() == set()
    assert retired_data_ids() == set()

    record_retired("PR #42 (async email)", pr_number=42, data_ids=["id-a", "id-b"])
    record_retired("PR #42 again", pr_number=42, data_ids=["id-a"])  # same key — idempotent

    assert retired_pr_numbers() == {42}
    assert retired_data_ids() == {"id-a", "id-b"}
    ledger = _json.loads((tmp_path / ".sentinel" / "retired.json").read_text())
    assert len([e for e in ledger if e["pr_number"] == 42]) == 1


# --- trust tier: only approved PRs drive the confident flag (minimal M9) ---

def test_provenance_tier_approved_via_env(monkeypatch):
    monkeypatch.setenv("SENTINEL_APPROVED_PRS", "42, 31")
    monkeypatch.delenv("SENTINEL_RETIRED_DIR", raising=False)
    assert provenance_tier("PR #42 (async email)") == "approved"
    assert provenance_tier("PR #31 (postgres)") == "approved"


def test_provenance_tier_inferred_when_not_approved(monkeypatch):
    monkeypatch.setenv("SENTINEL_APPROVED_PRS", "42")
    assert provenance_tier("PR #99 (unknown)") == "inferred"
    assert provenance_tier("no pr reference") == "inferred"  # conservative default


# --- issue_to_doc: live/snapshot issue → ingestible tagged doc (pure) ---

def test_issue_to_doc_renders_tagged_markdown():
    label, content = issue_to_doc({
        "number": 91,
        "title": "Black Friday checkout latency regression",
        "body": "p95 climbed to 1340ms; ~800ms was a blocking provider call.",
        "author": "@daniel-osei",
        "state": "closed",
        "created_at": "2024-08-12T09:00:00Z",
        "labels": ["incident", "latency"],
    })
    assert label == "ISSUE-91.md"
    assert "[source_type: Issue]" in content
    assert "[issue_number: 91]" in content
    assert "[author: daniel-osei]" in content   # leading @ stripped
    assert "[status: closed]" in content
    assert "[date: 2024-08-12]" in content        # date only
    assert "[labels: incident, latency]" in content
    assert "# Issue #91: Black Friday checkout latency regression" in content
    # data_id derives from the label, so forget/dedup work on live issues too.
    assert corpus_file_data_id("ISSUE-91.md") == corpus_file_data_id(label)


# --- API snapshot is the offline memory source (no markdown) ---

def test_gather_memory_reads_snapshot(tmp_path, monkeypatch):
    from sentinel import sources
    snap = tmp_path / "snap.json"
    snap.write_text(_json.dumps({
        "prs": [
            {"number": 42, "title": "async email", "body": "queue", "author": "p",
             "merged_at": "2024-08-16T12:00:00Z", "files": ["checkout/views.py"]},
            {"number": 57, "title": "sync email", "body": "inline", "author": "n",
             "merged_at": None, "files": []},  # open reversal — not memory
        ],
        "issues": [{"number": 91, "title": "incident", "body": "latency", "author": "d",
                    "state": "closed", "created_at": "2024-08-12T09:00:00Z", "labels": []}],
        "incoming": [{"number": 57, "slug": "sync_email", "title": "sync", "state": "open",
                      "text": "make email synchronous"}],
    }), encoding="utf-8")
    monkeypatch.setenv("SENTINEL_API_SNAPSHOT", str(snap))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    prs, issues = sources.gather_memory()
    assert {p["number"] for p in prs} == {42, 57}
    assert {i["number"] for i in issues} == {91}
    assert sources.refreshing_live() is False
    assert incoming_text("sync_email") == "make email synchronous"
    assert incoming_text(57) == "make email synchronous"
    assert incoming_text("missing") == ""


# ===========================================================================
# Visual Memory Recap — the interactive HTML artifact (sentinel.recap)
# ===========================================================================
from sentinel.recap import (  # noqa: E402
    curate_subgraph,
    parse_pr,
    render_recap_html,
    traversal_path,
)

_PR_TEXT = """# PR #57: Simplify checkout — send confirmation email synchronously

**Author:** @new-contributor
**Branch:** simplify-email → main

## Description

Simplifies email: sends inline, no queue.

## Diff

```diff
--- a/checkout/views.py
+++ b/checkout/views.py
@@ def checkout(request):
         order = create_order(request.user, request.cart)
-        send_order_confirmation_task.delay(order.id)
+        send_email_smtp(order.user.email, render_confirmation(order))
```
"""

_RECAP_NBID = {
    "dec": {"name": "PR #42 (async email)", "type": "Entity"},
    "i91": {"name": "Issue #91 black friday incident", "type": "Entity"},
    "eml": {"name": "email service", "type": "Entity"},
    "person": {"name": "priya sharma", "type": "Entity"},
    "d": {"name": "2024-08-14", "type": "Entity"},
}
_RECAP_EDGES = [
    {"src": "dec", "dst": "i91", "rel": "justified_by"},
    {"src": "dec", "dst": "eml", "rel": "pertains_to"},
    {"src": "dec", "dst": "person", "rel": "authored_by"},
    {"src": "dec", "dst": "d", "rel": "accepted_on"},   # date — pruned
    {"src": "dec", "dst": "dec", "rel": "self"},        # self-loop — ignored
]


def _recap_verdict(**over):
    base = dict(
        analysis="Removes async dispatch, adds inline SMTP.",
        reverses_decision=True,
        decision_reference="PR #42 (async email)",
        original_reasoning="Async email cut ~800ms of checkout latency after Black Friday.",
        impact_if_merged="Reintroduces the 800ms blocking SMTP call.",
        assumption="the SMTP call costs ~800ms on the critical path",
        affected_capability="Messaging",
        evidence_chain="PR #42 (made it async) -> Issue #91 (the latency incident)",
        confidence=0.92,
        provenance_tier="approved",
    )
    base.update(over)
    return Verdict(**base)


# --- parse_pr: title / meta / diff extraction ---

def test_parse_pr_extracts_title_meta_and_diff():
    p = parse_pr(_PR_TEXT)
    assert p["title"].startswith("PR #57")
    assert any("new-contributor" in m for m in p["meta"])
    kinds = [k for k, _ in p["diff"]]
    assert "file" in kinds and "hunk" in kinds and "del" in kinds and "add" in kinds


def test_parse_pr_no_diff_block_is_graceful():
    p = parse_pr("# PR #9: docs tweak\n\nJust prose, no diff.")
    assert p["title"] == "PR #9: docs tweak"
    assert p["diff"] == []


# --- curate_subgraph: PR-keyed root resolution + pruning ---

def test_curate_subgraph_resolves_pr_keyed_root():
    nodes, edges = curate_subgraph(_RECAP_NBID, _RECAP_EDGES, "PR #42 (async email)")
    roles = {n["id"]: n["role"] for n in nodes}
    assert roles["dec"] == "decision"
    assert roles["i91"] == "issue"
    ids = {n["id"] for n in nodes}
    assert "d" not in ids                      # date pruned
    rels = {e["rel"] for e in edges}
    assert "justified by" in rels              # underscore -> space


def test_curate_subgraph_empty_when_root_missing():
    assert curate_subgraph(_RECAP_NBID, _RECAP_EDGES, "PR #999 (missing)") == ([], [])


def test_curate_subgraph_resolves_root_by_topic_in_parens():
    nbid = {"n1": {"name": "decision: async email via celery", "type": "Entity"}}
    nodes, _ = curate_subgraph(nbid, [], "PR #7 (async email)")
    assert nodes and nodes[0]["role"] == "decision"


# --- traversal_path: the SPINE-1 animation order ---

def test_traversal_path_incoming_decision_issue():
    nodes = [
        {"id": "inc", "label": "PR #57", "role": "incoming"},
        {"id": "dec", "label": "Decision", "role": "decision"},
        {"id": "i91", "label": "Issue #91", "role": "issue"},
    ]
    edges = [
        {"src": "inc", "dst": "dec", "rel": "reverses"},
        {"src": "dec", "dst": "i91", "rel": "justified by"},
    ]
    assert traversal_path(nodes, edges) == ["inc", "dec", "i91"]


# --- render_recap_html: the self-contained artifact ---

def test_render_recap_contains_diff_belief_and_graph():
    v = _recap_verdict()
    nodes, edges = curate_subgraph(_RECAP_NBID, _RECAP_EDGES, v.decision_reference)
    html_out = render_recap_html(v, _PR_TEXT, [("Current memory", nodes, edges)])
    assert html_out.startswith("<!DOCTYPE html>")
    assert "Visual Memory Recap" in html_out
    assert "send_order_confirmation_task.delay" in html_out          # the diff
    assert "Memory conflict" in html_out                              # the annotation
    assert "~800ms of checkout latency" in html_out                   # the belief
    assert "92%" in html_out                                          # confidence
    assert "Messaging" in html_out                                    # capability chip
    assert "<svg" in html_out and "Play the traversal" in html_out    # interactive graph
    assert "http" not in html_out.split("</style>")[0]                # no CDN in the CSS


def test_render_recap_escapes_untrusted_text():
    v = _recap_verdict(original_reasoning='<script>alert("x")</script>')
    html_out = render_recap_html(v, _PR_TEXT, [])
    assert "<script>alert" not in html_out
    assert "&lt;script&gt;" in html_out


def test_render_recap_without_graph_still_renders_page():
    v = _recap_verdict(assumption="", evidence_chain="")
    html_out = render_recap_html(v, _PR_TEXT, [])
    assert "Visual Memory Recap" in html_out
    assert "Play the traversal" not in html_out       # graph section omitted
    assert "supersede" in html_out                     # belief card still there


def test_render_recap_two_states_renders_toggle():
    v = _recap_verdict()
    nodes, edges = curate_subgraph(_RECAP_NBID, _RECAP_EDGES, v.decision_reference)
    after = [dict(n, role="retired") if n["role"] == "decision" else n for n in nodes]
    html_out = render_recap_html(
        v, _PR_TEXT, [("Before forget", nodes, edges), ("After forget", after, edges)]
    )
    assert "Before forget" in html_out and "After forget" in html_out
    assert 'showState(1)' in html_out                  # the toggle buttons exist
    assert html_out.count('class="gstate"') == 2


def test_build_mermaid_resolves_pr_keyed_reference():
    nbid = {
        "d": {"name": "PR #16 (async email dispatch)", "type": "Entity"},
        "i": {"name": "issue #8 latency incident", "type": "Entity"},
    }
    edges = [{"src": "d", "dst": "i", "rel": "justified_by"}]
    out = build_mermaid(nbid, edges, "PR #16 (async email dispatch via queue)")
    # The ADR-era resolver returned "" here; the lenient resolver must find the node.
    assert "flowchart LR" in out
    assert '|"justified by"|' in out


def test_find_root_token_overlap_fallback():
    from sentinel.graph_viz import find_root

    # No "pr #16" entity exists (cognify skipped it) — the resolver must still find the
    # decision node by distinctive-word overlap, and a single shared word must NOT match.
    nbid = {
        "a": {"name": "order_confirmation_email", "type": "Entity"},          # 1 hit — too weak
        "b": {"name": "pr-42-implement-async-email.md", "type": "Entity"},    # 2 hits — winner
        "c": {"name": "gateway rate limiting", "type": "Entity"},
    }
    assert find_root(nbid, "PR #16 (async email dispatch)") == "b"
    assert find_root({"c": nbid["c"]}, "PR #16 (async email dispatch)") is None


def test_chain_subgraph_from_verdict_fields():
    from sentinel.recap import chain_subgraph

    v = _recap_verdict()
    nodes, edges = chain_subgraph(v, incoming_label="PR #57 sync email")
    roles = [n["role"] for n in nodes]
    assert roles[0] == "incoming" and "decision" in roles and "issue" in roles
    rels = {e["rel"] for e in edges}
    assert "reverses" in rels and "justified by" in rels
    assert chain_subgraph(Verdict(analysis="x", reverses_decision=False)) == ([], [])


def test_should_flag_false_when_superseded_intentionally():
    v = Verdict(analysis="x", reverses_decision=True,
                decision_reference="PR #16 (async email)", superseded_intentionally=True)
    assert v.should_flag is False


def test_render_comment_superseded_is_calm_note():
    v = _recap_verdict(superseded_intentionally=True)
    out = render_comment(v)
    assert "intentionally superseded" in out
    assert "[!CAUTION]" not in out
    assert "/sentinel intentional" not in out.split("superseded")[0]  # no CTA table
