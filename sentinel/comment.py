"""Render a Verdict into the polished GitHub PR comment Sentinel posts.

The climax artifact is the **Memory Review** card (PRODUCT_SPEC §3): not a bot dump of
"related documents", but a learning story — *what this PR changes · why it matters · what
your organization currently believes · the memory impact*. It reads like a colleague who
remembers the reasoning, reconstructed from the team's own PR + issue history.

Trust-tier drives assertiveness (§8.1 / §8.3):
  - provenance_tier == "approved"  → the confident supersession card (a human stands behind
    the belief; this PR *would supersede* an active learning). Loud `> [!CAUTION]`.
  - provenance_tier == "inferred"  → a SOFTER proposal — Sentinel only *inferred* the learning
    from PR history and asks for confirmation. Muted `> [!NOTE]`, never the loud styling.

Surfaces, all reused: alert callouts (> [!CAUTION] / [!NOTE] / [!TIP]), shields badges, a
unicode confidence meter, a <details> chain-of-thought, the inline ```mermaid evidence graph,
and the footer.
"""

from sentinel.detect import Verdict

_PURPLE = "7c3aed"

# How memory feels — the load-bearing learning story, with no diff lifted into prose.
_NO_LINK_NOTE = (
    "_no shared keywords, no `#ref` from this PR — recovered by graph + semantic reasoning_"
)


def _pct(c: float) -> str:
    return f"{max(0.0, min(1.0, c)):.0%}"


def _conf_color(c: float) -> str:
    return "2ea44f" if c >= 0.8 else "dbab09" if c >= 0.5 else "d1242f"


def _conf_bar(c: float) -> str:
    """A 10-cell unicode meter, e.g. 0.9 -> █████████░."""
    filled = max(0, min(10, round(c * 10)))
    return "█" * filled + "░" * (10 - filled)


def _badge(label: str, message: str, color: str) -> str:
    """A shields.io badge URL (handles the characters that need escaping).

    Order matters: escape literal '%' before introducing any '%20' for spaces, or the
    space-encoding gets double-escaped into '%2520'.
    """
    def enc(s: str) -> str:
        return (
            s.replace("%", "%25").replace("-", "--").replace("_", "__").replace(" ", "%20")
        )
    return f"https://img.shields.io/badge/{enc(label)}-{enc(message)}-{color}?style=flat-square"


def _sentinel_badge() -> str:
    return f"![Sentinel]({_badge('Sentinel', 'institutional memory', _PURPLE)})"


def _footer(tagline: str) -> str:
    return f"<sub>🛡️ <b>Sentinel</b> · {tagline}</sub>"


def _capability(verdict: Verdict) -> str:
    """The affected capability for the header, e.g. 'Messaging'. Empty if unknown."""
    return (getattr(verdict, "affected_capability", "") or "").strip()


def _header(verdict: Verdict, lead: str = "") -> str:
    """`## 🧠 Memory Review — Messaging`, gracefully dropping the capability when absent."""
    cap = _capability(verdict)
    title = "🧠 Memory Review"
    if cap:
        title += f" — {cap}"
    if lead:
        title += f" · {lead}"
    return f"> ## {title}"


def render_comment(verdict: Verdict, graph_section: str = "") -> str:
    """Markdown comment for a PR — the Memory Review card.

    Three shapes: the confident supersession card (approved memory), the soft "possible"
    proposal (inferred memory), the muted-by-feedback note, or — when nothing is
    contradicted — a calm "nothing contradicted" note.

    graph_section: an optional ```mermaid block (the evidence subgraph Sentinel traversed,
    from sentinel.graph_viz) — shown inline so the reviewer SEES the typed, multi-hop
    decision graph (PR ↔ Issue ↔ Decision), not just a verdict.
    """
    if verdict.reverses_decision and getattr(verdict, "superseded_intentionally", False):
        return render_superseded(verdict)
    if verdict.reverses_decision and verdict.suppressed_by_feedback:
        return render_suppressed(verdict)
    if not verdict.reverses_decision:
        return "\n".join([
            "> [!NOTE]",
            _header(verdict, "nothing contradicted"),
            ">",
            "> Sentinel read this PR against its memory and found **no active learning it "
            "supersedes**. Nothing to review — looks good to merge.",
            "",
            f"{_sentinel_badge()} ![memory](" + _badge("memory", "no conflicts", "2ea44f") + ")",
            "",
            _footer("turns engineering activity into organizational learning"),
        ])

    inferred = (getattr(verdict, "provenance_tier", "") or "").strip().lower() == "inferred"
    return _render_inferred(verdict, graph_section) if inferred else _render_approved(verdict, graph_section)


