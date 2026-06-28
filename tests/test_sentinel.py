"""Pure-function tests — no Cognee, no network, no LLM calls.

Run with:  pip install pytest && pytest tests/
"""

import pytest

from sentinel.comment import render_comment
from sentinel.detect import Verdict, _normalize_confidence
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
