"""Render a Verdict into the polished GitHub PR comment Sentinel posts.

Three comments, all designed to read like a product surface, not a bot dump:
  - render_comment(reversal)   → a ⚠️ "reversed decision" card with rationale + CTA
  - render_comment(clean)      → a calm ✅ "nothing reversed" note
  - render_resolution(...)     → a ✅ "decision retired" confirmation (the forget loop)

Formatting leans on GitHub-flavored markdown: alert callouts (> [!CAUTION]), shields
badges, blockquotes for quoted reasoning, and a <details> for the chain-of-thought.
"""

from sentinel.detect import Verdict

_PURPLE = "7c3aed"


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


def render_comment(verdict: Verdict) -> str:
    """Markdown comment for a PR: the ⚠️ reversal card, or a calm clean-bill note."""
    if not verdict.reverses_decision:
        return "\n".join([
            "> [!NOTE]",
            "> ## ✅ Sentinel — no past decision reversed",
            ">",
            "> No past decision in Sentinel's memory appears to be reversed by this PR. Looks good to merge.",
            "",
            f"{_sentinel_badge()} ![memory](" + _badge("memory", "no conflicts", "2ea44f") + ")",
            "",
            _footer("institutional-memory guardian"),
        ])

    ref = verdict.decision_reference or "a past decision"
    pct = _pct(verdict.confidence)
    bar = _conf_bar(verdict.confidence)

    lines = [
        "> [!CAUTION]",
        "> ## 🛡️ This PR reverses a past engineering decision",
        ">",
        f"> **{ref}** was a deliberate choice — and this change quietly undoes it.",
        "",
        f"{_sentinel_badge()} "
        f"![status]({_badge('decision', 'REVERSED', 'd1242f')}) "
        f"![confidence]({_badge('confidence', pct, _conf_color(verdict.confidence))})",
        "",
        "### 💡 Why it was decided",
        f"> {verdict.original_reasoning or '_(original rationale not captured)_'}",
        "",
        "### ⚠️ What merging this would reintroduce",
        f"> {verdict.impact_if_merged or '_(impact not captured)_'}",
        "",
    ]

    if verdict.analysis:
        lines += [
            "<details>",
            "<summary>🔎 <b>How Sentinel reached this verdict</b></summary>",
            "",
            f"> {verdict.analysis}",
            "",
            "</details>",
            "",
        ]

    lines += [
        f"**Confidence** &nbsp; `{bar}` &nbsp; **{pct}**",
        "",
        "---",
        "",
        "### Was this intentional?",
        "",
        "| | |",
        "|:--|:--|",
        "| ✅ **Yes, it's deliberate** | Comment `/sentinel intentional` — I'll record the superseding decision, retire "
        f"{ref}, and stop flagging this. |",
        "| 🔄 **No / not sure** | Please reconsider — the original reasoning above may still hold. |",
        "",
        _footer("catches PRs that silently reverse past decisions"),
    ]
    return "\n".join(lines)


def render_resolution(decision_reference: str, pr_number: int | None = None) -> str:
    """The ✅ confirmation posted after '/sentinel intentional' retires a decision."""
    ref = decision_reference or "the decision"
    where = f" in #{pr_number}" if pr_number else ""
    return "\n".join([
        "> [!TIP]",
        "> ## ✅ Decision retired — Sentinel updated its memory",
        ">",
        f"> You confirmed this override is intentional, so **{ref}** is no longer binding.",
        "",
        f"{_sentinel_badge()} ![retired]({_badge('decision', 'retired', '6e7781')})",
        "",
        "What I just did:",
        "",
        f"- 📝 Marked **{ref}** as `Superseded` in `docs/adr/`{where}",
        "- 🧠 Dropped it from institutional memory on the next ingest",
        "- 🔕 I won't flag this reversal again",
        "",
        "> _The forget loop: memory that updates the moment the team makes a new call._",
        "",
        _footer("forget loop · memory updated"),
    ])
