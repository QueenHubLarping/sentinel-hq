"""
Handle the human-in-the-loop decision: '/sentinel intentional'.

Sentinel is a detective, not a judge — it flags and asks; the team decides. When a
maintainer confirms an override is intentional, the contradicted decision is RETIRED
from memory (forget). After that, re-detecting the same PR yields no reversal — the
decision it was protecting no longer exists. This is the forget -> behavior-change loop.

Decision identity is **PR-keyed** (PRODUCT_SPEC §3): a decision is anchored to its
establishing PR (e.g. "PR #42 (async email)"). Selective forget removes only that
decision's document via cognee.forget(data_id=...) — graph nodes + vector embeddings for
that PR's doc are deleted; every other decision stays intact. The data_id is the same
stable UUID ingest.py assigned at add() time (corpus_file_data_id of the canonical
"PR-42.md" label), so forget works without internal Cognee dataset APIs and across CI
runner restarts. Durability backstop = `.sentinel/retired.json` (sentinel.retired), which
the next ingest skips — replacing the old "mark the ADR Superseded in docs/adr" trick.

The ADR-keyed helpers below (`_adr_number`, `supersede_adr_file`, `_mark_intentional_adr`)
are the legacy path, kept only until SPINE-2 is re-proven on the PR-keyed path (the §9
sequencing rule). mark_intentional dispatches to PR-keyed first, ADR only as a fallback.
"""

import re

import cognee

from sentinel.ingest import DATASET_NAME, adr_dir, corpus_file_data_id, prs_dir


def supersede_adr_file(adr_id: str, pr_number: int | None = None):
    """Mark the ADR file for *adr_id* as Superseded in docs/adr (source of truth).

    This is the durable, git-auditable way '/sentinel intentional' retires a decision
    on ephemeral CI runners: rewriting the '**Status:**' line to 'Superseded' makes the
    next ingest skip this ADR (see ingest.ingest_corpus), so detection stops flagging
    PRs that contradict it — without relying on a persistent graph.

    Returns the edited Path, or None if no matching ADR file was found.
    """
    matches = sorted(adr_dir().glob(f"{adr_id}*.md"))
    if not matches:
        return None
    path = matches[0]
    text = path.read_text(encoding="utf-8")
    note = "Superseded" + (f" (intentional override in #{pr_number})" if pr_number else " (intentional override)")
    new, n = re.subn(r"(\*\*Status:\*\*\s*).+", rf"\1{note}", text, count=1)
    if n == 0:
        # No status line present — insert one right after the H1 title (best effort).
        new = re.sub(r"(\A#.*\n)", rf"\1\n**Status:** {note}\n", text, count=1)
    path.write_text(new, encoding="utf-8")
    return path


def _adr_number(decision_reference: str) -> str | None:
    """Extract and normalize an ADR number from a model decision_reference string.

    Handles 'ADR-001 (async email...)', 'ADR-42', 'adr-003 foo', 'ADR 002', etc.
    Returns a zero-padded string like 'ADR-001', or None if no ADR pattern found.
    """
    m = re.search(r"ADR[- ](\d+)", decision_reference, re.IGNORECASE)
    if not m:
        return None
    return f"ADR-{int(m.group(1)):03d}"


def _pr_number(decision_reference: str) -> int | None:
    """Extract a PR number from a PR-keyed decision reference.

    Handles 'PR #42 (async email)', 'PR-42', 'PR 42', 'pr#19 ...'. Returns the int, or
    None if no PR pattern is found. This is the PR-keyed analogue of _adr_number and the
    new primary decision identity (PRODUCT_SPEC §3).
    """
    m = re.search(r"PR[\s#-]*?(\d+)", decision_reference, re.IGNORECASE)
    return int(m.group(1)) if m else None


def decision_ref_from_text(text: str) -> str:
    """Pull a clean 'PR #N' decision reference out of a longer comment body.

    Used by the '/sentinel intentional' flow to recover the decision Sentinel flagged from
    its own prior Memory Review comment, without re-running detection. Returns '' if none.
    """
    m = re.search(r"PR[\s#-]*?(\d+)", text, re.IGNORECASE)
    return f"PR #{m.group(1)}" if m else ""


