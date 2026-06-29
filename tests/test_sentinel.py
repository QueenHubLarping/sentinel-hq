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
    assert "✅" in comment
    assert "no past decision" in comment.lower()


def test_render_comment_reversal_contains_key_fields():
    v = Verdict(
        analysis="Removes async Celery dispatch, adds inline SMTP.",
        reverses_decision=True,
        decision_reference="ADR-001 (async email)",
        original_reasoning="800ms SMTP block was the single biggest latency driver.",
        impact_if_merged="Reintroduces 800ms blocking SMTP call in checkout.",
        confidence=0.9,
    )
    comment = render_comment(v)
    assert "⚠️" in comment
    assert "ADR-001" in comment
    assert "800ms" in comment
    assert "90%" in comment
    assert "/sentinel intentional" in comment


def test_render_comment_reversal_confidence_formats_as_percent():
    v = Verdict(
        analysis="x",
        reverses_decision=True,
        decision_reference="ADR-001",
        original_reasoning="r",
        impact_if_merged="i",
        confidence=0.75,
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
    assert "🔕" in comment
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
    monkeypatch.setenv("SENTINEL_ADR_DIR", str(tmp_path))
    assert file_dismissed_signatures() == set()

    record_noise_file("ADR-001 (async email)")
    record_noise_file("ADR-001 something else")  # same signature — idempotent
    record_noise_file("ADR-003 (rate limiting)")

    assert file_dismissed_signatures() == {"ADR-001", "ADR-003"}
    # One entry per signature despite the repeated dismissal.
    body = dismissed_file().read_text(encoding="utf-8")
    assert body.count("ADR-001") == 1


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
