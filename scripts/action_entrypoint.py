"""
Sentinel GitHub Action entrypoint.

On a PR: load the PR, ensure the decision graph exists, detect reversals, render the
comment. In dry-run mode (default) it just prints + writes the job summary — no token,
no network. In post mode it comments on the PR via the GitHub API.

Env:
  SENTINEL_MODE     dry-run (default) | post
  SENTINEL_PR_FILE  optional path to a PR markdown file (testing); else GitHub event
  GITHUB_TOKEN      required only for mode=post

Sentinel is advisory (detective, not gatekeeper): it never fails the build.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402
import cognee  # noqa: E402
from sentinel.comment import (  # noqa: E402
    render_comment,
    render_feedback_recorded,
    render_resolution,
)
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.github_pr import (  # noqa: E402
    checkout_branch,
    comment_body,
    commit_and_push,
    event_name,
    find_flagged_decision_text,
    issue_number,
    load_pr_text,
    post_comment,
    pr_head_branch,
)
from sentinel.improve import record_noise, record_noise_file  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel.resolve import _adr_number, mark_intentional, supersede_adr_file  # noqa: E402


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _write_summary(comment: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(comment, encoding="utf-8")


async def handle_resolve() -> int:
    """Handle a '/sentinel intentional' comment: retire the flagged decision (forget).

    Two transports, one verb. The DURABLE backstop: mark the ADR Superseded in docs/adr
    on the PR branch and push it (survives a wiped graph; next ingest skips it). The REAL
    Cognee verb, run best-effort alongside it: ``cognee.forget(data_id=...)`` via
    mark_intentional(), which surgically removes that decision's nodes/embeddings from the
    persistent graph so the very next detection no longer flags it. Sentinel is advisory:
    a native-verb failure prints a warning and is swallowed — the command never breaks.
    """
    if "/sentinel intentional" not in comment_body().lower():
        print("Comment is not '/sentinel intentional'; nothing to do.")
        return 0

    number = issue_number()
    adr_id = _adr_number(find_flagged_decision_text(number)) if number else None
    if not adr_id:
        print("No prior Sentinel reversal flag found on this PR; nothing to retire.")
        post_comment("🛡️ _Sentinel_: I couldn't find a reversal I'd flagged on this PR to retire.")
        return 0

    branch = pr_head_branch(number)
    checkout_branch(branch)
    path = supersede_adr_file(adr_id, number)
    if not path:
        post_comment(f"🛡️ _Sentinel_: couldn't locate the `{adr_id}` file in `docs/adr/` to supersede.")
        return 0

    commit_and_push(branch, f"docs(adr): supersede {adr_id} — intentional override in #{number}")
    print(f"-> retired {adr_id}: marked {path.name} Superseded on {branch}")

    # The real Cognee verb, best-effort: genuinely forget the decision from the persistent
    # graph (the git supersession above is the durability backstop). Never fail the command.
    try:
        await setup_cognee()
        result = await mark_intentional(adr_id)
        print(f"-> native cognee.forget: {result.get('status')} "
              f"({result.get('retired_items', 0)} item(s)) for {adr_id}")
    except Exception as exc:  # noqa: BLE001 — advisory: a flaky forget must not break the command
        print(f"native forget skipped (durable ADR supersession already applied): {exc}")

    post_comment(render_resolution(adr_id, number))
    return 0


async def handle_feedback() -> int:
    """Handle a '/sentinel noise' comment: record a 👎 so this drift stops surfacing (improve).

    Two transports, one verb. The DURABLE backstop: append the drift signature to a
    `.sentinel-dismissed` file committed to the PR branch (the next detection reads it live
    and suppresses the flag). The REAL Cognee verb, run best-effort alongside it:
    record_noise() does ``cognee.add`` + ``cognee.cognify`` + ``cognee.improve``, writing the
    👎 into the graph itself. Sentinel is advisory: a native-verb failure prints a warning and
    is swallowed — the maintainer command never breaks.
    """
    if "/sentinel noise" not in comment_body().lower():
        print("Comment is not '/sentinel noise'; nothing to do.")
        return 0

    number = issue_number()
    adr_id = _adr_number(find_flagged_decision_text(number)) if number else None
    if not adr_id:
        print("No prior Sentinel reversal flag found on this PR; nothing to mark as noise.")
        post_comment("🛡️ _Sentinel_: I couldn't find a flag of mine on this PR to mark as noise.")
        return 0

    branch = pr_head_branch(number)
    checkout_branch(branch)
    path = record_noise_file(adr_id)
    commit_and_push(branch, f"chore(sentinel): dismiss {adr_id} drift as noise (/sentinel noise in #{number})")
    print(f"-> dismissed {adr_id} drift as noise: updated {path.name} on {branch}")

    # The real Cognee verb, best-effort: write the 👎 into the graph via cognee.add +
    # cognify + improve (the .sentinel-dismissed file above is the durability backstop).
    # cognify/improve are LLM/embedding-heavy and can be slow/flaky — never fail the command.
    try:
        await setup_cognee()
        result = await record_noise(adr_id, pr_number=number)
        print(f"-> native cognee.improve: {result.get('status')} for {result.get('signature', adr_id)}")
    except Exception as exc:  # noqa: BLE001 — advisory: a flaky improve must not break the command
        print(f"native improve skipped (durable dismissal already recorded): {exc}")

    post_comment(render_feedback_recorded(adr_id, number))
    return 0


async def main() -> int:
    # '/sentinel ...' replies arrive as issue_comment events — handle the forget
    # (intentional) and improve (noise) loops here, before the detection path.
    if event_name() == "issue_comment":
        body = comment_body().lower()
        if "/sentinel intentional" in body:
            return await handle_resolve()
        if "/sentinel noise" in body:
            return await handle_feedback()
        print("Comment is not a Sentinel command; nothing to do.")
        return 0

    mode = os.environ.get("SENTINEL_MODE", "dry-run")
    pr_file = os.environ.get("SENTINEL_PR_FILE") or (sys.argv[1] if len(sys.argv) > 1 else None)

    pr_text = load_pr_text(pr_file)

    try:
        await setup_cognee()
    except RuntimeError as exc:
        msg = (
            f"⚠️ **Sentinel: configuration error** — {exc}\n\n"
            "Sentinel cannot run; skipping check. Fix the error above and re-run."
        )
        print(msg)
        _write_summary(msg)
        return 0  # advisory: never fail the build

    if await _node_count() == 0:
        print("-> decision graph empty; ingesting corpus (one-time)...")
        await ingest_corpus()

    verdict = await detect_reversal(pr_text)
    comment = render_comment(verdict)

    print("\n" + comment + "\n")
    _write_summary(comment)

    if verdict.should_flag:
        # GitHub Actions annotation — surfaces in the PR checks UI.
        print(f"::warning title=Sentinel::This PR reverses {verdict.decision_reference}")
        if mode == "post":
            post_comment(comment)
            print("-> posted comment to PR")
    elif verdict.suppressed_by_feedback:
        print(f"-> reversal of {verdict.decision_reference} muted by prior '/sentinel noise' feedback")

    return 0  # advisory: never fail the build


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
