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