async def mark_intentional(decision_reference: str = "") -> dict:
    """Retire the superseded decision via cognee.forget (PR-keyed), scoped to one decision.

    Resolves the establishing PR from the reference (e.g. 'PR #42'), forgets that PR's
    decision document(s) by their stable data_id, and records the retirement in
    `.sentinel/retired.json` so the next ingest skips it (durable on ephemeral runners).
    Falls back to the legacy ADR-keyed path only when the reference carries no PR number
    (kept until SPINE-2 is re-proven on the PR-keyed path — §9 sequencing rule).
    """
    from cognee.low_level import setup

    await setup()

    pr_num = _pr_number(decision_reference)
    if pr_num is not None:
        return await _mark_intentional_pr(decision_reference, pr_num)

    # Legacy fallback: reference carries no PR number (dormant ADR path).
    return await _mark_intentional_adr(decision_reference)


async def _mark_intentional_pr(decision_reference: str, pr_num: int) -> dict:
    """Forget the PR-keyed decision: every doc for this PR (live label + bundled file)."""
    from sentinel.retired import record_retired

    # The data_ids to forget: the canonical live-PR label ("PR-42.md", what sources.pr_to_doc
    # emits) plus any bundled corpus file(s) for that PR ("PR-42-implement-async-email.md").
    labels = {f"PR-{pr_num}.md"}
    for path in sorted(prs_dir().glob(f"PR-{pr_num}*.md")):
        labels.add(path.name)

    retired = []
    for label in sorted(labels):
        data_id = corpus_file_data_id(label)
        try:
            result = await cognee.forget(data_id=data_id, dataset=DATASET_NAME)
        except Exception as exc:  # noqa: BLE001 — a missing/duplicate id must not break forget
            result = {"skipped": str(exc)}
        retired.append({"data_id": str(data_id), "label": label, "result": result})

    # Durable backstop: record in .sentinel/retired.json (next ingest skips this PR).
    ledger = record_retired(
        decision_reference, pr_number=pr_num, data_ids=[r["data_id"] for r in retired]
    )

    return {
        "status": "retired",
        "decision": decision_reference,
        "pr_number": pr_num,
        "retired_items": len(retired),
        "items": retired,
        "ledger": str(ledger),
    }


async def _mark_intentional_adr(decision_reference: str = "") -> dict:
    """LEGACY ADR-keyed forget (dormant; removed after SPINE-2 re-proven — §9)."""
    adr_id = _adr_number(decision_reference)
    if not adr_id:
        return {
            "status": "error",
            "decision": decision_reference,
            "note": (
                f"Could not extract an ADR number from {decision_reference!r}. "
                "Expected a reference containing 'ADR-NNN'."
            ),
        }

    # Locate matching ADR files (e.g. "ADR-001-async-email.md") in the same
    # directory ingest read them from — the consuming repo's docs/adr when running
    # in CI, else the bundled corpus.
    adr_path = adr_dir()
    matches = sorted(adr_path.glob(f"{adr_id}*.md"))
    if not matches:
        return {
            "status": "not_found",
            "decision": decision_reference,
            "adr_id": adr_id,
            "note": (
                f"No ADR file found matching '{adr_id}*.md' in {adr_path}. "
                "Re-run ingest if the ADRs were recently changed."
            ),
        }

    # Retire each matching file using the same stable UUID that ingest.py assigned.
    retired = []
    for path in matches:
        data_id = corpus_file_data_id(path.name)
        result = await cognee.forget(data_id=data_id, dataset=DATASET_NAME)
        retired.append({"data_id": str(data_id), "file": path.name, "result": result})

    return {
        "status": "retired",
        "decision": decision_reference,
        "adr_id": adr_id,
        "retired_items": len(retired),
        "items": retired,
    }
