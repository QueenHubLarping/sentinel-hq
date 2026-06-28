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
from sentinel.comment import render_comment, render_resolution  # noqa: E402
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
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel.resolve import _adr_number, supersede_adr_file  # noqa: E402


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _write_summary(comment: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(comment, encoding="utf-8")


async def handle_resolve() -> int:
    """Handle a '/sentinel intentional' comment: retire the flagged decision.

    Cheap and self-contained — no cognee/LLM. We read which ADR was flagged from
    Sentinel's prior comment, mark that ADR Superseded in docs/adr on the PR's branch,
    push it, and confirm. The next detection rebuilds memory without that ADR.
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
    post_comment(render_resolution(adr_id, number))
    return 0


async def main() -> int:
    # '/sentinel intentional' replies arrive as issue_comment events — handle the
    # forget loop here (no cognee needed) and return before the detection path.
    if event_name() == "issue_comment":
        return await handle_resolve()

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

    if verdict.reverses_decision:
        # GitHub Actions annotation — surfaces in the PR checks UI.
        print(f"::warning title=Sentinel::This PR reverses {verdict.decision_reference}")
        if mode == "post":
            post_comment(comment)
            print("-> posted comment to PR")

    return 0  # advisory: never fail the build


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
