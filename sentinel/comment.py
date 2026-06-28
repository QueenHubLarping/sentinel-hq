"""Render a Verdict into the GitHub PR comment Sentinel would post."""

from sentinel.detect import Verdict


def render_comment(verdict: Verdict) -> str:
    """Markdown comment for a PR. Returns the ⚠️ warning, or a clean-bill note."""
    if not verdict.reverses_decision:
        return "✅ **Sentinel:** no past decision appears to be reversed by this PR."

    return (
        f"⚠️ **This PR reverses a past decision: {verdict.decision_reference}**\n\n"
        f"**Why it was decided:** {verdict.original_reasoning}\n\n"
        f"**What this change reintroduces:** {verdict.impact_if_merged}\n\n"
        "Was this intentional? Reply `/sentinel intentional` to record a superseding "
        "decision (the old one is retired, so I stop flagging this). Otherwise, please "
        "reconsider — the original reasoning may still hold.\n\n"
        f"— 🛡️ _Sentinel · confidence {verdict.confidence:.0%}_"
    )