def _belief_block(verdict: Verdict) -> list[str]:
    """The shared 'What your organization currently believes' section.

    The quoted reasoning, the conditional assumption it rests on, and the reconstruction
    path — the evidence chain that proves only graph + semantic recall could find it.
    """
    ref = verdict.decision_reference or "a past decision"
    reasoning = verdict.original_reasoning or "_(original rationale not captured)_"
    assumption = (getattr(verdict, "assumption", "") or "").strip()
    chain = (getattr(verdict, "evidence_chain", "") or "").strip()

    lines = [
        "> ### What your organization currently believes",
        f"> > {reasoning}",
    ]
    if assumption:
        lines += [">", f"> **This holds only while:** {assumption}"]
    lines += [
        ">",
        f"> **Reconstructed via:**  {chain or ref}",
        f"> {_NO_LINK_NOTE}",
    ]
    return lines


def _changes_line(verdict: Verdict) -> str:
    """One line for 'What this PR changes' — the diff's effect, never the diff itself."""
    return verdict.impact_if_merged or verdict.analysis or "_(change effect not captured)_"


def _graph_block(graph_section: str) -> list[str]:
    if not graph_section:
        return []
    return [
        "> ### The decision graph behind this",
        ">",
        "> _Sentinel reached this by **traversing typed edges across the team's history** in "
        "its Cognee knowledge graph — **PR ↔ Issue ↔ Decision** — not by keyword search:_",
        "",
        graph_section,
        "",
    ]


def _cot_block(verdict: Verdict) -> list[str]:
    if not verdict.analysis:
        return []
    return [
        "<details>",
        "<summary>🔎 <b>How Sentinel reconstructed this</b></summary>",
        "",
        f"> {verdict.analysis}",
        "",
        "</details>",
        "",
    ]


def _render_approved(verdict: Verdict, graph_section: str) -> str:
    """Confident supersession card — a human stands behind the belief (approved tier)."""
    ref = verdict.decision_reference or "a past decision"
    pct = _pct(verdict.confidence)
    bar = _conf_bar(verdict.confidence)

    lines = [
        "> [!CAUTION]",
        _header(verdict),
        ">",
        "> This PR doesn't just change code — it changes **what your organization believes**.",
        "",
        f"{_sentinel_badge()} "
        f"![memory]({_badge('memory', 'supersedes a learning', 'd1242f')}) "
        f"![tier]({_badge('belief', 'human-approved', _PURPLE)}) "
        f"![confidence]({_badge('confidence', pct, _conf_color(verdict.confidence))})",
        "",
        "> ### What this PR changes",
        f"> {_changes_line(verdict)}",
        ">",
        "> ### Why this matters",
        "> This supersedes an **active architectural learning** your team is standing on.",
        ">",
    ]
    lines += _belief_block(verdict)
    lines += [
        ">",
        "> ### Memory impact",
        f"> ⚠️  This PR would **supersede** that learning ({ref}). "
        f"Confidence in the current belief: **{pct}**.",
        "",
    ]
    lines += _graph_block(graph_section)
    lines += _cot_block(verdict)
    lines += [
        f"**Confidence in the belief** &nbsp; `{bar}` &nbsp; **{pct}**",
        "",
        "---",
        "",
        "### Is this intentional?",
        "",
        "_Sentinel is a detective, not a judge — it states what it knows and asks what only you do._",
        "",
        "| | |",
        "|:--|:--|",
        "| ✅ **Yes — we're superseding it on purpose** | Comment `/sentinel intentional` — I'll "
        f"record the new learning, retire {ref}, and stop flagging this. |",
        "| 👎 **This review isn't useful** | Comment `/sentinel noise` — I'll learn this drift is "
        "noise and stop raising it. |",
        "| 🔄 **No / not sure** | Please reconsider — the belief above may still hold. |",
        "",
        _footer("catches PRs that quietly supersede what your org learned"),
    ]
    return "\n".join(lines)


def _render_inferred(verdict: Verdict, graph_section: str) -> str:
    """Soft proposal — Sentinel only *inferred* this learning from PR history (inferred tier).

    No CAUTION styling, no assertion: it surfaces a *possible* supersession and asks the
    human to confirm, which is also what promotes the memory inferred → approved (§8.2).
    """
    ref = verdict.decision_reference or "a past decision"
    pct = _pct(verdict.confidence)
    bar = _conf_bar(verdict.confidence)

    lines = [
        "> [!NOTE]",
        _header(verdict, "possible"),
        ">",
        "> ⚠️  **Possible** — I *inferred* this learning from the team's PR history; nobody has "
        "confirmed it yet. Worth a look before it merges?",
        "",
        f"{_sentinel_badge()} "
        f"![memory]({_badge('memory', 'possible supersession', 'dbab09')}) "
        f"![tier]({_badge('belief', 'machine-inferred', '6e7781')}) "
        f"![confidence]({_badge('confidence', pct, _conf_color(verdict.confidence))})",
        "",
        "> ### What this PR changes",
        f"> {_changes_line(verdict)}",
        ">",
        "> ### Why this might matter",
        "> It looks like this **supersedes a learning I reconstructed** from PR history — but as "
        "an *inferred* belief, I'm proposing, not asserting.",
        ">",
    ]
    lines += _belief_block(verdict)
    lines += [
        ">",
        "> ### Memory impact",
        f"> This *may* supersede {ref}. As inferred memory it can't drive a hard flag — "
        f"a one-line confirm promotes it to approved. Confidence: **{pct}**.",
        "",
    ]
    lines += _graph_block(graph_section)
    lines += _cot_block(verdict)
    lines += [
        f"**Confidence in the belief** &nbsp; `{bar}` &nbsp; **{pct}**",
        "",
        "---",
        "",
        "### Can you confirm?",
        "",
        "| | |",
        "|:--|:--|",
        "| ✅ **Yes, that was a real decision** | Comment `/sentinel intentional` — I'll promote "
        f"this learning ({ref}) to approved, retire it as superseded, and stop flagging this. |",
        "| 👎 **No — this isn't a real learning** | Comment `/sentinel noise` — I'll learn this "
        "drift is noise and stop raising it. |",
        "| 🔄 **Not sure** | No action needed — I'll keep it as a candidate and may re-ask on a "
        "related PR. |",
        "",
        _footer("proposes inferred learnings · asks before it asserts"),
    ]
    return "\n".join(lines)


def render_superseded(verdict: Verdict) -> str:
    """The calm note when the cited decision was already retired via '/sentinel intentional'.

    The forget loop's other half: the team ratified this supersession, so a change aligned
    with the NEW belief is not a reversal worth raising. Honest — Sentinel says what it
    found and why it is staying quiet."""
    ref = verdict.decision_reference or "a past learning"
    return "\n".join([
        "> [!NOTE]",
        _header(verdict, "superseded — staying quiet"),
        ">",
        f"> This change relates to **{ref}**, which your team **intentionally superseded** "
        "(`/sentinel intentional`). The old learning is retired; this PR is consistent with "
        "the organization's current belief.",
        "",
        f"{_sentinel_badge()} ![superseded]({_badge('learning', 'superseded', '6e7781')})",
        "",
        _footer("forget loop · retired learnings stay retired"),
    ])


def render_suppressed(verdict: Verdict) -> str:
    """The calm note shown when a supersession is real but the team muted it via '/sentinel noise'.

    Honest by design: Sentinel still *detected* the contradiction — it's just respecting the
    team's earlier 👎 and staying quiet, and it says so.
    """
    ref = verdict.decision_reference or "a past learning"
    return "\n".join([
        "> [!NOTE]",
        _header(verdict, "staying quiet (you muted this)"),
        ">",
        f"> This change does supersede **{ref}**, but the team previously marked this drift as "
        "noise via `/sentinel noise`, so Sentinel isn't raising it.",
        "",
        f"{_sentinel_badge()} ![muted]({_badge('flag', 'muted by feedback', '6e7781')})",
        "",
        "> _Changed your mind? Re-enable it any time and Sentinel will review this drift again._",
        "",
        _footer("improve loop · learns which flags to stop raising"),
    ])


def render_feedback_recorded(decision_reference: str, pr_number: int | None = None) -> str:
    """The ✅ confirmation posted after '/sentinel noise' records the 👎 (the improve loop)."""
    ref = decision_reference or "this drift"
    where = f" in #{pr_number}" if pr_number else ""
    return "\n".join([
        "> [!TIP]",
        "> ## 👎 Got it — Sentinel learned this review was noise",
        ">",
        f"> You marked the **{ref}** review as unhelpful{where}, so Sentinel wrote that into its "
        "memory and won't raise this drift again.",
        "",
        f"{_sentinel_badge()} ![improved]({_badge('memory', 'feedback recorded', '7c3aed')})",
        "",
        "What I just did:",
        "",
        f"- 🧠 Stored a 👎 feedback record for **{ref}** in the memory graph (`cognee.improve`)",
        "- 🔕 Down-weighted this drift in future recall (live — next run reads it)",
        "",
        "> _The improve loop: detective, not nag — it learns which reviews you don't want._",
        "",
        _footer("improve loop · feedback recorded"),
    ])


def render_resolution(decision_reference: str, pr_number: int | None = None) -> str:
    """The ✅ confirmation posted after '/sentinel intentional' retires a learning (forget loop)."""
    ref = decision_reference or "the learning"
    where = f" in #{pr_number}" if pr_number else ""
    return "\n".join([
        "> [!TIP]",
        "> ## ✅ Learning retired — Sentinel updated its memory",
        ">",
        f"> You confirmed this supersession is intentional{where}, so **{ref}** is no longer what "
        "your organization believes.",
        "",
        f"{_sentinel_badge()} ![retired]({_badge('learning', 'superseded', '6e7781')})",
        "",
        "What I just did:",
        "",
        f"- 🧠 Retired the **{ref}** learning from Sentinel's memory (`cognee.forget`)",
        "- 📌 Recorded it as superseded so it won't be re-ingested",
        "- 🔕 I won't flag this supersession again",
        "",
        "> _The forget loop: memory that updates the moment the team makes a new call._",
        "",
        _footer("forget loop · memory updated"),
    ])
